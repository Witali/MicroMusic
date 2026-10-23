"""Assemble tiny speech with separate, strictly bounded Flash and EEPROM images.

Generated binaries, disassembly, PCM and reports belong in an ignored build
directory. An oversized object is measured, but cannot become a runnable image.
Successful images are checked in three cycle-counted ATtiny13 emulator engines.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT/'ATtiny13A/Sound/codec/tiny/firmware.S'
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from fixed_period import decode_fixed, validate
from dc_blocker import block_dc


def sha(data):
    return hashlib.sha256(data).hexdigest()


def intel_hex(data):
    """Emit an address-zero Intel HEX image, for Flash or EEPROM programming."""
    rows = []
    for address in range(0, len(data), 16):
        chunk = data[address:address+16]
        record = bytes((len(chunk), address >> 8, address & 255, 0))+chunk
        rows.append(':'+record.hex().upper()+f'{(-sum(record)) & 255:02X}')
    return '\n'.join(rows+[':00000001FF'])+'\n'


def run(argv, cwd, check=True):
    result = subprocess.run(list(map(str, argv)), cwd=cwd, capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError(result.stdout+result.stderr)
    return result


def parse_symbols(output):
    result = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) == 3 and re.fullmatch(r'[0-9a-fA-F]+', fields[0]):
            result[fields[2]] = int(fields[0], 16)
    return result


def expected_loops(model, loops=3, play_once=False):
    """Restart excitation per phrase and preserve the DC integrator across loops."""
    if play_once:
        return np.r_[decode_fixed(model),np.full(model['samples']*(loops-1),128,np.uint8)]
    source = deepcopy(model)
    source.pop('dc_block_shift', None)
    expected = np.tile(decode_fixed(source), loops)
    shift = model.get('dc_block_shift', 0)
    return block_dc(expected, shift)[0] if shift else expected


def build(model_path, output, avr_bin=None, node='node', play_once=False):
    from tiny_period import pack_tiny
    model_path, output = Path(model_path).resolve(), Path(output).resolve()
    model = json.loads(model_path.read_text(encoding='utf-8'))
    validate(model)
    if model['phase_bits'] != 4 or model['samples'] % 64 or not 1 <= model['samples']//64 <= 1023:
        raise ValueError('Tiny AVR requires phase_bits=4 and 1..1023 complete 64-sample blocks')
    packed = pack_tiny(model)
    tables, fields = bytes(packed['flash_tables']), bytes(packed['field_stream'])
    data, eeprom = bytes(packed['flash_data']), bytes(packed['eeprom'])
    features = packed['constants']
    if data != tables+fields or len(tables) != features['WAVE_FLASH_BYTES']:
        raise ValueError('Packed tiny Flash layout does not match table/stream constants')
    if len(eeprom) != 64 or not 0 <= features['EEPROM_USED_BYTES'] <= 64:
        raise ValueError('Packed tiny EEPROM must be exactly 64 bytes with a valid used length')
    if eeprom[features['EEPROM_USED_BYTES']:] != b'\xff'*(64-features['EEPROM_USED_BYTES']):
        raise ValueError('Unused EEPROM bytes must remain erased (0xFF)')
    constants = dict(SAMPLES=model['samples'], BLOCKS=model['samples']//64,
                     INITIAL_PHASE=model['initial_phase_u16'], NOISE_SEED=model['noise_seed_u16'],
                     DC_SHIFT=model.get('dc_block_shift', 0))
    constants.update(features)
    constants['PLAY_ONCE'] = int(play_once)
    output.mkdir(parents=True, exist_ok=True)
    for name in ('firmware.elf', 'firmware.bin', 'firmware.hex', 'eeprom.bin', 'eeprom.hex',
                 'verification.json', 'build.json', 'actual.raw'):
        (output/name).unlink(missing_ok=True)
    (output/'model-flash.bin').write_bytes(data)
    (output/'eeprom.bin').write_bytes(eeprom)
    (output/'eeprom.hex').write_text(intel_hex(eeprom), encoding='ascii', newline='\n')
    (output/'config.inc').write_text(''.join(f'.set {name},{value}\n' for name,value in constants.items()),
                                    encoding='ascii', newline='\n')
    shutil.copyfile(TEMPLATE, output/'firmware.S')
    expected = expected_loops(model, play_once=play_once)
    (output/'expected.raw').write_bytes(expected.tobytes())
    suffix = '.exe' if os.name == 'nt' else ''
    def executable(name):
        return Path(avr_bin).resolve()/(name+suffix) if avr_bin else name
    compiler, objcopy = executable('avr-gcc'), executable('avr-objcopy')
    compiler_version = run([compiler, '--version'], output).stdout.splitlines()[0]
    run([compiler, '-mmcu=attiny13', '-nostdlib', '-x', 'assembler', '-c',
         'firmware.S', '-o', 'firmware.o'], output)
    symbols = parse_symbols(run([executable('avr-nm'), '-n', 'firmware.o'], output).stdout)
    sections = run([executable('avr-objdump'), '-h', 'firmware.o'], output).stdout
    (output/'sections.txt').write_text(sections, encoding='utf-8', newline='\n')
    match = re.search(r'^\s*\d+\s+\.text\s+([0-9a-fA-F]+)\b', sections, re.MULTILINE)
    if not match or 'wave_data' not in symbols or 'STACK_FLOOR' not in symbols:
        raise ValueError('Tiny firmware must expose .text, wave_data and an absolute STACK_FLOOR')
    if not 0x60 <= symbols['STACK_FLOOR'] <= 0x9f:
        raise ValueError('Tiny firmware static SRAM end is outside the 64-byte SRAM')
    object_bytes, code_bytes = int(match[1], 16), symbols['wave_data']
    if (symbols.get('field_data') != code_bytes+len(tables) or object_bytes != code_bytes+len(data)):
        raise ValueError('Unexpected packed tiny AVR Flash-table layout')
    flash_bytes = (object_bytes+1) & ~1
    report = dict(schema='micromusic-tiny-speech-build-v1', status='oversized' if flash_bytes>1024 else 'pending',
                  playbackMode='once' if play_once else 'loop',
                  hardwareTested=False, cpuHz=9600000, sampleHz=7500, flashLimitBytes=1024,
                  eepromLimitBytes=64, flashBytes=flash_bytes, eepromBytes=len(eeprom),
                  eepromUsedBytes=features['EEPROM_USED_BYTES'], objectTextBytes=object_bytes,
                  linkerPaddingBytes=flash_bytes-object_bytes, codeBytes=code_bytes, dataBytes=len(data),
                  waveformFlashBytes=len(tables), fieldBytes=len(fields), compileFeatures=features,
                  phraseSamples=model['samples'], verifiedLoops=0, constants=constants,
                  compiler=compiler_version, symbols=symbols, modelSha256=sha(model_path.read_bytes()),
                  dataSha256=sha(data), eepromSha256=sha(eeprom), expectedPcmSha256=sha(expected.tobytes()),
                  imageSha256=None, verification=None,
                  normalizedSourceSha256={str(p.relative_to(ROOT)).replace('\\','/'):
                    sha((output/'firmware.S' if p==TEMPLATE else p).read_text(encoding='utf-8').encode('utf-8')) for p in (
                      TEMPLATE, Path(__file__), ROOT/'ATtiny13A/Sound/codec/tiny_period.py',
                      ROOT/'ATtiny13A/Sound/codec/fixed_period.py', ROOT/'ATtiny13A/Sound/codec/dc_blocker.py',
                      ROOT/'tools/verify-tiny-speech.mjs', ROOT/'tools/lib/tiny-work-profile.mjs')})
    if flash_bytes <= 1024:
        run([compiler, '-mmcu=attiny13', '-nostdlib', '-Wl,--defsym=__TEXT_REGION_LENGTH__=1024',
             '-Wl,-Ttext=0', '-x', 'assembler', 'firmware.S', '-o', 'firmware.elf'], output)
        run([objcopy, '-O', 'binary', 'firmware.elf', 'firmware.bin'], output)
        image = (output/'firmware.bin').read_bytes()
        if (len(image)>1024 or len(image)!=flash_bytes or image[code_bytes:object_bytes]!=data or
                image[object_bytes:] not in (b'', b'\x00')):
            raise ValueError('Linked image has unexpected size/table bytes')
        (output/'firmware.hex').write_text(intel_hex(image), encoding='ascii', newline='\n')
        (output/'disassembly.txt').write_text(run([executable('avr-objdump'), '-d', 'firmware.elf'], output).stdout,
                                              encoding='utf-8', newline='\n')
        report['imageSha256'] = sha(image)
        command = [node, ROOT/'tools/verify-tiny-speech.mjs', output/'firmware.bin', output/'expected.raw',
                   output/'verification.json', '--eeprom', output/'eeprom.bin',
                   '--phrase-samples', model['samples'], '--loops', 3,
                   '--minimum-sp', symbols['STACK_FLOOR'], '--actual-raw', output/'actual.raw']
        if play_once:
            command.extend(('--playback','once'))
        if 'wait' in symbols:
            command.extend(('--wait-pc',symbols['wait']))
        verification = run(command, ROOT, check=False)
        if (output/'verification.json').exists():
            report['verification'] = json.loads((output/'verification.json').read_text(encoding='utf-8'))
            report['status'] = 'verified' if report['verification']['pass'] else 'verification-failed'
            report['verifiedLoops'] = report['verification']['verifiedLoops']
        else:
            report['status'] = 'verification-failed'
            report['verificationError'] = (verification.stdout+verification.stderr).strip()
    (output/'build.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--avr-bin', type=Path)
    parser.add_argument('--node', default='node')
    parser.add_argument('--play-once', action='store_true', help='play the phrase once, then output centered silence')
    args = parser.parse_args()
    report = build(args.model, args.output, args.avr_bin, args.node, play_once=args.play_once)
    print(json.dumps(report, indent=2))
    return 1 if report['status']=='verification-failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())

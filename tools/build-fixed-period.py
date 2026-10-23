"""Build a fixed-period AVR model without relaxing ATtiny13 Flash limits.

Oversized objects are measured and reported honestly; no executable image or
emulator validation is produced for them. All generated files belong in an
ignored build directory. A fit image is checked against three AVR engines.
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
TEMPLATE = ROOT/'ATtiny13A/Sound/codec/fixed/firmware.S'
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from fixed_period import decode_fixed, pack_avr_data, validate
from dc_blocker import block_dc


def sha(data):
    return hashlib.sha256(data).hexdigest()


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


def expected_loops(model, loops=3):
    # Waveform phase and synthetic excitation restart per phrase. The output
    # DC estimator remains continuous across the three phrase seams.
    unfiltered = deepcopy(model)
    unfiltered.pop('dc_block_shift', None)
    expected = np.tile(decode_fixed(unfiltered), loops)
    shift = model.get('dc_block_shift', 0)
    return block_dc(expected, shift)[0] if shift else expected


def build(model_path, output, avr_bin=None, node='node'):
    model_path, output = Path(model_path).resolve(), Path(output).resolve()
    model = json.loads(model_path.read_text(encoding='utf-8'))
    validate(model)
    if model['phase_bits'] != 4:
        raise ValueError('Current AVR firmware supports only phase_bits=4')
    if model['samples'] % 64 or (model['samples']+63)//64 > 255:
        raise ValueError('Current AVR block counter requires 64-sample blocks and at most 16320 samples')
    data = pack_avr_data(model)
    output.mkdir(parents=True, exist_ok=True)
    # Never let an old successful image appear to belong to a failed build.
    for name in ('firmware.elf', 'firmware.bin', 'verification.json', 'build.json'):
        (output/name).unlink(missing_ok=True)
    (output/'model-avr.bin').write_bytes(data)
    constants = dict(SAMPLES=model['samples'], BLOCKS=(model['samples']+63)//64,
                     INITIAL_PHASE=model['initial_phase_u16'], NOISE_SEED=model['noise_seed_u16'],
                     DC_SHIFT=model.get('dc_block_shift', 0))
    (output/'config.inc').write_text(''.join(f'.set {name},{value}\n' for name,value in constants.items()),
                                    encoding='ascii', newline='\n')
    shutil.copyfile(TEMPLATE, output/'firmware.S')
    expected = expected_loops(model)
    (output/'expected.raw').write_bytes(expected.tobytes())
    suffix = '.exe' if os.name == 'nt' else ''
    def executable(name):
        return Path(avr_bin).resolve()/(name+suffix) if avr_bin else name
    compiler, objcopy = executable('avr-gcc'), executable('avr-objcopy')
    compiler_version = run([compiler, '--version'], output).stdout.splitlines()[0]
    # The relocatable object lets us measure a too-large experiment while the
    # actual linker and the production emulator retain their real 1 KiB cap.
    run([compiler, '-mmcu=attiny13', '-nostdlib', '-x', 'assembler', '-c',
         'firmware.S', '-o', 'firmware.o'], output)
    symbols = parse_symbols(run([executable('avr-nm'), '-n', 'firmware.o'], output).stdout)
    sections = run([executable('avr-objdump'), '-h', 'firmware.o'], output).stdout
    (output/'sections.txt').write_text(sections, encoding='utf-8', newline='\n')
    match = re.search(r'^\s*\d+\s+\.text\s+([0-9a-fA-F]+)\b', sections, re.MULTILINE)
    if not match or 'wave_data' not in symbols:
        raise ValueError('Firmware must expose .text and wave_data')
    object_bytes, code_bytes = int(match[1], 16), symbols['wave_data']
    if (symbols.get('noise_data') != code_bytes+256 or symbols.get('field_data') != code_bytes+280 or
            object_bytes != code_bytes+len(data)):
        raise ValueError('Unexpected packed AVR flash-table layout')
    flash_bytes = (object_bytes+1) & ~1  # The AVR linker aligns final .text to a word.
    report = dict(schema='micromusic-fixed-period-build-v1', status='oversized' if flash_bytes>1024 else 'pending',
                  hardwareTested=False, cpuHz=9600000, sampleHz=7500, flashLimitBytes=1024,
                  flashBytes=flash_bytes, objectTextBytes=object_bytes,
                  linkerPaddingBytes=flash_bytes-object_bytes, codeBytes=code_bytes, dataBytes=len(data),
                  waveformBytes=256, firBytes=24, fieldBytes=len(data)-280,
                  phraseSamples=model['samples'], verifiedLoops=0,
                  constants=constants, compiler=compiler_version, symbols=symbols,
                  modelSha256=sha(model_path.read_bytes()), dataSha256=sha(data),
                  expectedPcmSha256=sha(expected.tobytes()), imageSha256=None, verification=None,
                  normalizedSourceSha256={str(p.relative_to(ROOT)).replace('\\','/'):
                    sha((output/'firmware.S' if p==TEMPLATE else p).read_text(encoding='utf-8').encode('utf-8')) for p in (
                      TEMPLATE, Path(__file__), ROOT/'ATtiny13A/Sound/codec/fixed_period.py',
                      ROOT/'ATtiny13A/Sound/codec/dc_blocker.py', ROOT/'tools/verify-fixed-period.mjs')})
    if flash_bytes <= 1024:
        run([compiler, '-mmcu=attiny13', '-nostdlib', '-Wl,--defsym=__TEXT_REGION_LENGTH__=1024',
             '-Wl,-Ttext=0', '-x', 'assembler',
             'firmware.S', '-o', 'firmware.elf'], output)
        run([objcopy, '-O', 'binary', 'firmware.elf', 'firmware.bin'], output)
        image = (output/'firmware.bin').read_bytes()
        if (len(image)>1024 or len(image)!=flash_bytes or image[code_bytes:object_bytes]!=data or
                image[object_bytes:] not in (b'', b'\x00')):
            raise ValueError('Linked image has unexpected size/table bytes')
        (output/'disassembly.txt').write_text(run([executable('avr-objdump'), '-d', 'firmware.elf'], output).stdout,
                                              encoding='utf-8', newline='\n')
        report['imageSha256'] = sha(image)
        command = [node, ROOT/'tools/verify-fixed-period.mjs', output/'firmware.bin', output/'expected.raw',
                   output/'verification.json', '--phrase-samples', model['samples'], '--loops', 3,
                   '--minimum-sp', symbols.get('STACK_FLOOR', 0x80)]
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
    args = parser.parse_args()
    report = build(args.model, args.output, args.avr_bin, args.node)
    print(json.dumps(report, indent=2))
    if report['status']=='verification-failed':
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

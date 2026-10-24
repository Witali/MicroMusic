"""Build rounded or original-floor Q3/T1 with 64 speech bytes in EEPROM.

The stream format and exact arithmetic are unchanged. Both generated HEX files
belong to the same build; EEPROM is not a separate optional waveform source.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
TEMPLATE = CODEC/'q3-rounded-eeprom/hq4-t1.S'
FLOOR_TEMPLATE = CODEC/'q3-eeprom/hq4-t1.S'
sys.path.insert(0, str(CODEC))
from hq4_q3_rounded import render
from hq4_q3 import render as floor_render

spec = importlib.util.spec_from_file_location('rounded_eeprom_hq4_helpers', ROOT/'tools/build-hq4-oneshot.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
run, parse_symbols, intel_hex = helpers.run, helpers.parse_symbols, helpers.intel_hex
CORE_BYTES = 450
EEPROM_BYTES = 64
MAX_STREAM_BYTES = 1024-CORE_BYTES-1+EEPROM_BYTES
FLOOR_CORE_BYTES = 448
FLOOR_MAX_STREAM_BYTES = 1024-FLOOR_CORE_BYTES-1+EEPROM_BYTES


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_stream(stream, samples, *, rounded=True):
    if isinstance(samples, bool) or not isinstance(samples, int) or samples <= 0 or samples % 64:
        raise ValueError('Expected a positive complete sample count, multiple of 64')
    source = Path(stream).resolve()
    payload = source.read_bytes()
    maximum = MAX_STREAM_BYTES if rounded else FLOOR_MAX_STREAM_BYTES
    if not EEPROM_BYTES <= len(payload) <= maximum:
        raise ValueError(f'EEPROM-first Q3 requires 64..{maximum} stream bytes')
    frames, durations = helpers.validate_stream(payload)
    if int(durations.sum()) != samples:
        raise ValueError('Stream must preserve the complete requested recording duration')
    if np.any((frames[:, 2:] & 15) == 0) or np.any((frames[:, 2:] >> 4) == 0):
        raise ValueError('Q3 coefficient -8 is excluded from the stable reflection range')
    phrase, wraps = (render if rounded else floor_render)(frames, durations, 1)
    return source, payload, phrase, wraps


def build(stream, output, avr_bin=None, node='node', expected_samples=None, *, rounded=True):
    samples = expected_samples
    if samples is None:
        _, durations = helpers.validate_stream(Path(stream).read_bytes())
        samples = int(durations.sum())
    source, payload, phrase, wraps = load_stream(stream, samples, rounded=rounded)
    template = TEMPLATE if rounded else FLOOR_TEMPLATE
    expected_core = CORE_BYTES if rounded else FLOOR_CORE_BYTES
    maximum = MAX_STREAM_BYTES if rounded else FLOOR_MAX_STREAM_BYTES
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in ('firmware.elf', 'firmware.bin', 'firmware.hex', 'eeprom.hex', 'verification.json', 'actual.raw', 'build.json'):
        (output/name).unlink(missing_ok=True)
    expected = np.r_[phrase, np.full(samples*2, 128, np.uint8)]
    eeprom, tail = payload[:64], payload[64:]
    shutil.copyfile(template, output/'firmware.S')
    (output/'speech.hq').write_bytes(payload)
    (output/'eeprom.bin').write_bytes(eeprom)
    (output/'eeprom.hex').write_text(intel_hex(eeprom), encoding='ascii', newline='\n')
    (output/'expected.raw').write_bytes(expected.tobytes())
    suffix = '.exe' if os.name == 'nt' else ''
    def executable(name):
        return Path(avr_bin).resolve()/(name+suffix) if avr_bin else name
    compiler = executable('avr-gcc')
    version = run([compiler, '--version'], output).stdout.splitlines()[0]
    run([compiler, '-mmcu=attiny13', '-nostdlib', '-x', 'assembler', '-c', 'firmware.S', '-o', 'firmware.o'], output)
    symbols = parse_symbols(run([executable('avr-nm'), '-n', 'firmware.o'], output).stdout)
    sections = run([executable('avr-objdump'), '-h', 'firmware.o'], output).stdout
    match = re.search(r'^\s*\d+\s+\.text\s+([0-9a-fA-F]+)\b', sections, re.MULTILINE)
    if not match or not all(name in symbols for name in ('code_end', 'voice_data', 'STACK_FLOOR', 'wait_slot')):
        raise ValueError('Unexpected rounded-Q3 code layout')
    object_bytes = int(match[1], 16)
    code_bytes, voice_start = symbols['code_end'], symbols['voice_data']
    if code_bytes != expected_core or voice_start != code_bytes or object_bytes != voice_start+len(tail)+1:
        raise ValueError('Measured EEPROM reader/core size or Flash continuation differs')
    flash_bytes = (object_bytes+1) & ~1
    inputs = (template, Path(__file__), CODEC/('hq4_q3_rounded.py' if rounded else 'hq4_q3.py'), CODEC/'hq4_core.py',
              ROOT/'tools/build-hq4-oneshot.py', ROOT/'tools/build-tiny-speech.py',
              ROOT/'tools/verify-tiny-speech.mjs', ROOT/'tools/lib/tiny-work-profile.mjs')
    report = dict(schema='micromusic-q3-eeprom-build-v1', status='pending', playbackMode='once',
        hardwareTested=False, cpuHz=9600000, sampleHz=7500, flashLimitBytes=1024,
        flashBytes=flash_bytes, objectTextBytes=object_bytes, codeBytes=code_bytes,
        dataBytes=len(tail)+1, streamBytes=len(payload), streamFlashBytes=len(tail),
        streamEepromBytes=len(eeprom), maximumStreamBytes=maximum, eofBytes=1,
        linkerPaddingBytes=flash_bytes-object_bytes, codePaddingBytes=0,
        eepromLimitBytes=64, eepromBytes=64, eepromUsedBytes=64, eepromSha256=sha(eeprom),
        phraseSamples=samples, verifiedLoops=0, silenceSamplesVerified=0, compiler=version, symbols=symbols,
        coefficientScale=8, productRounding='nearest, ties toward positive infinity' if rounded else 'floor', tiltShift=1,
        streamSha256=sha(payload), phrasePcmSha256=sha(phrase.tobytes()), expectedPcmSha256=sha(expected.tobytes()),
        streamInput=dict(sourcePath=source.relative_to(ROOT).as_posix() if source.is_relative_to(ROOT) else 'external/'+source.name,
                         copiedPath='speech.hq', sha256=sha(payload)),
        intermediateWraps=wraps.tolist(), imageSha256=None, verification=None,
        storagePolicy='First64 speech bytes in EEPROM; exact continuation and EOF in Flash; program both HEX files',
        normalizedSourceSha256={p.relative_to(ROOT).as_posix():sha(p.read_text(encoding='utf-8').encode()) for p in inputs})
    # This low-level execution builder reports wraps instead of claiming a
    # quality pass; a speech fitter must separately reject unstable candidates.
    if flash_bytes > 1024:
        raise ValueError('Complete EEPROM-first decoder and Flash continuation exceed 1024 bytes')
    run([compiler, '-mmcu=attiny13', '-nostdlib', '-Wl,--defsym=__TEXT_REGION_LENGTH__=1024',
         '-Wl,-Ttext=0', '-x', 'assembler', 'firmware.S', '-o', 'firmware.elf'], output)
    run([executable('avr-objcopy'), '-O', 'binary', 'firmware.elf', 'firmware.bin'], output)
    image = (output/'firmware.bin').read_bytes()
    if len(image) != flash_bytes or image[voice_start:object_bytes] != tail+b'\xff' or image[object_bytes:] not in (b'', b'\x00'):
        raise ValueError('Linked EEPROM-first image changed the Flash continuation or EOF')
    report['imageSha256'] = sha(image)
    (output/'firmware.hex').write_text(intel_hex(image), encoding='ascii', newline='\n')
    (output/'disassembly.txt').write_text(run([executable('avr-objdump'), '-d', 'firmware.elf'], output).stdout,
                                        encoding='utf-8', newline='\n')
    command = [node, ROOT/'tools/verify-tiny-speech.mjs', output/'firmware.bin', output/'expected.raw',
        output/'verification.json', '--eeprom', output/'eeprom.bin', '--phrase-samples', samples,
        '--loops', 3, '--playback', 'once', '--minimum-sp', symbols['STACK_FLOOR'],
        '--wait-pc', symbols['wait_slot'], '--actual-raw', output/'actual.raw']
    checked = run(command, ROOT, check=False)
    if (output/'verification.json').exists():
        verification = json.loads((output/'verification.json').read_text(encoding='utf-8'))
        report.update(verification=verification, status='verified' if verification['pass'] else 'verification-failed',
                      verifiedLoops=verification['verifiedLoops'], silenceSamplesVerified=verification['silenceSamplesVerified'])
    else:
        report.update(status='verification-failed', verificationError=(checked.stdout+checked.stderr).strip())
    (output/'build.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stream', type=Path, required=True)
    parser.add_argument('--samples', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--avr-bin', type=Path)
    parser.add_argument('--node', default='node')
    parser.add_argument('--floor', action='store_true', help='Original Q3 products: 448-byte core, 639-byte stream capacity')
    args = parser.parse_args()
    report = build(args.stream, args.output, args.avr_bin, args.node, expected_samples=args.samples, rounded=not args.floor)
    print(json.dumps({k:report[k] for k in ('status','codeBytes','flashBytes','eepromBytes','streamBytes','maximumStreamBytes')}, indent=2))
    return 0 if report['status'] == 'verified' else 2


if __name__ == '__main__':
    raise SystemExit(main())

"""Pack, assemble and independently verify an experimental long-frame HQ4 model.

This tool consumes explicit frames/durations; it does not claim to analyze or
optimize recordings. No existing public stream or decoder is replaced.
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
TEMPLATE = CODEC/'long-oneshot/hq4.S'
sys.path.insert(0, str(CODEC))
from long_hq4 import DECODER_BYTES, STREAM_BUDGET, pack_stream, unpack_stream
from model import decode

spec = importlib.util.spec_from_file_location('tiny_helpers', ROOT/'tools/build-tiny-speech.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def build(model, output, avr_bin=None, node='node'):
    payload = pack_stream(model['frames'], model['durations'])
    frames, durations = unpack_stream(payload)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = dict(schema='micromusic-long-hq4-build-v1', experimental=True,
                  status='oversized' if len(payload) > STREAM_BUDGET else 'pending',
                  hardwareTested=False, playbackMode='once', cpuHz=9600000,
                  sampleHz=7500, flashLimitBytes=1024, codeBytes=DECODER_BYTES,
                  streamBytes=len(payload), eofBytes=1, eepromBytes=0,
                  phraseSamples=int(np.sum(durations)), frames=len(frames),
                  maximumFrameSamples=int(np.max(durations)), streamSha256=digest(payload))
    # Never leave a stale image apparently associated with a new oversized model.
    for name in ('firmware.elf', 'firmware.bin', 'firmware.hex', 'verification.json', 'actual.raw'):
        (output/name).unlink(missing_ok=True)
    (output/'speech.hq').write_bytes(payload)
    if report['status'] != 'oversized':
        phrase = decode(frames, durations, 0)
        expected = np.r_[phrase, np.full(len(phrase), 128, np.uint8)]
        erased = b'\xff'*64
        shutil.copyfile(TEMPLATE, output/'firmware.S')
        (output/'expected.raw').write_bytes(expected.tobytes())
        (output/'verification-eeprom.bin').write_bytes(erased)
        suffix = '.exe' if os.name == 'nt' else ''

        def executable(name):
            return Path(avr_bin).resolve()/(name+suffix) if avr_bin else name

        compiler = executable('avr-gcc')
        helpers.run([compiler, '-mmcu=attiny13', '-nostdlib',
                     '-Wl,--defsym=__TEXT_REGION_LENGTH__=1024', '-Wl,-Ttext=0',
                     '-x', 'assembler', 'firmware.S', '-o', 'firmware.elf'], output)
        symbols = helpers.parse_symbols(helpers.run([executable('avr-nm'), '-n', 'firmware.elf'], output).stdout)
        helpers.run([executable('avr-objcopy'), '-O', 'binary', 'firmware.elf', 'firmware.bin'], output)
        image = (output/'firmware.bin').read_bytes()
        expected_size = (DECODER_BYTES+len(payload)+2) & ~1
        if (symbols['code_end'] != DECODER_BYTES or symbols['voice_data'] != DECODER_BYTES
                or len(image) != expected_size or len(image) > 1024
                or image[DECODER_BYTES:DECODER_BYTES+len(payload)+1] != payload+b'\xff'):
            raise ValueError('Unexpected long-frame HQ4 image layout')
        (output/'firmware.hex').write_text(helpers.intel_hex(image), encoding='ascii', newline='\n')
        (output/'disassembly.txt').write_text(helpers.run([executable('avr-objdump'), '-d', 'firmware.elf'], output).stdout,
                                             encoding='utf-8', newline='\n')
        command = [node, ROOT/'tools/verify-tiny-speech.mjs', output/'firmware.bin', output/'expected.raw',
                   output/'verification.json', '--eeprom', output/'verification-eeprom.bin',
                   '--phrase-samples', len(phrase), '--loops', 2, '--playback', 'once',
                   '--minimum-sp', symbols['STACK_FLOOR'], '--wait-pc', symbols['wait_slot'],
                   '--actual-raw', output/'actual.raw']
        checked = helpers.run(command, ROOT, check=False)
        verification = (json.loads((output/'verification.json').read_text(encoding='utf-8'))
                        if (output/'verification.json').exists() else None)
        report.update(status='verified' if verification and verification['pass'] else 'verification-failed',
                      flashBytes=len(image), imageSha256=digest(image),
                      phrasePcmSha256=digest(phrase.tobytes()), verification=verification,
                      compiler=helpers.run([compiler, '--version'], output).stdout.splitlines()[0])
        if verification is None:
            report['verificationError'] = (checked.stdout+checked.stderr).strip()
    inputs = [TEMPLATE, Path(__file__), CODEC/'long_hq4.py', CODEC/'model.py']
    report['normalizedSourceSha256'] = {p.relative_to(ROOT).as_posix():
        digest(p.read_text(encoding='utf-8').encode('utf-8')) for p in inputs}
    (output/'build.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    return report


def synthetic_model():
    # Exercise every duration code, both pitch paths, both spectral half updates,
    # full updates and repeats. Total length crosses the 16-bit sample boundary.
    durations = [64, 128, 192, 256]+list(range(320, 3969, 64))
    frames = []
    coefficients = [0x88]*4
    for i, _ in enumerate(durations):
        if i % 4 == 1:
            coefficients[0] = 0x87
        elif i % 4 == 2:
            coefficients[3] = 0x89
        elif i % 4 == 3:
            coefficients = [0x88]*4
        frames.append([0 if i % 3 == 0 else (48 if i % 3 == 1 else 88),
                       2 | ((i % 4) << 4), *coefficients])
    return dict(frames=frames, durations=durations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--model', type=Path, help='JSON object with frames and durations')
    source.add_argument('--self-test', action='store_true', help='Verify every duration code on a synthetic model')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--avr-bin', type=Path)
    parser.add_argument('--node', default='node')
    args = parser.parse_args()
    model = synthetic_model() if args.self_test else json.loads(args.model.read_text(encoding='utf-8'))
    report = build(model, args.output, args.avr_bin, args.node)
    print(json.dumps({key: report.get(key) for key in ('status', 'flashBytes', 'codeBytes', 'streamBytes',
                                                    'phraseSamples', 'maximumFrameSamples')}, indent=2))
    return 0 if report['status'] == 'verified' else 1


if __name__ == '__main__':
    raise SystemExit(main())

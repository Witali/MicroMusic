#!/usr/bin/env python3
"""Build the retained HQ4-T experiment and compare every AVR output sample."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'ATtiny13A/Sound/codec/timbre'
TEMPLATE = BASE / 'chego/firmware.S'
sys.path.insert(0, str(ROOT / 'ATtiny13A/Sound/codec'))
from hq4_core import unpack_stream
from hq4_timbre import decode


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(args, cwd):
    result = subprocess.run(list(map(str, args)), cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-bin', type=Path)
    parser.add_argument('--node', default='node')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--variant', choices=('chego', 'chego-auto', 'chego-spectrum'), default='chego')
    args = parser.parse_args()
    source = BASE / args.variant
    folder = ROOT / 'build/hq4-timbre'
    if args.variant != 'chego':
        folder /= args.variant
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATE, folder / 'firmware.S')
    shutil.copyfile(source / 'speech.hq', folder / 'speech.hq')
    suffix = '.exe' if os.name == 'nt' else ''
    compiler = args.avr_bin.resolve() / ('avr-gcc' + suffix) if args.avr_bin else 'avr-gcc'
    objcopy = args.avr_bin.resolve() / ('avr-objcopy' + suffix) if args.avr_bin else 'avr-objcopy'
    run([compiler, '-mmcu=attiny13', '-nostdlib', '-Wl,-Ttext=0', '-x', 'assembler',
         'firmware.S', '-o', 'firmware.elf'], folder)
    run([objcopy, '-O', 'binary', 'firmware.elf', 'firmware.bin'], folder)
    stream = (folder / 'speech.hq').read_bytes()
    image = (folder / 'firmware.bin').read_bytes()
    size = 422 + len(stream) + 1
    if len(image) - size not in (0, 1) or image[size:] not in (b'', b'\x00', b'\xff'):
        raise ValueError('Unexpected linker padding')
    image = image[:size]
    if size > 1024 or image[422:] != stream + b'\xff':
        raise ValueError('Invalid flash layout')
    (folder / 'firmware.bin').write_bytes(image)
    frames, durations = unpack_stream(stream)
    phrase_samples = int(np.sum(durations))
    if phrase_samples != 9216:
        raise ValueError('Unexpected phrase duration')
    # Three loops exercise persistent lattice and de-emphasis states at the seam.
    pcm = decode(np.tile(frames, (3, 1)), np.tile(durations, 3))
    (folder / 'expected.raw').write_bytes(pcm.tobytes())
    verification = json.loads(run([args.node, ROOT / 'tools/verify-hq4-timbre.mjs',
                                   folder / 'firmware.bin', folder / 'expected.raw'], ROOT))
    report = {
        'schema': 'micromusic-hq4-timbre-verification-v1',
        'codeBytes': 422, 'speechBytes': len(stream), 'sampleHz': 7500,
        'phraseSamples': phrase_samples, 'verifiedLoops': 3,
        'firstLoopPcmSha256': digest(pcm[:phrase_samples].tobytes()),
        'sourceInputs': {str(path.relative_to(ROOT)).replace('\\', '/'):
                         digest(path.read_bytes()) for path in (
                             TEMPLATE, source / 'speech.hq',
                             ROOT / 'ATtiny13A/Sound/codec/model.py',
                             ROOT / 'ATtiny13A/Sound/codec/hq4_timbre.py')},
        **verification,
    }
    # Firmware sources, stream and hashes are retained; generated binaries stay in build/.
    retained = source / 'verification.json'
    if args.check:
        if json.loads(retained.read_text(encoding='utf-8')) != report:
            raise ValueError('Retained verification is stale')
    else:
        retained.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

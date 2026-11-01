#!/usr/bin/env python3
"""Build each lower feature alone and verify a target-ASM reset slice."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import build_wb


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--avr-gcc', required=True)
    p.add_argument('--node', default='node')
    p.add_argument('--corpus', type=Path, default=ROOT/'build/low-corpus')
    p.add_argument('--out', type=Path, default=ROOT/'build/low-features')
    args = p.parse_args()
    rows = []
    for mask, label, width in [(1, 'wb775', 20), (2, 'wb575', 15), (4, 'wb395', 10)]:
        out = args.out/label
        for sub in ['streams', 'oracle']:
            (out/sub).mkdir(parents=True, exist_ok=True)
        name = 'ru_slutskaya_a'
        (out/'streams'/f'{name}.spxraw').write_bytes(
            (args.corpus/label/'streams'/f'{name}.spxraw').read_bytes()[:128*width])
        (out/'oracle'/f'{name}.pcm').write_bytes(
            (args.corpus/label/'oracle'/f'{name}.pcm').read_bytes()[:128*640])
        build_wb.avr(args.avr_gcc, 'asm', packet_bytes=width, enable_nb4=False,
                     low_rates=mask, destination=out)
        subprocess.run([args.node, ROOT/'tests/verify_wb.mjs', '--firmware', out,
                        '--streams', out/'streams', '--oracle', out/'oracle'], check=True)
        report = json.loads((out/'verification.json').read_text())
        rows.append(dict(profile=label, lowerFeatureMask=mask, nb4Enabled=False, **report))
    (args.out/'verification.json').write_bytes((json.dumps(dict(images=rows), indent=2)+'\n').encode())
    print('PASS: three independent optional features, exact ASM PCM/reset, 128 frames each')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Compare complete decoded streams against the unmodified fixed-point release."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default='clang')
    args = parser.parse_args()
    variants = ['reference', 'compact', 'tight', 'profile']
    binaries = {name: build.host(args.cc, name) for name in variants}
    build.verify_primitives(args.cc)
    results = []
    for path in sorted((ROOT / 'reference/R4/data').glob('*.spxraw')):
        data = path.read_bytes()
        assert data and len(data) % 20 == 0
        pcm = {}
        for name, binary in binaries.items():
            output = ROOT / 'build' / name / (path.stem + '.pcm')
            subprocess.run([binary, path, output], check=True, capture_output=True)
            pcm[name] = output.read_bytes()
            assert len(pcm[name]) == len(data) // 20 * 320
        for name in variants[1:]:
            if pcm[name] != pcm['reference']:
                sample = next(i for i, (a, b) in enumerate(zip(pcm[name], pcm['reference'])) if a != b) // 2
                raise AssertionError(f'{path.name}: {name} differs at sample {sample}')
        results.append({'stream': path.name, 'frames': len(data) // 20,
                        'pcm_sha256': hashlib.sha256(pcm['reference']).hexdigest()})
        print(path.name, len(data) // 20, 'frames: identical PCM')
    report = {'reference': 'Unmodified Xiph Speex 1.2.1 fixed point, enhancer/highpass off',
              'variants': variants, 'streams': results, 'frames': sum(r['frames'] for r in results)}
    (ROOT / 'build/pcm-verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('PASS:', report['frames'], 'frames')


if __name__ == '__main__':
    main()

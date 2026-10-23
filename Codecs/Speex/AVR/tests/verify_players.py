#!/usr/bin/env python3
"""Build and simulate the complete PWM player for every retained test stream."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc', required=True)
    parser.add_argument('--node', default='node')
    args = parser.parse_args()
    streams = sorted((ROOT / 'reference/R4/data').glob('*.spxraw'))
    # Leave the speech demo as the final reproducible player ELF/HEX.
    streams.sort(key=lambda p: p.name == 'speech_ru.spxraw')
    results = []
    for stream in streams:
        build.avr(args.avr_gcc, stream)
        subprocess.run([args.node, ROOT / 'tests/verify_player.mjs'], check=True, capture_output=True)
        row = json.loads((ROOT / 'build/player/player-verification.json').read_text(encoding='utf-8'))
        results.append(row)
        print(f"PASS {stream.name}: {row['frames']} frames, no underruns, {row['freeSramAtPeak']} bytes free SRAM", flush=True)
    report = {'simulator': 'avr8js 0.21.1', 'physicalBoardTested': False,
              'includesInterrupts': True, 'frames': sum(r['frames'] for r in results),
              'samples': sum(r['samples'] for r in results),
              'freeSramAtPeak': min(r['freeSramAtPeak'] for r in results),
              'streams': results}
    (ROOT / 'build/player-all.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('PASS: complete player', report['frames'], 'frames /', report['samples'], 'samples', flush=True)


if __name__ == '__main__':
    main()

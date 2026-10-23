#!/usr/bin/env python3
"""Build and simulate the complete PWM player for every retained test stream."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc', required=True)
    parser.add_argument('--node', default='node')
    parser.add_argument('--backend', choices=['asm', 'c'], default='asm')
    parser.add_argument('--streams', type=Path, default=ROOT / 'reference/R4/data')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/player-matrix')
    parser.add_argument('--frame-load-cycles', type=int, default=0,
                        help='Extra CPU work injected into every 20-ms player frame')
    args = parser.parse_args()
    streams = sorted(args.streams.glob('*.spxraw'))
    if not streams:
        parser.error('No raw streams found')
    args.out.mkdir(parents=True, exist_ok=True)
    # Leave the speech demo as the final reproducible player ELF/HEX.
    streams.sort(key=lambda p: p.name == 'speech_ru.spxraw')
    results = []
    for stream in streams:
        build.avr(args.avr_gcc, stream, args.frame_load_cycles, args.backend)
        subprocess.run([args.node, ROOT / 'tests/verify_player.mjs', stream.resolve()], check=True, capture_output=True)
        row = json.loads((ROOT / 'build/player/player-verification.json').read_text(encoding='utf-8'))
        results.append(row)
        for name, suffix in [('player-pwm.u8', '.u8'), ('reference.pcm', '.pcm'),
                             ('player-verification.json', '.json')]:
            shutil.copyfile(ROOT / 'build/player' / name, args.out / (stream.stem + suffix))
        print(f"PASS {stream.name}: {row['frames']} frames, no underruns, {row['freeSramAtPeak']} bytes free SRAM", flush=True)
    report = {'simulator': 'avr8js 0.21.1', 'physicalBoardTested': False,
              'includesInterrupts': True, 'frames': sum(r['frames'] for r in results),
              'extraCpuCyclesPerFrame': args.frame_load_cycles,
              'verifiedReservedCpuPercent': args.frame_load_cycles / 320000 * 100,
              'samples': sum(r['samples'] for r in results),
              'freeSramAtPeak': min(r['freeSramAtPeak'] for r in results),
              'streams': results}
    (args.out / 'player-all.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if args.streams == ROOT / 'reference/R4/data' and not args.frame_load_cycles:
        shutil.copyfile(args.out / 'player-all.json', ROOT / 'build/player-all.json')
    print('PASS: complete player', report['frames'], 'frames /', report['samples'], 'samples', flush=True)


if __name__ == '__main__':
    main()

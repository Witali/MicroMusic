#!/usr/bin/env python3
"""Build and simulate Flash-fed ASM players with all optional rates enabled."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import build
import build_wb


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--avr-gcc', required=True)
    p.add_argument('--node', default='node')
    p.add_argument('--corpus', type=Path, default=ROOT/'build/low-corpus')
    p.add_argument('--legacy-root', type=Path, help='Codec root with existing WB corpora')
    p.add_argument('--oracle', type=Path, required=True)
    p.add_argument('--out', type=Path, default=ROOT/'build/low-flash')
    args = p.parse_args()
    profiles = [('nb215', 6), ('nb395', 10), ('nb595', 15),
                ('wb395', 10), ('wb575', 15), ('wb775', 20)]
    if args.legacy_root:
        profiles += [('wb98', 25), ('wb128', 32)]
    reports = []
    for label, width in profiles:
        folder = args.out/label
        folder.mkdir(parents=True, exist_ok=True)
        source = args.corpus/label/'streams/ru_slutskaya_a.spxraw'
        if label == 'wb98':
            source = args.legacy_root/'build/wb-corpus/streams/ru_slutskaya_a.spxraw'
        elif label == 'wb128':
            source = args.legacy_root/'build/higher-corpus/wb128/streams/ru_slutskaya_a.spxraw'
        data = source.read_bytes()[:128*width]
        assert len(data) == 128*width
        stream, oracle = folder/'slice.spxraw', folder/'slice.pcm'
        stream.write_bytes(data)
        wide = label.startswith('wb')
        subprocess.run([str(args.oracle), str(int(wide)), str(width), stream, oracle], check=True)
        if wide:
            build_wb.avr(args.avr_gcc, 'asm', stream=stream, load=9600,
                         destination=folder, enable_nb4=True, low_rates=7)
            command = [args.node, ROOT/'tests/verify_wb_player.mjs', stream, folder, oracle]
        else:
            build.avr(args.avr_gcc, packet_file=stream, frame_load_cycles=9600,
                      backend='asm', enable_nb4=True, low_rates=7, destination=folder)
            command = [args.node, ROOT/'tests/verify_player.mjs', stream,
                       '--firmware', folder, '--oracle', oracle]
        subprocess.run(command, check=True)
        report = json.loads((folder/'player-verification.json').read_text())
        reports.append(dict(profile=label, sourceStream=source.name,
                            sourceSha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                            pcmSha256=hashlib.sha256(oracle.read_bytes()).hexdigest(), **report))
    result = dict(scope='128-frame reset slices in MCU program Flash; all rates enabled; 3% added work',
                  frames=sum(r['frames'] for r in reports), includesInterrupts=True,
                  physicalBoardTested=False, underruns=0, streams=reports)
    (args.out/'verification.json').write_bytes((json.dumps(result, indent=2)+'\n').encode())
    print('PASS Flash-fed players:', len(reports), 'profiles /', result['frames'], 'frames')


if __name__ == '__main__':
    main()

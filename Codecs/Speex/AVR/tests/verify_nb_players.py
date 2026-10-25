#!/usr/bin/env python3
"""Freeze NB player images and verify every retained stream with timer IRQs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build


def source_hashes():
    files=list((ROOT/'src').glob('*'))
    files += [ROOT/'tools'/n for n in ['build.py','apply_profile.py']]
    files += [ROOT/'tests'/n for n in ['verify_nb_players.py','verify_player.mjs','avr_tick.mjs']]
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(files) if p.is_file()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc',required=True)
    parser.add_argument('--node',default='node')
    parser.add_argument('--backend',choices=['asm','c'],default='asm')
    parser.add_argument('--streams',type=Path,default=ROOT/'reference/R4/data')
    parser.add_argument('--out',type=Path,default=ROOT/'build/nb-player-frozen')
    parser.add_argument('--filter',default='.')
    parser.add_argument('--frame-load-cycles',type=int,default=0)
    args=parser.parse_args()
    streams=[p for p in sorted(args.streams.glob('*.spxraw')) if re.search(args.filter,p.stem)]
    if not streams:parser.error('No matching streams')
    args.out.mkdir(parents=True,exist_ok=True)
    snapshot=source_hashes()
    (args.out/'source-sha256.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    rows=[]
    for stream in streams:
        build.avr(args.avr_gcc,stream,args.frame_load_cycles,args.backend)
        result=subprocess.run([args.node,str(ROOT/'tests/verify_player.mjs'),str(stream.resolve())],
                              capture_output=True)
        image=args.out/stream.stem;image.mkdir(parents=True,exist_ok=True)
        (image/'simulation.log').write_bytes(result.stdout+result.stderr)
        result.check_returncode()
        for file in (ROOT/'build/player').iterdir():
            if file.is_file():shutil.copyfile(file,image/file.name)
        row=json.loads((image/'player-verification.json').read_text())
        assert row['backend']==args.backend and row['underruns']==0
        assert hashlib.sha256((image/'speex-player.bin').read_bytes()).hexdigest()==row['binarySha256']
        assert source_hashes()==snapshot,'Player sources changed during validation'
        rows.append(row)
        print(f"PASS {stream.name}: {row['frames']} frames, {row['freeSramAtPeak']} B free, "
              f"min queue {row['minQueuedSamplesBeforeOutput']}",flush=True)
    report=dict(backend=args.backend,simulator='avr8js 0.21.1 + tests/avr_tick.mjs',
        includesInterrupts=True,physicalBoardTested=False,frames=sum(r['frames'] for r in rows),
        samples=sum(r['samples'] for r in rows),underruns=sum(r['underruns'] for r in rows),
        extraCpuCyclesPerFrame=args.frame_load_cycles,
        verifiedReservedCpuPercent=args.frame_load_cycles/3200,
        freeSramAtPeak=min(r['freeSramAtPeak'] for r in rows),
        minQueuedSamplesBeforeOutput=min(r['minQueuedSamplesBeforeOutput'] for r in rows),
        maxBlockReadyGapCycles=max(r['maxBlockReadyGapCycles'] for r in rows),streams=rows)
    (args.out/'player-all.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='streams'}),flush=True)


if __name__=='__main__':main()

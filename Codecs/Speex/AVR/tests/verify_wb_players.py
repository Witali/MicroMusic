#!/usr/bin/env python3
"""Build frozen WB player images and verify 16-kHz PWM with both timers/IRQ."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_wb
def source_hashes():
    files=list((ROOT/'src').glob('*'))+[ROOT/'tools'/s for s in ['build.py','apply_profile.py','build_wb.py']]
    files +=[ROOT/'tests'/s for s in ['verify_wb_player.mjs','avr_tick.mjs']]
    return {f.relative_to(ROOT).as_posix():hashlib.sha256(f.read_bytes()).hexdigest()
        for f in sorted(files) if f.is_file()}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--avr-gcc',required=True);p.add_argument('--node',default='node')
    p.add_argument('--streams',type=Path,default=ROOT/'build/wb-corpus/streams')
    p.add_argument('--oracle',type=Path,default=ROOT/'build/wb-corpus/oracle')
    p.add_argument('--out',type=Path,default=ROOT/'build/wb-pwm')
    p.add_argument('--filter',default='^(ru_|en_)')
    p.add_argument('--frame-load-cycles',type=int,default=0)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    streams=[f for f in sorted(args.streams.glob('*.spxraw')) if re.search(args.filter,f.stem)]
    if not streams:p.error('No matching streams')
    snapshot=source_hashes();(args.out/'source-sha256.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    rows=[]
    for stream in streams:
        image=args.out/stream.stem
        build_wb.avr(args.avr_gcc,'asm',stream,args.frame_load_cycles,image)
        result=subprocess.run([args.node,str(ROOT/'tests/verify_wb_player.mjs'),str(stream.resolve()),
            str(image.resolve()),str((args.oracle/(stream.stem+'.pcm')).resolve())],capture_output=True)
        (image/'simulation.log').write_bytes(result.stdout+result.stderr)
        if result.returncode:
            sys.stderr.write(result.stderr.decode(errors='replace'));result.check_returncode()
        row=json.loads((image/'player-verification.json').read_text());rows.append(row)
        assert source_hashes()==snapshot,'Player source changed during verification'
        print(f"PASS {stream.name}: {row['frames']} frames, {row['freeSramAtPeak']} B free, min queue {row['minQueuedSamplesBeforeOutput']}",flush=True)
    report=dict(profile='WB1-Q7-16',simulator='avr8js 0.21.1 + tests/avr_tick.mjs',
        physicalBoardTested=False,includesInterrupts=True,sampleRate=16000,
        frames=sum(r['frames'] for r in rows),samples=sum(r['samples'] for r in rows),
        underruns=sum(r['underruns'] for r in rows),
        minQueuedSamplesBeforeOutput=min(r['minQueuedSamplesBeforeOutput'] for r in rows),
        freeSramAtPeak=min(r['freeSramAtPeak'] for r in rows),
        extraCpuCyclesPerFrame=args.frame_load_cycles,streams=rows)
    (args.out/'player-all.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='streams'}),flush=True)
if __name__=='__main__':main()

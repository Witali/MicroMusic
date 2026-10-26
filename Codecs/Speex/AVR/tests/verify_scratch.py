#!/usr/bin/env python3
"""Check the instrumented native NB decoder's reduced scratch on all streams."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--decoder',type=Path,default=ROOT/'build/profile'/('decode.exe' if os.name=='nt' else 'decode'))
    p.add_argument('--streams',type=Path,default=ROOT/'build/cache3-corpus/streams')
    p.add_argument('--oracle',type=Path,default=ROOT/'build/cache3-corpus/oracle')
    p.add_argument('--out',type=Path,default=ROOT/'build/lifetime-native-scratch')
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True);rows=[]
    for stream in sorted(args.streams.glob('*.spxraw')):
        actual=args.out/(stream.stem+'.pcm')
        result=subprocess.check_output([args.decoder,stream,actual],text=True)
        match=re.search(r'static state\+scratch=(\d+) scratch_peak=(\d+)',result);assert match
        state,peak=map(int,match.groups());assert peak==40,'Instrumented PUSH must fit the 40-byte arena'
        assert actual.read_bytes()==(args.oracle/(stream.stem+'.pcm')).read_bytes()
        rows.append(dict(stream=stream.name,frames=stream.stat().st_size//20,stateBytes=state,scratchPeak=peak,
            inputSha256=digest(stream),pcmSha256=digest(actual)))
    assert rows and len({r['stateBytes'] for r in rows})==1
    report=dict(instrumentedPushChecksEnabled=True,scratchPeak=40,exactPcm=True,
        decoderSha256=digest(args.decoder),frames=sum(r['frames'] for r in rows),streams=rows,
        sourceSha256={p.relative_to(ROOT).as_posix():digest(p) for p in sorted((ROOT/'src').iterdir()) if p.is_file()})
    (args.out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f"PASS: {len(rows)} streams / {report['frames']} exact frames; checked scratch peak 40 B")
if __name__=='__main__':main()

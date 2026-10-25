#!/usr/bin/env python3
"""Combine retained NB fixtures/speech and decode with the independent oracle."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'build/nb-corpus')
    args=parser.parse_args()
    streams=args.out/'streams';oracle=args.out/'oracle'
    streams.mkdir(parents=True,exist_ok=True);oracle.mkdir(parents=True,exist_ok=True)
    decoder=ROOT/'build/reference'/('decode.exe' if sys.platform=='win32' else 'decode')
    sources=[ROOT/'reference/R4/data',ROOT/'build/real-speech/streams']
    rows=[];names=set()
    for directory in sources:
        files=sorted(directory.glob('*.spxraw'))
        if not files:raise ValueError('Prepare retained fixtures/speech first: '+str(directory))
        for file in files:
            if file.name in names:raise ValueError('Duplicate stream '+file.name)
            names.add(file.name);raw=file.read_bytes()
            assert raw and len(raw)%20==0 and all(raw[i]>>3==3 for i in range(0,len(raw),20))
            target=streams/file.name;shutil.copyfile(file,target)
            pcm=oracle/(file.stem+'.pcm')
            subprocess.run([str(decoder),str(target),str(pcm)],check=True)
            data=pcm.read_bytes();assert len(data)==len(raw)//20*320
            rows.append(dict(stream=file.name,frames=len(raw)//20,
                inputSha256=hashlib.sha256(raw).hexdigest(),pcmSha256=hashlib.sha256(data).hexdigest()))
    report=dict(oracle='Pinned untouched Xiph Speex 1.2.1 fixed-point NB decoder',
        frames=sum(r['frames'] for r in rows),streams=sorted(rows,key=lambda r:r['stream']))
    (args.out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(streams=len(rows),frames=report['frames'])))


if __name__=='__main__':main()

#!/usr/bin/env python3
"""Retain 16-kHz raw speech packets and independent WB1 reference PCM."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
EXE='decode.exe' if sys.platform=='win32' else 'decode'
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--clips',type=Path,default=ROOT/'build/real-speech/clips')
    p.add_argument('--out',type=Path,default=ROOT/'build/wb-corpus')
    args=p.parse_args();streams=args.out/'streams';oracle=args.out/'oracle'
    streams.mkdir(parents=True,exist_ok=True);oracle.mkdir(exist_ok=True)
    files=sorted(args.clips.glob('*/16000/encoded.spxraw'))
    if not files:raise ValueError('Prepare the 16-kHz speech corpus first (verify_rates.py)')
    for f in files:shutil.copyfile(f,streams/(f.parent.parent.name+'.spxraw'))
    # Every pair of high-band LSP codebook indices, all 32 folding gains,
    # four distinct gains/subframes and transitions between codebook pairs.
    base=files[0].read_bytes();packets=[]
    for a in range(64):
        for b in range(64):
            i=a*64+b;q=i&31
            tail=(9<<32)|(a<<26)|(b<<20)|(q<<15)|(((q+7)&31)<<10)|(((q+17)&31)<<5)|((q+29)&31)
            nb=base[(i%(len(base)//25))*25:][:20]
            packets.append(nb+((tail<<4)|15).to_bytes(5,'big'))
    (streams/'coverage_lsp4096.spxraw').write_bytes(b''.join(packets))
    rows=[]
    for f in sorted(streams.glob('*.spxraw')):
        target=oracle/(f.stem+'.pcm');actual=args.out/(f.stem+'-native.pcm')
        subprocess.run([str(ROOT/'build/wb-reference'/EXE),'1','25',str(f),str(target)],check=True)
        subprocess.run([str(ROOT/'build/wb-native'/EXE),str(f),str(actual)],check=True)
        assert target.read_bytes()==actual.read_bytes(),f.name
        data=f.read_bytes();pcm=target.read_bytes();assert len(pcm)==len(data)//25*640
        rows.append(dict(stream=f.name,frames=len(data)//25,inputSha256=hashlib.sha256(data).hexdigest(),
            pcmSha256=hashlib.sha256(pcm).hexdigest(),nativeCExact=True))
    report=dict(profile='WB1-Q7-16',frames=sum(r['frames'] for r in rows),streams=rows,
        oracle='Untouched Xiph NB/HB; only final QMF replaced by independent compact-filter equation')
    (args.out/'native-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(frames=report['frames'],streams=len(rows),nativeCExact=True)))
if __name__=='__main__':main()

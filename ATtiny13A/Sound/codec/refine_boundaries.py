#!/usr/bin/env python3
"""Losslessly preserve total sample count while moving subframe boundaries.
Uses the exact AVR arithmetic decoder and hard 1 KiB flash constraint.
"""
import argparse,time,json
import numpy as np,soundfile as sf
from pathlib import Path
from optimize_hq4 import OUT, REF, stoi_value, clicks, spec
from hq4_core import decode,pack_stream

def refine(name,passes=10):
    p=OUT/name/'best.npz'; ob=np.load(p);f=ob['frames'].copy();d=ob['durations'].copy()
    ref,sr=sf.read(REF/name/'original.wav');assert sr==7500
    s=stoi_value(ref,decode(f,d));orig=s
    origsp=spec(ref,decode(f,d));valid=0;start=time.monotonic();num=0
    maxlen=1024-406-1
    for phase in range(passes):
        improved=0
        it=range(len(d)-1) if phase%2==0 else range(len(d)-2,-1,-1)
        for idx in it:
            a,b=int(d[idx]),int(d[idx+1]);total=a+b
            opts=[(z,total-z) for z in [64,128,192,256] if 64<=total-z<=256 and z!=a]
            candidate=None;best=s
            for aa,bb in opts:
                d[idx]=aa;d[idx+1]=bb
                if len(pack_stream(f,d))>maxlen:continue
                y=decode(f,d);num+=1
                if clicks(y)>0:continue
                st=stoi_value(ref,y)
                if st>best+0.000003 and spec(ref,y)<=origsp*1.06:
                    candidate=(aa,bb);best=st
            d[idx]=a;d[idx+1]=b
            if candidate:
                d[idx],d[idx+1]=candidate;s=best;improved+=1;valid+=1
                print(name,'swap at',idx,(a,b),'->',candidate,'stoi',s,flush=True)
        print(name,'phase',phase+1,'STOI',s,'improvements',improved,flush=True)
        if not improved:break
    np.savez(p,frames=f,durations=d)
    stream=pack_stream(f,d);(OUT/name/'speech.hq').write_bytes(stream)
    pcm=decode(f,d);(OUT/name/'expected_pcm.raw').write_bytes(pcm.tobytes())
    info={'name':name,'baseline_stoi':orig,'after_stoi':s,'changes':valid,'checks':num,'duration_seconds':time.monotonic()-start,'flash':406+len(stream)+1,'spectrum':spec(ref,pcm)}
    (OUT/name/'boundary_refinement.json').write_text(json.dumps(info,indent=2))
    print('FINAL',info,flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--clip',required=True);p.add_argument('--passes',type=int,default=10);a=p.parse_args();refine(a.clip,a.passes)

#!/usr/bin/env python3
"""Second feedback pass: tune F0, loudness, pulse shape and K1..K8 with code budget.
This script changes only encoded data. No fixed-frame/legacy code is linked into AVR.
"""
import argparse,time,json,random
from pathlib import Path
import numpy as np,soundfile as sf
from quality import Compare
from model import decode
from build_hq import encode
ROOT=Path(__file__).resolve().parent

def streamlen(f,d):return len(encode(f,d)[0])
def score(cp,x):
 st,spec,click=cp.scores(x)
 return st-0.014*spec-0.003*click,(st,spec,click)

def setcoeff(row,k,value):
 old=int(row[2+k//2]);row[2+k//2]=((old&240)|value) if k%2==0 else ((old&15)|(value<<4))

def tune(name,seconds=35,passes=2):
 path=ROOT/'samples'/name;stored=np.load(path/'trained.npz');f=stored['frames'].copy();d=stored['durations'].copy();ref,sr=sf.read(ROOT/'references'/name/'original.wav');assert sr==7500
 cp=Compare(ref);baseline=score(cp,decode(f,d,0));current=baseline[0];initial=baseline[1];click_limit=initial[2];limit=610
 print(name,'start',initial,'size',streamlen(f,d),flush=True)
 t0=time.monotonic();changes=0;examined=0
 # Prioritize frames that change sharply, include all eventually.
 frame_indices=list(range(len(f)))
 rng=random.Random(315)
 for iteration in range(passes):
  if iteration%2:frame_indices=frame_indices[::-1]
  else: rng.shuffle(frame_indices)
  for idx in frame_indices:
   if time.monotonic()-t0>=seconds:break
   prev=f[idx].copy();p=int(prev[0]);g=int(prev[1])&15;m=(int(prev[1])>>4)&3
   # Search independent axes; each uses a fresh current snapshot. One change per axis per frame.
   for dim in [0,1,2,3]:
    if time.monotonic()-t0>=seconds:break
    row=f[idx].copy();p=int(row[0]);g=int(row[1])&15;m=(int(row[1])>>4)&3
    if dim==0:
     opts=[p-4,p-3,p-2,p-1,p+1,p+2,p+3,p+4,p//2,p*2,round(p*1.5),round(p*.7),0]
     vals=[(q,g,m,None,None) for q in sorted(set(opts)) if q==0 or 16<=q<=126]
    elif dim==1:
     opts=[g-4,g-2,g-1,g+1,g+2,g+4,0,4,8,12,15]
     vals=[(p,q,m,None,None) for q in sorted(set(opts)) if 0<=q<=15]
    elif dim==2:
     vals=[(p,g,q,None,None) for q in range(4) if q!=m]
    else:
     vals=[]
     for k in range(8):
      quant=(int(row[2+k//2])>>(4*(k%2)))&15
      for dv in [-2,-1,1,2]:
       if 0<=quant+dv<16:vals.append((p,g,m,k,quant+dv))
    best=current;chosen=None;metrics=None
    for p2,g2,m2,k,v in vals:
     f[idx,0]=p2;f[idx,1]=(m2<<4)|g2
     if k is not None:setcoeff(f[idx],k,v)
     examined+=1
     if streamlen(f,d)<=limit:
      result=score(cp,decode(f,d,0));vscore,mets=result
      if vscore>best+0.000015 and mets[2]<=click_limit and mets[0]>=initial[0]-0.0001:
       best=vscore;chosen=f[idx].copy();metrics=mets
     f[idx]=row
    if chosen is not None:
     f[idx]=chosen;current=best;changes+=1
     if changes%12==0:print(name,'changes',changes,'STOI',round(metrics[0],5),'spec',round(metrics[1],4),'stream bytes',streamlen(f,d),'evals',examined,flush=True)
  if time.monotonic()-t0>=seconds:break
 sig=decode(f,d,0);final=score(cp,sig)[1];np.savez(path/'trained.npz',frames=f,durations=d)
 # Preserve training report from earlier pass.
 result={'baseline':initial,'final':final,'changed':changes,'trials':examined,'stream_bytes':streamlen(f,d),'run_seconds':round(time.monotonic()-t0,2)}
 (path/'refinement.json').write_text(json.dumps(result,indent=2))
 print(name,'DONE',result,flush=True)
 return result

if __name__=='__main__':
 pa=argparse.ArgumentParser();pa.add_argument('--voice',choices=['chego','otvechaesh','vinni'],required=True);pa.add_argument('--seconds',type=int,default=35);pa.add_argument('--passes',type=int,default=2)
 ar=pa.parse_args();tune(ar.voice,ar.seconds,ar.passes)

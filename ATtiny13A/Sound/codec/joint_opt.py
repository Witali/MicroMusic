#!/usr/bin/env python3
"""Deterministic rate-constrained LPC refinement with coupled parameter moves.

Complements refine_hq.py: that script adjusts a parameter in one frame,
this one tests correlated changes in 2-4 consecutive frames, swaps 64/128ms
frame durations, and cross-fades local reflection-coefficient patterns.
Decoding is the same AVR-bit-exact MiniLPC-HQ model. Checks click budget.
No data/format changes are inserted into the AVR decoder.
"""
from pathlib import Path
import argparse,json,time
import numpy as np,soundfile as sf
from quality import Compare
from model import decode
from build_hq import encode
ROOT=Path(__file__).parent

def edit_k(frames,i,k,delta):
    ind=2+k//2; b=int(frames[i,ind]);q=(b>>(4*(k%2)))&15
    q2=int(np.clip(q+delta,0,15))
    frames[i,ind]=((b&240)|q2) if (k&1)==0 else ((b&15)|(q2<<4))

def main():
  a=argparse.ArgumentParser(description=__doc__)
  a.add_argument('--voice',choices=['chego','otvechaesh','vinni'],required=True)
  a.add_argument('--seconds',type=int,default=75)
  a.add_argument('--max-evals',type=int,default=18000)
  a.add_argument('--seed',type=int,default=1377)
  args=a.parse_args()
  ref,sr=sf.read(ROOT/'references'/args.voice/'original.wav');assert sr==7500
  comp=Compare(ref);path=ROOT/'samples'/args.voice
  old=np.load(path/'trained.npz');f=old['frames'].copy();d=old['durations'].copy()
  # Reject changes that introduce strong adjacent-sample jumps.
  def evaluate(f,d):
    b=encode(f,d)[0]
    if len(b)>610:return None
    y=decode(f,d,0)
    st,spec,clicks=comp.scores(y)
    if clicks:return None
    return (st-0.005*spec),st,spec,len(b)
  initial=evaluate(f,d);assert initial is not None
  best=initial;accepted=0;tested=0
  rng=np.random.default_rng(args.seed)
  t0=time.monotonic();freq={}
  while tested<args.max_evals and time.monotonic()-t0<args.seconds:
    i=int(rng.integers(len(f)))
    ff=f.copy();dd=d.copy()
    op=int(rng.integers(8));j=min(len(f)-1,i+1)
    if op==0: # share a new pitch offset across two frames
      step=int(rng.choice([-4,-3,-2,-1,1,2,3,4])); count=int(rng.integers(1,4))
      for k in range(i,min(len(f),i+count)):
        if ff[k,0]!=0:ff[k,0]=np.clip(int(ff[k,0])+step,15,126)
    elif op==1: # gain envelope movement across two frames
      step=int(rng.choice([-3,-2,-1,1,2,3]));count=int(rng.integers(1,4))
      for k in range(i,min(len(f),i+count)):
        h=int(ff[k,1]);ff[k,1]=(h&240)|np.clip((h&15)+step,0,15)
    elif op==2: # coupled one coefficient
      k=int(rng.integers(8));step=int(rng.choice([-2,-1,1,2]))
      for z in (i,j):edit_k(ff,z,k,step)
    elif op==3: # interpolate one spectral code towards a neighbor
      k=int(rng.integers(8));ind=2+k//2;bit=4*(k%2)
      if i==j:continue
      q=int((ff[i,ind]>>bit)&15);qq=int((ff[j,ind]>>bit)&15)
      if q==qq:continue
      edit_k(ff,i,k,1 if qq>q else -1)
    elif op==4: # local excitation mode re-selection
      m=int(rng.integers(4));idx=i if rng.random()<.5 else j
      ff[idx,1]=(int(ff[idx,1])&15)|(m<<4)
    elif op==5: # moving frame timing boundary without changing total length
      if i==j or (int(dd[i]),int(dd[j])) not in [(64,128),(128,64)]:continue
      dd[i],dd[j]=dd[j],dd[i]
    elif op==6: # correlated gain+pitch along time (different effects)
      step=int(rng.choice([-2,-1,1,2])); h=int(ff[i,1]);ff[i,1]=(h&240)|np.clip((h&15)+step,0,15)
      if ff[i,0]!=0:ff[i,0]=np.clip(int(ff[i,0])+step,15,126)
    else: # morph a whole half-spectrum (4 LPC coeffs) to local neighbor
      if i==j:continue
      half=int(rng.integers(2));s=2+half*2
      target=ff[j,s:s+2].copy();src=ff[i,s:s+2].copy()
      for z in range(2):
        a0=int(src[z]);b0=int(target[z]);lo=(a0&15);hi=(a0>>4);blo=(b0&15);bhi=(b0>>4)
        lo=np.clip(lo+np.sign(blo-lo),0,15);hi=np.clip(hi+np.sign(bhi-hi),0,15)
        ff[i,s+z]=int(lo)|(int(hi)<<4)
    metrics=evaluate(ff,dd);tested+=1
    if metrics is not None and metrics[0]>best[0]+0.000007:
      f,d=ff,dd;best=metrics;accepted+=1;freq[op]=freq.get(op,0)+1
      if accepted%10==0:
        print(args.voice,'accepted',accepted,'stoi',round(best[1],6),'spec',round(best[2],5),'bytes',best[3],'evals',tested,'sec',round(time.monotonic()-t0),flush=True)
  # Retain result only if measured quality improved under exactly the same constraints.
  assert best[0]>=initial[0]
  np.savez(path/'trained.npz',frames=f,durations=d)
  report={'initial':{'stoi':initial[1],'spec':initial[2],'stream_bytes':initial[3]},
          'final':{'stoi':best[1],'spec':best[2],'stream_bytes':best[3]},
          'accepted':accepted,'evals':tested,'elapsed_s':round(time.monotonic()-t0,2),'operations':freq,'seed':args.seed}
  (path/'joint_search.json').write_text(json.dumps(report,indent=2))
  print(args.voice,'DONE',report,flush=True)
if __name__=='__main__': main()

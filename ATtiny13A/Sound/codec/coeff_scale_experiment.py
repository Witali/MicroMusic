#!/usr/bin/env python3
"""Explore Q3 reflection coefficients instead of Q4 (wider lattice range).
No new hardware or additional frame data; offline-only until AVR is assembled.
"""
import sys,time,json,argparse
from pathlib import Path
import numpy as np,soundfile as sf
from numba import njit

from quality import Compare
from hq4_codec import unpack,encode
from optimize_hq4 import ROOT,SRC,quant_edit
from model import decode

@njit
def s8(v):return ((v+128)&255)-128
@njit
def synth_q(frames,durations,shift):
 n=int(np.sum(durations));out=np.empty(n,np.uint8)
 state=np.zeros(8,np.int32);k=np.zeros(8,np.int32)
 seed=0xa7;period=0;gain=0;phase=1;mode=0;fi=0;next_t=int(durations[0])-1
 for t in range(n):
  if t==0 or t==next_t:
   if t!=0:
    fi+=1
    if fi>=len(frames):fi=0
    next_t+=int(durations[fi])
   period=int(frames[fi,0]);gain=int(frames[fi,1])&15;mode=(int(frames[fi,1])>>4)&3;phase=period
   for j in range(4):
    data=int(frames[fi,2+j]);k[j*2]=(data&15)-8;k[j*2+1]=(data>>4)-8
  ex=0
  if period:
   phase=(phase-1)&255
   if phase==0:phase=period;ex=(2*gain)&255
   else:
    lag=period-phase
    if lag==1:ex=(gain*(3-(mode&1)))&255
    elif lag==2:ex=(gain*(2-(mode>>1)))&255
    elif lag==3:ex=(-gain)&255
  else:
   low=seed&1;seed>>=1
   if low:seed^=0xb8
   ex=((-gain if seed&1 else gain))&255
  for j in range(7,-1,-1):
   old=state[j];coef=k[j]
   a=s8(old)
   if coef<0:a=s8(-a)
   mm=((a*abs(coef))>>shift)&255
   ex=(ex-mm)&255
   if j<7:
    b=s8(ex)
    if coef<0:b=s8(-b)
    nm=((b*abs(coef))>>shift)&255
    state[j+1]=(old+nm)&255
  state[0]=ex;out[t]=(ex+128)&255
 return out

def remap(src):
 f=src.copy()
 for i in range(len(f)):
  for k in range(8):
   j=2+k//2;shift=(k%2)*4;q=((int(src[i,j])>>shift)&15)-8
   vv=int(np.clip(round(q/2),-8,7))+8
   f[i,j]=(int(f[i,j])&~(15<<shift))|(vv<<shift)
 return f

def run(n,iterations=3000,seed=9):
 f0,d,_=unpack((SRC/n/'speech.hq').read_bytes()+b'\xff');f=remap(f0)
 ref,sr=sf.read(str(ROOT/'references')+'/'+n+'/original.wav');comp=Compare(ref)
 original=comp.scores(decode(f0,d));start=comp.scores(synth_q(f,d,3));current=start[0]-.006*start[1];rng=np.random.default_rng(seed);acc=0;t0=time.monotonic()
 for z in range(iterations):
  i=int(rng.integers(len(f)));old=f[i].copy()
  typ=int(rng.choice(4,p=[.62,.14,.16,.08]));
  if typ==0:quant_edit(f,i,int(rng.integers(8)),int(rng.choice([-2,-1,1,2])))
  elif typ==1:
   k=int(f[i,1])&15;v=k+int(rng.choice([-2,-1,1,2]));
   if not 0<=v<=15:continue
   f[i,1]=(int(f[i,1])&240)|v
  elif typ==2:
   p=int(f[i,0]);v=p+int(rng.choice([-2,-1,1,2]));
   if p==0 or not 16<=v<=126:continue
   f[i,0]=v
  else:f[i,1]=(int(f[i,1])&15)|(int(rng.integers(4))<<4)
  if len(encode(f,d))<=617:
   y=synth_q(f,d,3)
   if not np.any(np.abs(np.diff(y.astype(np.int16)))>=48):
    mt=comp.scores(y);obj=mt[0]-.006*mt[1]
    if obj>current+.00002:current=obj;start=mt;acc+=1
    else:f[i]=old
   else:f[i]=old
  else:f[i]=old
  if z%1100==0:print(n,'iter',z,'score',start[:2],'accepted',acc,'elapsed',round(time.monotonic()-t0,1),flush=True)
 report={'phrase':n,'Q4_STOI':original[0],'Q4_spec':original[1],'Q3_STOI':start[0],'Q3_spec':start[1],'accepted':acc,'iterations':iterations,'runtime':round(time.monotonic()-t0,1)}
 np.savez(ROOT/n/'q3_candidate.npz',frames=f,durations=d)
 print('RESULT',report,flush=True)
 return report

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--phrases',nargs='+',default=['chego','otvechaesh','vinni']);p.add_argument('--iters',type=int,default=1500)
 a=p.parse_args();reports=[run(n,a.iters) for n in a.phrases]
 (ROOT/'coeff_scale_results.json').write_text(json.dumps(reports,indent=2))

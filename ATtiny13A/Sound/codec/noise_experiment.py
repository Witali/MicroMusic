#!/usr/bin/env python3
"""Bit-exact-style model of unvoiced/noise excitation variants using existing 2 mode bits.
Offline exploratory test. Selected variant must be implemented and verified on AVR before release.
"""
import sys,time,json
import numpy as np,soundfile as sf
from numba import njit

from model import mul_q4
from quality import Compare
from hq4_codec import unpack
from optimize_hq4 import SRC,ROOT

@njit
def synth_noise(frames,durations):
 n=int(np.sum(durations));out=np.empty(n,np.uint8)
 state=np.zeros(8,np.int32);k=np.zeros(8,np.int32)
 seed=0xa7;period=0;gain=0;phase=1;mode=0;fi=0;next_t=int(durations[0])-1
 oldsign=1
 for t in range(n):
  if t==0 or t==next_t:
   if t!=0:
    fi+=1
    if fi>=len(frames):fi=0
    next_t+=int(durations[fi])
   period=int(frames[fi,0]);gain=int(frames[fi,1])&15;mode=(int(frames[fi,1])>>4)&3
   phase=period
   for j in range(4):
    data=int(frames[fi,2+j]);k[2*j]=(data&15)-8;k[2*j+1]=(data>>4)-8
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
   sg=-1 if seed&1 else 1
   if mode==0: ex=(sg*gain)&255
   elif mode==1:ex=((sg+oldsign)*gain)&255
   elif mode==2:ex=((sg-oldsign)*gain)&255
   else:ex=(sg*gain//2)&255
   oldsign=sg
  for j in range(7,-1,-1):
   old=state[j];coef=k[j];ex=(ex-mul_q4(old,coef))&255
   if j<7:state[j+1]=(old+mul_q4(ex,coef))&255
  state[0]=ex;out[t]=(ex+128)&255
 return out

def train(name):
 f,d,_=unpack((SRC/name/'speech.hq').read_bytes()+b'\xff')
 ref,sr=sf.read(str(ROOT/'references')+'/'+name+'/original.wav');cp=Compare(ref)
 # Set all unvoiced modes to 0 so the decoder produces the exact reference result.
 for i in range(len(f)):
  if f[i,0]==0:f[i,1]&=15
 old=cp.scores(synth_noise(f,d));best=old;accepted=0
 for passes in range(3):
  for i in range(len(f)):
   if f[i,0]!=0:continue
   row=f[i].copy();chosen=None;metbest=best
   for m in [0,1,2,3]:
    f[i,1]=(int(row[1])&15)|(m<<4)
    y=synth_noise(f,d)
    if np.any(np.abs(np.diff(y.astype(np.int16)))>=48):continue
    st,spec,clicks=cp.scores(y)
    if st-0.005*spec>metbest[0]-0.005*metbest[1]+.00003 and spec<=old[1]+.03:
     metbest=(st,spec,clicks);chosen=f[i].copy()
   f[i]=chosen if chosen is not None else row
   if chosen is not None:accepted+=1;best=metbest
 print(name,'baseline',old,'best',best,'accepted',accepted, 'modes',np.bincount((f[f[:,0]==0,1]>>4)&3,minlength=4),flush=True)
 np.savez(ROOT/name/'noise_frames.npz',frames=f,durations=d)
 return {'phrase':name,'baseline':old,'best':best,'accepted':accepted}

if __name__=='__main__':
 reports=[train(n) for n in ['chego','otvechaesh','vinni']]
 (ROOT/'noise_experiment_results.json').write_text(json.dumps(reports,indent=2))

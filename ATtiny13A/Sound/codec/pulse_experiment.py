#!/usr/bin/env python3
"""Compare inexpensive glottal-excitation variants in the exact 8-bit LPC model.
Modes use existing two bits in every speech frame. Evaluation uses original PCM.
"""
import sys,argparse,time,json
import numpy as np,soundfile as sf
from numba import njit

from model import mul_q4
from quality import Compare
from hq4_codec import unpack,encode
from optimize_hq4 import ROOT,SRC

@njit
def synth(frames,durs,pulses):
 n=int(np.sum(durs));out=np.empty(n,np.uint8)
 state=np.zeros(8,np.int32);k=np.zeros(8,np.int32)
 seed=0xa7;period=0;gain=0;phase=1;mode=0;fi=0;next_t=int(durs[0])-1
 for t in range(n):
  if t==0 or t==next_t:
   if t!=0:
    fi+=1
    if fi>=len(frames):fi=0
    next_t+=int(durs[fi])
   period=int(frames[fi,0]);gain=int(frames[fi,1])&15;mode=(int(frames[fi,1])>>4)&3
   phase=period
   for j in range(4):
    data=int(frames[fi,2+j]);k[2*j]=(data&15)-8;k[2*j+1]=(data>>4)-8
  ex=0
  if period:
   phase=(phase-1)&255
   if phase==0:
    phase=period
    ex=(int(pulses[mode,0])*gain)&255
   else:
    lag=period-phase
    if 1<=lag<=3:ex=(int(pulses[mode,lag])*gain)&255
  else:
   low=seed&1;seed=seed>>1
   if low:seed^=0xb8
   ex=((-gain if seed&1 else gain))&255
  for j in range(7,-1,-1):
   old=state[j];coef=k[j];ex=(ex-mul_q4(old,coef))&255
   if j<7:state[j+1]=(old+mul_q4(ex,coef))&255
  state[0]=ex;out[t]=(ex+128)&255
 return out

def profiles(first,sec0,sec1,th0,th1,fourth):
 return np.array([[first,sec0,th0,fourth],[first,sec1,th0,fourth],[first,sec0,th1,fourth],[first,sec1,th1,fourth]],np.int8)

PROFILES={
 'original':profiles(2,3,2,2,1,-1),
 'lower_mid':profiles(2,2,1,2,1,-1),
 'late_zero':profiles(2,3,2,2,0,-1),
 'lower_zero':profiles(2,2,1,2,0,-1),
 'late_slope':profiles(2,3,2,1,0,-1),
 'lower_late':profiles(2,2,1,1,0,-1),
 'tail_stronger':profiles(2,3,2,2,1,-2),
 'tail_strong_low':profiles(2,2,1,2,1,-2),
 'soft_first':profiles(1,2,1,2,1,-1),
 'strong_first':profiles(3,2,1,2,1,-1),
 'soft_second':profiles(2,2,1,1,0,0),
 'all_positive':profiles(2,3,2,2,1,0),
}

def tune(name,profile,passes=1):
 f,d,_=unpack((SRC/name/'speech.hq').read_bytes()+b'\xff')
 ref,sr=sf.read(str(ROOT/'references')+'/'+name+'/original.wav'); comp=Compare(ref)
 starting=comp.scores(synth(f,d,profile));best=(starting[0]-0.004*starting[1],starting); accepted=0
 # simple greedy mode-only search, no changes to duration, pitch or K.
 for it in range(passes):
  for i in range(len(f)):
   row=f[i].copy();choose=None
   for m in range(4):
    f[i,1]=(int(row[1])&15)|(m<<4)
    if int(row[1])==int(f[i,1]):continue
    y=synth(f,d,profile)
    if np.any(np.abs(np.diff(y.astype(np.int16)))>=48):continue
    met=comp.scores(y)
    score=met[0]-0.004*met[1]
    if score>best[0]+.00001:
     best=score,met;choose=f[i].copy()
   f[i]=choose if choose is not None else row
   if choose is not None:accepted+=1
 last=comp.scores(synth(f,d,profile))
 return starting,last,f,accepted

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--names',nargs='+',default=['chego','otvechaesh','vinni']);p.add_argument('--profiles',nargs='+',default=list(PROFILES));a=p.parse_args()
 rows=[]
 for n in a.names:
  for pname in a.profiles:
   t0=time.monotonic();initial,final,f,accepted=tune(n,PROFILES[pname])
   row={'phrase':n,'profile':pname,'initial_stoi':initial[0],'final_stoi':final[0],'spectral_error':final[1],'clicks':final[2],'accepted':accepted,'seconds':round(time.monotonic()-t0,2)}
   rows.append(row);print(n,pname,'STOI',round(final[0],6),'spec',round(final[1],4),'clicks',final[2],'accepted',accepted,'time',row['seconds'],flush=True)
 with (ROOT/'pulse_experiment_results.json').open('w') as out:json.dump(rows,out,indent=2)

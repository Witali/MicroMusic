"""Search primitive 8-bit maximal-length LFSR taps & seeds without firmware-size growth.
Requires only patching two LDI immediates in firmware.S; no new parser or data bytes.
"""
import json,argparse
from pathlib import Path
import numpy as np,soundfile as sf
from numba import njit
from quality import Compare
ROOT=Path(__file__).parent
TAPS=[0x8e,0x95,0x96,0xa6,0xaf,0xb1,0xb2,0xb4,0xb8,0xc3,0xc6,0xd4,0xe1,0xe7,0xf3,0xfa]
SEEDS=[0x01,0x17,0x3b,0x57,0xa7,0xd5,0xfe]
@njit
def s8(v):return ((v+128)&255)-128
@njit
def mul_q4(x,k):
 a=s8(x)
 if k<0:a=s8(-a)
 return ((a*abs(k))>>4)&255
@njit
def decode_noise(frames,durations,tap,seed_init):
 n=int(np.sum(durations));out=np.empty(n,np.uint8)
 state=np.zeros(8,np.int32);k=np.zeros(8,np.int32);seed=seed_init;period=0;gain=0;phase=1;mode=0
 fi=0;next_t=int(durations[0])-1
 for t in range(n):
  if t==0 or t==next_t:
   if t!=0:
    fi+=1
    if fi>=len(frames):fi=0
    next_t+=int(durations[fi])
   period=int(frames[fi,0]);gain=int(frames[fi,1])&15;mode=(int(frames[fi,1])>>4)&3;phase=period
   for j in range(4):
    z=int(frames[fi,2+j]);k[j*2]=(z&15)-8;k[j*2+1]=(z>>4)-8
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
   low=seed&1;seed=seed>>1
   if low:seed=seed^tap
   ex=((-gain if (seed&1) else gain))&255
  for j in range(7,-1,-1):
   old=state[j];coef=k[j];ex=(ex-mul_q4(old,coef))&255
   if j<7:state[j+1]=(old+mul_q4(ex,coef))&255
  state[0]=ex;out[t]=(ex+128)&255
 return out

def search(name):
 x=np.load(ROOT/'samples'/name/'trained.npz');f=x['frames'];d=x['durations'];ref,sr=sf.read(ROOT/'references'/name/'original.wav');assert sr==7500
 cp=Compare(ref)
 baseline=cp.scores(decode_noise(f,d,0xb8,0xa7))
 all=[]
 for tap in TAPS:
  for seed in SEEDS:
   y=decode_noise(f,d,tap,seed)
   st,sp,clk=cp.scores(y)
   all.append({'tap':tap,'seed':seed,'stoi':st,'spec':sp,'clicks':clk})
 valid=[v for v in all if v['clicks']==0 and v['spec']<=baseline[1]+0.025]
 winner=max(valid,key=lambda a:a['stoi']-0.005*a['spec'])
 bscore=baseline[0]-0.005*baseline[1]
 if winner['stoi']-0.005*winner['spec']<bscore:winner={'tap':0xb8,'seed':0xa7,'stoi':baseline[0],'spec':baseline[1],'clicks':baseline[2]}
 report={'baseline':baseline,'best':winner,'top5':sorted(valid,key=lambda a:a['stoi'],reverse=True)[:5]}
 (ROOT/'samples'/name/'noise_search.json').write_text(json.dumps(report,indent=2))
 print(name,report,flush=True)
 return winner
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--voice',choices=['chego','otvechaesh','vinni'],required=True);args=p.parse_args();search(args.voice)

"""MicroMusic pitch-code and glottal-excitation ablation tests. A codec simulation, not hardware claim."""
from pathlib import Path
import numpy as np
from numba import njit
import soundfile as sf
from pystoi import stoi
from scipy.signal import stft
from spectral_objective import evaluate,x,FS
P=Path(__file__).resolve().parent
z=np.load(P/'best_parameters.npz');K=z['K'].astype(np.int64);PP=z['P'].astype(np.int64);E=z['E'].astype(np.int64)
@njit(cache=True)
def synth_chirp(K,PP,E,length,chirp,tap_smooth=0):
 n=len(PP);out=np.zeros(length,dtype=np.int64)
 st=np.zeros(7,dtype=np.int64)
 phase=1;seed=0xa7
 lastfi=-1;prv=0
 for t in range(length):
  fi=((t+1)//256)%n
  if fi!=lastfi:
   if E[fi]==0: st[:]=0
   lastfi=fi
  p=PP[fi];g=E[fi]
  if p:
   phase=(phase-1)&255
   if phase==0:phase=p;ii=0;valid=True
   else:ii=(p-phase)&255;valid=(ii!=0)
   ex=int(chirp[ii])*g if valid and ii<len(chirp) else 0
  else:
   seed=(seed>>1)^(0xb8 if seed&1 else 0)
   ex=-g if seed&1 else g
  v=ex
  for stage in range(6,-1,-1):
   value=(int(K[fi,stage])*st[stage])>>4
   v=((v-value+128)&255)-128
   if stage<6:
    value2=(int(K[fi,stage])*v)>>4
    st[stage+1]=((st[stage]+value2+128)&255)-128
  st[0]=v
  if tap_smooth==1:
   out[t]=(v>>1)+(prv>>1)
  elif tap_smooth==2:
   out[t]=((v*3+prv)>>2)
  elif tap_smooth==3:
   out[t]=(v+(prv*3))>>2
  else:out[t]=v
  prv=v
 return out

if __name__=='__main__':
 source,_=sf.read('source_original_7500.wav');src=source[:len(x)]
 chirps={
 'v4 [5,3,0,-2]':[5,3,0,-2],
 'A [3,3,1,-1]':[3,3,1,-1],
 'B [2,3,2,-1]':[2,3,2,-1],
 'C [1,3,3,1,-1]':[1,3,3,1,-1],
 'D [1,2,3,2,0,-1]':[1,2,3,2,0,-1],
 'E [1,2,3,3,2,0,-1]':[1,2,3,3,2,0,-1],
 'F [1,2,3,4,2,0,-1,-1]':[1,2,3,4,2,0,-1,-1],
 'G [0,1,2,3,3,2,0,-1,-1]':[0,1,2,3,3,2,0,-1,-1],
 'H [2,3,3,1,-1,-1]':[2,3,3,1,-1,-1],
 'I [1,2,4,3,1,-1,-1]':[1,2,4,3,1,-1,-1],
 }
 ans=[]
 for name,cs in chirps.items():
  for filt in [0,1,2,3]:
   y=synth_chirp(K,PP,E,len(x),np.array(cs,dtype=np.int64),filt)
   score=evaluate(y/128,True)
   d=np.abs(np.diff(y))
   jump=float(np.mean(np.maximum(0,d-30)**2))
   print(f'{name:26} smooth={filt} stoi={score["stoi"]:.3f} mel={score["spectral_mel_distance"]:.3f} loud={score["loudness_envelope_error"]:.3f} maxstep={max(d):3d} >=60={sum(d>=60):3d} click_metric={jump:.1f}',flush=True)
   ans.append((name,cs,filt,score['stoi'],score['spectral_mel_distance'],int(max(d)),int(sum(d>=60)),jump))
 np.savez('all_chirp_results.npz',ans=np.array(ans,dtype=object))

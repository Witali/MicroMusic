from pathlib import Path
import numpy as np
from numba import njit
from optimize_v3 import P,x,FS,H,N,rms,corrs,lags,levinson,metrics,lsd
@njit(cache=True)
def synth(K,pitch,energy,length,shift,chirp):
 state=np.zeros(7,dtype=np.int64);seed=0xa7;count=1;y=np.zeros(N*256)
 for t in range(len(y)):
  fi=t//256;k=K[fi];pp=pitch[fi];amp=energy[fi]
  if pp:
   count=(count-1)&255
   if count==0:count=pp
   dt=(pp-count)&255
   if dt<4:exc=amp*chirp[dt]
   else:exc=0
  else:
   seed=(seed>>1)^(0xb8 if (seed&1) else 0)
   exc=-amp if (seed&1) else amp
  v=exc
  for stage in range(6,-1,-1):
   w=(k[stage]*state[stage])>>shift
   v=((v-w+128)&255)-128
   if stage>0:
    w2=(k[stage]*v)>>shift
    state[stage]=((state[stage-1]+w2+128)&255)-128
  state[0]=v;y[t]=v/128.
 return y[:length]
RAW=np.array([levinson(np.pad(x[f*H:(f+1)*H],(0, max(0,H-len(x[f*H:(f+1)*H])))))[0] for f in range(N)])
CHIRP=np.array([5,3,0,-2],dtype=np.int64)
if __name__=='__main__':
 rows=[]
 for shift in [3,4,5]:
  for alpha in [.20,.3,.4,.5,.6,.75,.9,1.,1.2,1.5,2.]:
   K=np.clip(np.rint(RAW*(2**shift)*alpha),-7,7).astype(np.int64)
   for th in [.25,.45,.6]:
    pi=np.where((corrs>th)&(rms>.01),lags,0).astype(np.int64)
    for fac in [15,30,60,100]:
     E=np.clip(np.rint(rms*fac),0,15).astype(np.int64);E[rms<.005]=0;pi[E==0]=0
     yy=synth(K,pi,E,len(x),shift,CHIRP)
     s,d=metrics(yy)
     # include speaker formant preservation by weighing LSD besides STOI
     rows.append((s,d,shift,alpha,th,fac,np.sqrt((yy*yy).mean()),K,pi,E))
  print('shift',shift, 'best STOI', [(round(z[0],3),round(z[1],2),z[3:6]) for z in sorted([v for v in rows if v[2]==shift],reverse=True)[:5]], flush=True)
 rows.sort(key=lambda v:v[0],reverse=True)
 for z in rows[:25]:print('TOP',tuple(round(float(q),3) for q in z[:7]),flush=True)
 np.savez(P/'v3_tune_best.npz',K=rows[0][7],pitch=rows[0][8],energy=rows[0][9],shift=rows[0][2])

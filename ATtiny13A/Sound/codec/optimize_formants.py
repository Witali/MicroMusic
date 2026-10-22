import numpy as np
from tune import synth,RAW,CHIRP
from optimize_v3 import P,FS,x,H,N,metrics,corrs,lags,rms
threshold=.25;pitch=np.where((corrs>threshold)&(rms>.01),lags,0).astype(np.int64)
energy=np.clip(np.rint(rms*30),0,15).astype(np.int64);energy[rms<.005]=0;pitch[energy==0]=0
SHIFT=4
scales=np.full(7,.4)
def quality(sc, ee=energy,pi=pitch, verbose=False):
    K=np.clip(np.rint(RAW*(2**SHIFT)*np.asarray(sc)[None,:]),-7,7).astype(np.int64)
    yy=synth(K,pi,ee,len(x),SHIFT,CHIRP)
    s,d=metrics(yy)
    quality=s-.020*d # combined objective: intelligibility and spectral shape
    return quality, s, d, K, yy
best=quality(scales)
print('begin',scales,best[:3],flush=True)
for epoch in range(3):
  for col in range(7):
    cand=[]
    for candidate in [0.16,0.22,0.28,0.34,0.4,0.46,0.52,0.60,0.7,0.82,1.0]:
      cur=scales.copy();cur[col]=candidate
      z=quality(cur);cand.append((z[0],candidate,z[:3]))
    cand.sort(reverse=True)
    scales[col]=cand[0][1]
    best=quality(scales)
    print('epoch',epoch,'coefficient',col,'scales',np.round(scales,2),'metric',np.round(best[:3],4),flush=True)
for threshold in [.15,.2,.25,.30,.35,.45,.55,.65]:
 for eng in [15,22,30,42,60,90]:
  pi=np.where((corrs>threshold)&(rms>.01),lags,0).astype(np.int64)
  ee=np.clip(np.rint(rms*eng),0,15).astype(np.int64);ee[rms<.005]=0;pi[ee==0]=0
  result=quality(scales,ee,pi)
  if result[0]>best[0]:
    best=result;bp=pi;be=ee
    print('BETTER',threshold,eng,np.round(best[:3],4),flush=True)
# if baseline remains higher use baseline pitch and energy
if 'bp' not in locals():bp=pitch;be=energy
print('FINISHED',np.round(scales,3),np.round(best[:3],4),flush=True)
np.savez(P/'v3_formant_best.npz',K=best[3], pitch=bp, energy=be, shift=SHIFT, scales=scales, stoi=best[1],dist=best[2])

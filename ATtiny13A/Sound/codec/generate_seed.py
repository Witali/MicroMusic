#!/usr/bin/env python3
"""Create first 7-stage quantized TinyLPC parameters for any prepared voice WAV.
Does not promise the generated parameters will fit 1024B; firmware builder checks.
"""
import argparse
from pathlib import Path
import numpy as np
from scipy.signal import correlate
from perceptual import load_wav,FS
H=256

def refl_coeff(frame,order=7):
    x=np.asarray(frame).copy()
    x=(x-x.mean())*np.hamming(len(x))
    r=np.array([float(x[k:]@x[:len(x)-k]) for k in range(order+1)])
    r[0]=r[0]*1.10+1e-7
    a=np.r_[1.0,np.zeros(order)];err=max(r[0],1e-9);coef=[]
    for k in range(1,order+1):
        v=np.clip(-(r[k]+sum(a[j]*r[k-j] for j in range(1,k)))/max(err,1e-9),-.94,.94)
        a0=a.copy()
        for j in range(1,k):a[j]=a0[j]+v*a0[k-j]
        a[k]=v;err*=max(.1,1-v*v)
        coef.append(v)
    return np.asarray(coef)

def find_period(x,idx):
    st=idx*H-128
    seg=np.pad(x,(max(0,-st),max(0,st+H+128-len(x))))[max(0,st):max(0,st)+H+256]
    if len(seg)<400:return 0,0
    seg=seg-seg.mean();peak=max(abs(seg).max(),1e-8)
    seg=np.sign(seg)*np.maximum(0,abs(seg)-peak*.20)
    scores=[]
    for lag in range(16,128):
        a=seg[lag:];b=seg[:-lag]
        cc=np.dot(a,b)/(np.sqrt(np.dot(a,a)*np.dot(b,b))+1e-8)
        scores.append(cc)
    best=max(scores)
    if best<.48:return 0,best
    # Pick the shortest sufficiently strong harmonic-related period.
    candidates=[i+16 for i,c in enumerate(scores) if c>=max(.48,best*.86)]
    return min(candidates) if candidates else 0,best

def generate(source,output):
    x=load_wav(source)
    frames=int(np.ceil(len(x)/H))
    x=np.pad(x,(0,frames*H-len(x)))
    K=[];P=[];E=[]
    for i in range(frames):
        seg=x[i*H:(i+1)*H]
        rms=float(np.sqrt(np.mean(seg**2)))
        pitch,corr=find_period(x,i)
        audible=rms>.012
        energy=int(np.clip(np.rint(rms*(60 if not pitch else 45)),1,15)) if audible else 0
        if not energy:pitch=0
        K.append(np.clip(np.rint(7.5*refl_coeff(seg)),-7,7).astype('int64'))
        P.append(pitch);E.append(energy)
    out=Path(output);out.parent.mkdir(parents=True,exist_ok=True)
    np.savez(out,K=np.asarray(K,dtype='int64'),P=np.asarray(P,dtype='int64'),E=np.asarray(E,dtype='int64'))
    print(f'Initial LPC fit {frames} frames / {len(x)/FS:.3f}s / {int(np.count_nonzero(E))} non-silent frames -> {out}')
    return out

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();generate(a.source,a.out)

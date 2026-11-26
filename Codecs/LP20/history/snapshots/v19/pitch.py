#!/usr/bin/env python3
"""Adaptive period tracking, no speaker ID / no trained pitch model.
All pitch analysis is encoder-side. Fractional lag via linear interpolation.
The loss measures non-periodic reconstruction error in confidently voiced spans.
"""
import numpy as np
from scipy.signal import butter,sosfiltfilt
from scipy.ndimage import median_filter,gaussian_filter1d
from numpy.lib.stride_tricks import sliding_window_view
FS=7812.5

def track(x,fs=FS,fmin=50.,fmax=650.):
 x=np.asarray(x,dtype=float); n=len(x); hop=round(fs*.01); half=round(fs*.026)
 if n<2*half:raise ValueError('Need at least 52 ms')
 # Remove sub-pitch drift, reduce impact of sharp high-frequency consonants.
 u=sosfiltfilt(butter(2,[40,min(2200,fs*.44)],fs=fs,btype='bandpass',output='sos'),x)
 centers=np.arange(0,n,hop); pad=np.pad(u,(half,half),mode='reflect');frames=sliding_window_view(pad,2*half+1)[centers].copy(); frames-=frames.mean(axis=1,keepdims=True)
 lmin=max(3,int(np.floor(fs/fmax)));lmax=min(half-8,int(np.ceil(fs/fmin)))
 lags=np.arange(lmin-1,lmax+2); ac=np.empty((len(frames),len(lags)))
 for j,l in enumerate(lags):
  a=frames[:,:-l];b=frames[:,l:];ac[:,j]=np.sum(a*b,axis=1)/(np.sqrt(np.sum(a*a,axis=1)*np.sum(b*b,axis=1))+1e-15)
 power=np.mean(frames**2,axis=1); active=power>max(1e-20,power.max()*10**(-38/10));
 peaks=(ac[:,1:-1]>=ac[:,:-2])&(ac[:,1:-1]>ac[:,2:]); candidates=lags[1:-1]; v=ac[:,1:-1];
 # Prefer earliest strong local maximum; avoid selecting octave multiples.
 # For continuity use previous confident lag only as a soft prior, reset in unvoiced spans.
 lag=np.zeros(len(frames)); conf=np.zeros(len(frames)); prev=None
 for i in range(len(frames)):
  best=float(v[i].max()); js=np.flatnonzero(peaks[i]&(v[i]>=max(.58,best-.075)))
  if not active[i] or not len(js):prev=None;continue
  rank=v[i,js]-.065*np.log2(candidates[js]/lmin)
  if prev is not None:rank-=.085*np.minimum(2.,abs(np.log2(candidates[js]/prev)))
  k=int(js[np.argmax(rank)])+1; a,b,c=ac[i,k-1:k+2];den=a-2*b+c;delta=np.clip(.5*(a-c)/den,-.5,.5) if abs(den)>1e-12 else 0.
  lag[i]=lags[k]+delta;conf[i]=b;prev=lag[i]
 # Reject isolated one-frame estimates. Interpolate only within voiced runs.
 voiced=lag>0; isolated=voiced&~np.r_[False,voiced[:-1]]&~np.r_[voiced[1:],False];lag[isolated]=0;conf[isolated]=0
 w=np.clip((conf-.60)/.30,0,1)**1.3;w*=lag>0
 p=np.arange(n); use=np.flatnonzero(lag>0)
 period=np.interp(p,centers[use],lag[use]) if len(use) else np.full(n,fs/140.)
 weight=np.interp(p,centers,w); weight*=np.interp(p,centers,(lag>0).astype(float));
 # Do not apply past-lag loss across non-voiced boundaries.
 back=p-period;safe=np.clip(back,0,n-1);i0=np.floor(safe).astype(np.int32);i1=np.minimum(i0+1,n-1);frac=safe-i0
 weight*=np.interp(safe,p,weight);weight[back<0]=0
 return dict(centers=centers,lag=lag,confidence=conf,active=active,period=period,weight=weight,i0=i0,i1=i1,frac=frac,fs=fs)

def pred(p,e):return (1-p['frac'])*e[p['i0']]+p['frac']*e[p['i1']]

def cost(p,e,gradient=False):
 e=np.asarray(e);a=e-pred(p,e);w=p['weight'];s=float(np.dot(w,a*a));
 if not gradient:return s
 q=2*w*a;g=q-np.bincount(p['i0'],q*(1-p['frac']),minlength=len(e))-np.bincount(p['i1'],q*p['frac'],minlength=len(e));return s,g

def summary(p):
 use=p['lag']>0;hz=p['fs']/p['lag'][use];return dict(frames=len(use),voiced_frames=int(use.sum()),active_frames=int(p['active'].sum()),f0_p10=float(np.percentile(hz,10)) if len(hz) else None,f0_median=float(np.median(hz)) if len(hz) else None,f0_p90=float(np.percentile(hz,90)) if len(hz) else None,mean_confidence=float(p['confidence'][use].mean()) if len(hz) else None)

if __name__=='__main__':
 # Numerical test of lag-loss gradient; pitch test with known tones, not speech ground truth.
 rng=np.random.default_rng(19);n=7812;t=np.arange(n)/FS
 for hz in [65,110,220,420,600]:
  p=track(np.sin(2*np.pi*hz*t)+.35*np.sin(4*np.pi*hz*t));s=summary(p);assert abs(s['f0_median']/hz-1)<.02,(hz,s);print(hz,s)
 p=track(np.sin(2*np.pi*120*t));e=rng.normal(size=n);d=rng.normal(size=n);v,g=cost(p,e,True);eps=1e-5;num=(cost(p,e+eps*d)-cost(p,e-eps*d))/(2*eps);assert np.isclose(num,g@d,rtol=1e-5,atol=1e-5);print('gradient OK')

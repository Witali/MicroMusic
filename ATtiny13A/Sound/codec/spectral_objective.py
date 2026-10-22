from pathlib import Path
import numpy as np,soundfile as sf
from scipy.signal import stft
from scipy.ndimage import gaussian_filter1d
from tune import synth,CHIRP,RAW
from optimize_v3 import metrics,FS,H,N,x

FMIN,FMAX=125,3400
RANGE=None

def spectral_mel(signal):
    # Compute per-frame spectral envelopes using 512-sample FFT windows, step 128
    f,t,z=stft(signal,FS,nperseg=512,noverlap=384,boundary='zeros',padded=True)
    mag=np.abs(z)+1e-6
    # mel filter edges 160..3300, 24 bands
    edges=700*(np.exp(np.linspace(np.log1p(130/700),np.log1p(3500/700),27))-1)
    band=[]
    for low,mid,high in zip(edges[:-2],edges[1:-1],edges[2:]):
       w=np.maximum(0,np.minimum((f-low)/(mid-low),(high-f)/(high-mid)))
       w/=max(1e-5,w.sum())
       band.append((w[:,None]*mag).sum(axis=0))
    band=np.array(band)
    return t,band

Ts,REF=spectral_mel(x)
ENERGY=(REF**2).sum(axis=0)**.5
WEIGHTS=(ENERGY/np.max(ENERGY))**.65
WEIGHTS[WEIGHTS<.07]=0
WEIGHTS=WEIGHTS/(WEIGHTS.sum()+1e-9)
REF_LOG=np.log(np.maximum(REF,1e-6))
REF_NORM=REF_LOG-REF_LOG.mean(axis=0)


def evaluate(y,full=False):
    t, bands=spectral_mel(y)
    n=min(REF.shape[1],bands.shape[1]);b=bands[:,:n]
    log=np.log(np.maximum(b,1e-6));norm=log-log.mean(axis=0)
    diff=(norm-REF_NORM[:,:n])
    err=float(np.sum((np.mean(np.sqrt(diff**2+.05**2),axis=0))*WEIGHTS[:n]) )
    e=np.sqrt(np.mean(b*b,axis=0)); er=np.sqrt(np.mean(REF[:,:n]**2,axis=0))
    valid=WEIGHTS[:n]>.0005
    scale=np.sum(WEIGHTS[:n]*np.log(er[valid].mean()/max(1e-9,e[valid].mean()))) if valid.any() else 0
    level=np.log(np.maximum(e,1e-6))-np.log(np.maximum(er,1e-6))
    level-=np.sum(level*WEIGHTS[:n])
    lev=float(np.sum(np.abs(level)*WEIGHTS[:n]))
    # response spectral centroid (useful for voicedness and formants)
    if not full:return err,lev
    st,lsd=metrics(y)
    return {'spectral_mel_distance':err,'loudness_envelope_error':lev,'stoi':st,'old_lsd':lsd}

if __name__=='__main__':
    from time import monotonic
    z=np.load('v3_formant_best.npz'); k,p,e=z['K'],z['pitch'],z['energy']
    t=monotonic();y=synth(k,p,e,len(x),4,CHIRP)
    print('V3',evaluate(y,True),'time',monotonic()-t)
    z=np.load('pitch_fit.npz');y=synth(z['K'],z['pitch'],z['energy'],len(x),4,CHIRP)
    print('new pitch',evaluate(y,True),'time',monotonic()-t)
    for shift in [3,4]:
      for scale in [.4,.65,.85,1.1,1.4]:
        k=np.clip(np.rint(RAW*(2**shift)*scale),-7,7).astype(np.int64)
        for ea in [1,.5,.25]:
          E=np.rint(e*ea).astype(np.int64);E[(e>0)&(E==0)]=1
          y=synth(k,p,E,len(x),shift,CHIRP)
          print(shift,scale,ea,tuple(round(q,3) for q in evaluate(y)),round(y.std(),4),flush=True)

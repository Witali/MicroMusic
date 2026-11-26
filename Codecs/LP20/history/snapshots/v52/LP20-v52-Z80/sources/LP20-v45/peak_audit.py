#!/usr/bin/env python3
"""LP20 peak audit. Reuses v36/v42 common 3.5 kHz band, DC removal, one global
integer delay and gain fit, 10 ms end exclusion. Peak metrics normalize to the
same clip's reference peak (not to each reconstruction)."""
from pathlib import Path
import os,csv,sys,json
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter,sosfiltfilt,correlate
FS=48000

def load(p):
 f,x=wavfile.read(p);assert f==FS and x.ndim==1 and x.dtype==np.int16
 return x.astype(float)/32768

def filt(x):return sosfiltfilt(butter(5,3500,fs=FS,output='sos'),x)
def align(x,y):
 y=y-y.mean();n=len(x);assert len(y)==n;c=correlate(y,x,method='fft');lag=int(np.argmax(c[n-1-16:n+16])-16);a=x[max(0,-lag):n-max(0,lag)];b=y[max(0,lag):n-max(0,-lag)];g=float(np.dot(a,b)/np.dot(b,b));z=np.zeros(n);z[max(0,-lag):n-max(0,lag)]=g*b;return z,lag,g

def metrics(x,y):
 z,lag,g=align(x,y);e=(z-x)[480:-480];r=x[480:-480];a=np.abs(e);peak=np.max(np.abs(r));p99,p999,p9999=np.percentile(a,[99,99.9,99.99]);mx=a.max();N=960;n=len(r)//N;rr=r[:n*N].reshape(n,N);ee=e[:n*N].reshape(n,N);active=np.mean(rr**2,axis=1)>=np.max(np.mean(rr**2,axis=1))*10**(-3.5);bpk=np.max(abs(ee),axis=1)[active];at=int(np.argmax(a))+480
 return dict(snr_db=10*np.log10(np.dot(r,r)/np.dot(e,e)),reference_peak=peak,rmse=np.sqrt(np.mean(e**2)),peak_error_pct=100*mx/peak,p99_pct=100*p99/peak,p999_pct=100*p999/peak,p9999_pct=100*p9999/peak,peak_snr_db=20*np.log10(peak/mx),peak_fullscale_pct=100*mx,peak_time_s=at/FS,active_block_peak_p95_pct=100*np.percentile(bpk,95)/peak,fraction_above_5pct=100*np.mean(a>peak*.05),delay_samples=lag,gain=g)

def main():
 base=Path(sys.argv[1] if len(sys.argv)>1 else '/mnt/data');out=Path(__file__).parent;rows=[]
 for clip in ('first','second'):
  x=filt(load(base/'LP20-v42/release'/clip/'reference.wav'));x-=x.mean()
  paths={'v25 Quality':base/f'LP20-v25-{clip}-PWM-exact.wav','v39 Strict8':base/'LP20-v42/release'/clip/'v39.wav','v41 Compact':base/'LP20-v41-sample-hybrid'/f'{clip}-packed256'/'morph.wav','v42 Quality':base/f'LP20-v42-Quality-{clip}.wav','v42 LowNoise':base/f'LP20-v42-LowNoise-{clip}.wav'}
  for label,p in paths.items():
   if not p.exists():continue
   m=metrics(x,filt(load(p)));rows.append(dict(clip=clip,profile=label,**m));print(clip,label,{k:round(m[k],4) for k in ('snr_db','peak_error_pct','p999_pct','active_block_peak_p95_pct','peak_time_s')},flush=True)
 with open(out/'peak_comparison.csv','w') as f:
  w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
if __name__=='__main__':main()

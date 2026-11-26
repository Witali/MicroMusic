#!/usr/bin/env python3
"""Nonlinear PWM grid experiment. Unchanged LP4V bitstream, PC-only simulation."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import sys,json,csv,itertools
from pathlib import Path
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
sys.path.insert(0,str(BASE/'LP20-v45'))
from adaptive45 import decode_v
from rd44 import render,metrics
from peak_audit import filt,align,metrics as peak_metrics
import numpy as np
from scipy.signal import butter,sosfiltfilt,resample_poly
from scipy.io import wavfile
FS=7812.5; W=[35,100,135,145,150,160,170,175,185,220,285];CENTER=1280
H7=butter(5,7000,fs=48000,output='sos')
def load(c):
 p=BASE/'LP20-v44/input'/c;q=BASE/'LP20-v49'/c;d=dict(np.load(p/'model.npz'));m=json.loads((p/'decoder.json').read_text());r=wavfile.read(p/'reference.wav')[1];z,_,_=decode_v(q/'Quality.lp4v',(q/'book.bin').read_bytes());return d,m,r,z

def library():
 a=np.array(list(itertools.combinations_with_replacement(W,8)),np.int16);s=a.sum(1);var=np.sum((a-s[:,None]/8)**2,axis=1);out={}
 for t in np.unique(s[s>=CENTER]):
  ids=np.flatnonzero(s==t);b=list(map(int,a[ids[np.argmin(var[ids])]]));row=[];p=0
  for j in range(1,9):
   i=min(range(len(b)),key=lambda i:(abs(8*(p+b[i])-j*t),b[i]));v=b.pop(i);row.append(v);p+=v
  out[int(t)]=row;out[2560-int(t)]=[320-v for v in row]
 return dict(sorted(out.items()))
def select(lib,N,gamma,z=None,prior=.02):
 h=np.array([s-CENTER for s in lib if s>=CENTER]);a=h*128/1120.;K=(N+1)//2;sep=10 if N<=64 else 5
 if z is not None:
  v=np.arange(513)/4;hist=np.bincount(np.clip(np.rint(abs(z)*4).astype(int),0,512),minlength=513).astype(float);hist/=hist.sum();hist=(1-prior)*hist+prior/len(v);p=np.vstack([np.zeros(len(a)),np.cumsum(hist[:,None]*(v[:,None]-a[None,:])**2,axis=0)]);l=np.searchsorted(v,a);mid=np.searchsorted(v,(a[:,None]+a[None,:])/2,side='right');i,j=np.indices(mid.shape);C=p[mid,i]-p[l[i],i]+p[l[j],j]-p[mid,j];C[h[None,:]-h[:,None]<sep]=np.inf
 else:
  C=np.where(h[None,:]-h[:,None]>=sep,0.,np.inf);des=np.linspace(0,1,K)**gamma*h[-1]
 dp=np.full((K,len(h)),np.inf);pr=np.zeros(dp.shape,int);dp[0,0]=0
 for k in range(1,K):
  u=dp[k-1,:,None]+C;pr[k]=u.argmin(0);dp[k]=u.min(0)
  if z is None:dp[k]+=(h-des[k])**2
 j=len(h)-1;assert np.isfinite(dp[-1,j]);sel=[]
 for k in range(K-1,-1,-1):sel.append(h[j]);j=pr[k,j]
 h=np.array(sel[::-1]);return np.r_[CENTER-h[:0:-1],CENTER+h]
def lut(pats):
 lv=(pats.sum(1)-CENTER)*128/1120;v=np.arange(-512,512)/4;return np.argmin(abs(v[:,None]-lv[None,:]),axis=1).astype(np.int32)
def raw(z,pats):
 i=lut(pats)[np.clip(np.rint(z*4).astype(int)+512,0,1023)];w=pats[i];return (np.clip(w[:,:,None]-np.arange(4)*80,0,80).astype(np.float32)*2/80-1).ravel()
def render_raw(r,d):
 a=sosfiltfilt(H7,resample_poly(r,24,125))/.875*128/127;ref=resample_poly(d['target']/127,768,125);g=.98/max(abs(ref));a=a*g*min(1,.98/(max(abs(a))*g));return np.clip(np.rint(a*32767),-32768,32767).astype(np.int16)
def measure(r,w):
 a=filt(r.astype(float)/32768);a-=a.mean();y=filt(w.astype(float)/32768);m=peak_metrics(a,y);yy,_,_=align(a,y);e=yy-a;L=960;N=len(a)//L;af=a[:N*L].reshape(-1,L);ef=e[:N*L].reshape(-1,L);p=np.mean(af**2,axis=1);mask=p>=p.max()*10**(-3.5);quiet=mask&(p<=np.percentile(p[mask],33));m['quiet_snr_db']=10*np.log10(np.sum(af[quiet]**2)/np.sum(ef[quiet]**2));return m
def main(c):
 d,m,r,z=load(c);other='second' if c=='first' else 'first';_,_,_,zo=load(other);lib=library();assert len(lib)==353,len(lib)
 out=ROOT/c;out.mkdir(exist_ok=True);old={sum(v):v for v in m['patterns'].values()};g0=np.array(sorted(old));rows=[];variants=[('legacy-nearest',g0),('legacy-balanced',g0)]
 for gamma in (1,1.4,1.8,2.2,2.6):variants.append((f'59-power{gamma:g}',select(lib,59,gamma)))
 for u in (.005,.02,.12):variants.append((f'59-cross{u:g}',select(lib,59,1,zo,u)))
 for N in (97,129,255):
  for gamma in (1.,1.7):variants.append((f'{N}-power{gamma:g}',select(lib,N,gamma)))
 for N in (97,129):variants.append((f'{N}-cross',select(lib,N,1,zo,.02)))
 variants.append(('353-all',np.array(sorted(lib))))
 # Previous v49 renderer must match the saved WAV exactly.
 r0=render(z,d,m);assert np.array_equal(r0,wavfile.read(BASE/'LP20-v49'/c/'Quality.wav')[1]);v0=measure(r,r0);d0=measure(r,render(d['target'],d,m));rows.append(dict(clip=c,profile='v49',levels=len(g0),legacy_lut=True,**v0,direct_snr_db=d0['snr_db'],direct_peak_pct=d0['peak_error_pct'],direct_quiet_snr_db=d0['quiet_snr_db']));print(c,'baseline',v0['snr_db'],d0['snr_db'],flush=True)
 for name,g in variants:
  p=np.array([old[int(s)] if name!='legacy-balanced' and int(s) in old else lib[int(s)] for s in g],np.int16);j=lut(p);compat=len(g)<=64 and np.max(np.ptp(j.reshape(256,4),axis=1))<=1
  w=render_raw(raw(z,p),d);a=measure(r,w);b=measure(r,render_raw(raw(d['target'],p),d));row=dict(clip=c,profile=name,levels=len(g),legacy_lut=bool(compat),**a,direct_snr_db=b['snr_db'],direct_peak_pct=b['peak_error_pct'],direct_quiet_snr_db=b['quiet_snr_db']);rows.append(row);np.savez(out/(name+'.npz'),sums=g,patterns=p,lut=j);print(c,name,round(a['snr_db'],4),round(a['quiet_snr_db'],3),round(b['snr_db'],3),bool(compat),flush=True)
  if name in ('59-cross0.02','129-power1.7','353-all','59-power2.2'):wavfile.write(out/(name+'.wav'),48000,w)
  (out/'rows.json').write_text(json.dumps(rows,indent=2))
if __name__=='__main__':main(sys.argv[1])

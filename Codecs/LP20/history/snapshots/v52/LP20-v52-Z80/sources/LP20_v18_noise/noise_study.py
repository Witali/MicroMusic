#!/usr/bin/env python3
"""LP20 v18: exact context-LPC candidate search, speech-active spectral error,
post-PWM feedback. No changes to Z80 format. Metrics and patch selection are
reference-dependent, offline, not a runtime denoiser."""
import os,sys,json,time
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
ROOT=Path(__file__).resolve().parent
V17=Path(os.environ.get('LP20_V17',ROOT.parent/'LP20_v17_gain'))
sys.path.insert(0,str(V17))
from adapt import f,grads,step
from reuse_context import decode_reuse
import numpy as np
from numba import njit
from scipy.signal import resample_poly
from scipy.ndimage import gaussian_filter1d,uniform_filter1d
from numpy.lib.stride_tricks import sliding_window_view as sw
FS=7812.5
NFFT=256;HOP=64
WIN=np.sqrt(np.hanning(NFFT+2)[1:-1]);FREQ=np.fft.rfftfreq(NFFT,1/FS)

def load():
 d=dict(np.load(V17/'shapes/best.npz'));m=json.loads((V17/'release/quality/decoder.json').read_text());return d,m

def aligned(d,y,m,base=None):
 mm,r,z=f.measure(d,y,m);r=f.e.lp(r,3500);z=f.e.lp(z,3500);L=min(len(r),len(z));r=r[:L]-r[:L].mean();z=z[:L]-z[:L].mean();dl=mm['delay'] if base is None else base['delay'];g=mm['gain'] if base is None else base['gain'];assert dl>=0
 x=r[:L-dl];v=z[dl:]*g;return mm,x,v,r,z

def pcm_aligned(x):return resample_poly(x,125,768)

class Mask:
 def __init__(self,x):
  self.x=x;self.n=len(x);self.frames=sw(x,NFFT)[::HOP].copy();self.starts=np.arange(len(self.frames))*HOP
  X=np.fft.rfft(self.frames*WIN);self.P=np.abs(X)**2;power=np.mean(self.frames**2,axis=1);self.active=power>power.max()*10**(-35/10)
  # Voicing proxy from normalized autocorrelation, limited to 75--450 Hz.
  ac=[]
  a=self.frames-self.frames.mean(1,keepdims=True)
  for lag in range(17,105):
   u=a[:,:-lag];v=a[:,lag:];ac.append((u*v).sum(1)/(np.sqrt((u*u).sum(1)*(v*v).sum(1))+1e-18))
  self.voiced=self.active&(np.max(ac,axis=0)>.58)
  # Spectral masking approximation: spreading in adjacent frequency bins,
  # floor tied to local frame energy; penalize error in spectral valleys.
  spread=gaussian_filter1d(self.P,2.,axis=1);floor=np.maximum(spread.max(1,keepdims=True)*.003,np.max(spread)*1e-5)
  self.weights=1/(spread+floor);self.weights*=self.active[:,None];self.weights[:,0]=0;self.weights[:,FREQ>3500]=0
  self.weights*=1+1.2*self.voiced[:,None]*((FREQ>=1500)&(FREQ<=3500))[None,:]
  self.weights/=self.weights[self.weights>0].mean()
  self.voicefreq=(FREQ>=1500)&(FREQ<=3500)
 def analyze(self,v,grad=False):
  E=np.fft.rfft((sw(v[:self.n],NFFT)[::HOP][:len(self.frames)]-self.frames)*WIN);p=np.abs(E)**2
  vals=dict(masked_error=float(np.sum(p*self.weights)),active_error=float(np.sum(p[self.active])),voiced_high_error=float(np.sum(p[self.voiced][:,self.voicefreq])),active_frames=int(self.active.sum()),voiced_frames=int(self.voiced.sum()))
  if not grad:return vals
  gframe=2*np.fft.irfft(E*self.weights,n=NFFT)*WIN;g=np.zeros(self.n)
  for i,s in enumerate(self.starts):g[s:s+NFFT]+=gframe[i]
  return vals,g

def extra_metrics(x,v):
 u=pcm_aligned(x);z=pcm_aligned(v);n=min(len(u),len(z));return Mask(u[:n]).analyze(z[:n])

@njit(cache=True)
def trellis(t,tb,bk,bm,lens,alt,ab,active,th,q,w,wd,wl,pen,extra,qid,width):
 n=len(t);best=np.full((n+1,width),1e30);hist=np.zeros((n+1,width,6),np.int16);ids=np.full((n+1,width),-1,np.int16);prev=np.zeros((n+1,width),np.uint8);best[0,0]=0;h=np.empty(6,np.int16)
 for p in range(n):
  for j in range(width):
   if best[p,j]>1e29:break
   old=q[hist[p,j,0]+512]-t[p-1] if p else 0.
   # The exact same context as the ROM decoder, at block start.
   ctx=hist[p,j,0]>=th or hist[p,j,0]<-th
   for k in range(len(lens)):
    ln=lens[k];end=p+ln
    if end>n:continue
    err=best[p,j]+pen
    if err>=best[end,width-1]:continue
    h[:]=hist[p,j];pe=old;ok=True;use=ctx and active[k];bank=ab[k] if use else bm[k];vec=alt[k] if use else bk[k]
    for z in range(ln):
     v,ov=step(h,tb[bank],vec[z],10)
     if ov:ok=False;break
     e=q[v+512]-t[p+z];lo=.65*e+.35*pe;hi=e-pe
     err+=w[p+z]*e*e+wd[p+z]*hi*hi+wl[p+z]*lo*lo+extra[p+z,qid[v+512]];pe=e
     if err>=best[end,width-1]:ok=False;break
    if not ok:continue
    dup=-1
    for k2 in range(width):
     if best[end,k2]>1e29:break
     same=True
     for a in range(6):
      if h[a]!=hist[end,k2,a]:same=False;break
     if same:dup=k2;break
    if dup>=0:
     if err>=best[end,dup]:continue
     at=dup
    else:at=width-1
    while at>0 and err<best[end,at-1]:
     best[end,at]=best[end,at-1];hist[end,at]=hist[end,at-1];ids[end,at]=ids[end,at-1];prev[end,at]=prev[end,at-1];at-=1
    best[end,at]=err;hist[end,at]=h;ids[end,at]=k;prev[end,at]=j
 out=np.empty(n,np.int16);p=n;j=0;cnt=0
 while p>0:
  k=ids[p,j]
  if k<0:raise ValueError('no path')
  out[cnt]=k;cnt+=1;j=prev[p,j];p-=lens[k]
 return out[:cnt][::-1].copy()

def prepare():
 d,m=load();mm,x,v,r,z=aligned(d,d['y'],m);mask=Mask(pcm_aligned(x));vpcm=pcm_aligned(v);extra,ng=mask.analyze(vpcm,True)
 # Error origin diagnostic, same passband / independent gain and delay fit.
 pcm=f.e.lp(resample_poly(d['y']/508.,768,125),3500);m_pcm=f.e.align_metric(f.e.lp(r,3500),pcm);m_pwm=f.e.align_metric(pcm,f.e.lp(z,3500))
 print('BASE',mm,extra,'PCM',m_pcm,'PWM vs PCM',m_pwm,flush=True)
 gr,gt,_=grads(d,d['y'],m);n=len(d['y']);ng=np.pad(ng,(0,max(0,n-len(ng))))[:n];ng*=np.sqrt(np.mean(gr**2))/(np.sqrt(np.mean(ng**2))+1e-30)
 np.savez(ROOT/'gradient.npz',gr=gr,gt=gt,ng=ng);(ROOT/'baseline.json').write_text(json.dumps(dict(**mm,**extra,pcm=m_pcm,pwm_only=m_pwm),indent=2))

def run(which):
 d,m=load();g=np.load(ROOT/'gradient.npz');t=d['target'];y=d['y'];nom=f.lut10(d['ww10']);lev=np.array([sum(m['patterns'][str(int(i))]) for i in d['ww10']]);lev=(lev-1280)*128/1120;qi=np.searchsorted(d['ww10'],nom);q=lev[qi];old=q[y+512];n=len(y)
 # Vary rate locally; global allocation enforces the original byte budget.
 # ex = amplitude weighting, high = high-band error, low = low-band error;
 # feedback combines masked spectral SSE and true STOI gradient.
 pars=[(12,.15,.1,.55,.35,.4,1.0),(24,.25,.45,.1,.6,.7,1.0),(42,.45,.6,.0,.55,.9,1.5),(75,.25,.25,.45,.3,.6,1.0),(20,.6,.75,.0,.8,1.1,2.0),(34,.1,.08,.85,.8,.4,1.4),(10,.1,.9,.0,.65,.7,1.2),(55,.55,.4,.25,.6,1.,1.6)]
 lam,ex,hi,lo,noise,stoi,trust=pars[which]
 w=(uniform_filter1d(t*t,156)+12.)**(-ex);w/=w.mean();wd=w*hi;wl=w*lo
 delta=lev[None,:]-old[:,None];extra=((noise*g['ng']-stoi*g['gt']+.1*g['gr'])[:,None]*delta+trust*w[:,None]*delta**2);extra-=extra.min(1,keepdims=True);extra=extra.astype(np.float32);start=time.time()
 ix=trellis(t,d['tb'],d['bk'],d['bm'],d['lens'],d['alt'],d['ab'],d['active'],int(d['threshold']),q,w,wd,wl,lam,extra,qi,2);yy,ov=decode_reuse(d['tb'],d['bk'],d['bm'],d['lens'],ix,d['alt'],d['ab'],d['active'],int(d['threshold']));assert not ov
 mm,x,v,_,_=aligned(d,yy,m);mm.update(extra_metrics(x,v));mm.update(bytes=len(ix),kbps=len(ix)*8/(n/FS)/1000,params=pars[which],seconds=time.time()-start);np.savez(ROOT/f'candidate{which}.npz',idx=ix,y=yy);(ROOT/f'candidate{which}.json').write_text(json.dumps(mm,indent=2));print('CANDIDATE',which,mm,flush=True)
if __name__=='__main__':
 if sys.argv[1]=='prepare':prepare()
 else:run(int(sys.argv[1]))

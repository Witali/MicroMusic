#!/usr/bin/env python3
"""PC-only experiments on v45, unchanged legacy PWM renderer."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
import sys,json,csv,time
import numpy as np
ROOT=Path(__file__).resolve().parent
V45=Path(os.environ.get('LP20_V45',ROOT.parent/'LP20-v45'))
sys.path.insert(0,str(V45))
from adaptive45 import *
from peak_audit import filt,align,metrics as peak_metrics
from scipy.signal import welch
ROOT=Path(__file__).resolve().parent

@njit(cache=True)
def shape(x,lv,a,b):
 out=np.empty(len(x));e1=0.;e2=0.
 for i in range(len(x)):
  v=x[i]+a*e1+b*e2;v=min(max(v,lv[0]),lv[-1]);j=np.searchsorted(lv,v);j=min(max(j,1),len(lv)-1)
  if abs(v-lv[j-1])<=abs(v-lv[j]):j-=1
  out[i]=lv[j];e2=e1;e1=v-out[i]
 return out

def pre(x,amount):
 f=np.fft.rfftfreq(len(x),1/FS);gain=1+amount*(1/np.sinc(f/FS)-1)
 return np.fft.irfft(np.fft.rfft(x)*gain,n=len(x))

def data(clip):
 base=BASE/'input'/clip;d=dict(np.load(base/'model.npz'));meta=json.loads((base/'decoder.json').read_text());ref=wavfile.read(base/'reference.wav')[1];lv=np.unique(levels(d,meta)[1]);x=d['target'];return base,d,meta,ref,lv,x

def evaluate(ref,wav,full=False):
 if full:return metrics(ref,wav)
 x=filt(ref.astype(float)/32768);x-=x.mean();y=filt(wav.astype(float)/32768);return peak_metrics(x,y)

def full_error(ref,wav,level):
 r=filt(ref.astype(float)/32768);r-=r.mean();y,lag,g=align(r,filt(wav.astype(float)/32768));e=r-y;e[:480]=0;e[-480:]=0
 return resample_poly(e,125,768)*level/max(abs(r))

def direct(clip):
 base,d,meta,ref,lv,x=data(clip);out=ROOT/clip;out.mkdir(exist_ok=True);rows=[];best={}
 def test(tag,z,params):
  w=render(z,d,meta);m=evaluate(ref,w);rows.append(dict(clip=clip,profile=tag,**params,**m));return w,m
 def keep(tag,z,w,m):
  for k,cost in [('snr',-m['snr_db']),('peak',m['peak_error_pct']),('balanced',-m['snr_db']+.20*max(0,m['peak_error_pct']-8))]:
   if k not in best or cost<best[k][0]:best[k]=(cost,tag,z,w,m)
 for g in (1.,.94,.90,.85):
  for p in (0.,1.):
   for a,b in ((0.,0.),(.35,0.),(.70,0.),(.65,-.18)):
    z=shape(pre(x*g,p),lv,a,b);tag=f'direct-g{g}-p{p}-a{a}-b{b}';w,m=test(tag,z,dict(input_gain=g,preemphasis=p,feedback1=a,feedback2=b));keep(tag,z,w,m)
  print(clip,'GAIN',g,[(k,v[-1]['snr_db'],v[-1]['peak_error_pct']) for k,v in best.items()],flush=True)
 for label in ('snr','peak','balanced'):
  _,tag,z,w,m=best[label];r=next(r for r in rows if r['profile']==tag);g=r['input_gain'];p=r['preemphasis'];a=r['feedback1'];b=r['feedback2'];t=pre(x*g,p)
  for j in range(3):
   e=full_error(ref,w,np.max(abs(x))*g);t=t+.7*pre(e,.7);z=shape(t,lv,a,b);newtag=f'{tag}-out{j+1}';w,m=test(newtag,z,dict(input_gain=g,preemphasis=p,feedback1=a,feedback2=b));keep(newtag,z,w,m)
 for k,(_,tag,z,w,m) in best.items():
  wavfile.write(out/f'direct-{k}.wav',48000,w);np.save(out/f'direct-{k}.npy',z);print(clip,k,tag,m['snr_db'],m['peak_error_pct'],flush=True)
 (out/'direct.json').write_text(json.dumps(rows,indent=2));(out/'direct-best.json').write_text(json.dumps({k:v[1] for k,v in best.items()},indent=2))

if __name__=='__main__':direct(sys.argv[1])

import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import numpy as np
from scipy.signal import resample_poly
from scipy.ndimage import uniform_filter1d,gaussian_filter1d
from scipy.io.wavfile import read
from pathlib import Path
import encoder_core as c, encode as e
from search import search,reconstruct,train_refine
import json,time,sys
ROOT=Path(__file__).resolve().parent.parent;FS=7812.5

def prepare(path,mode):
 sr,x=read(path);x=x.astype(float)/32768
 if x.ndim>1:x=x.mean(axis=1)
 assert sr==48000
 x=resample_poly(x,125,768);x-=x.mean();x*=.99/max(abs(x))
 if mode=='level':
  env=np.sqrt(np.maximum(0,uniform_filter1d(x*x,size=781)));gain=np.clip((.10/np.maximum(env,.018))**.4,.75,2.)
  x*=gaussian_filter1d(gain,120);x*=.99/max(abs(x))
 return np.pad(x*127,(0,(-len(x))%8))

def extend(t,tb,bk,bm,lens,idx,start,w,limit):
 order=tb.shape[1];loc=np.r_[0,np.cumsum(lens[idx])];v=np.arange(256);v[v>=128]-=256;a=(tb@v)/(v@v);target=np.clip(np.rint(t),-127,127).astype(np.int16);cand=[]
 for k,n in enumerate(lens):
  hits=np.where(idx==k)[0]
  if len(hits)<2:continue
  p=loc[hits];arr=target[p[:,None]+np.arange(n)];h=np.concatenate([start[hits,::-1],arr],axis=1);pred=sum(tb[bm[k],j,h[:,order-1-j:order-1-j+n]&255] for j in range(order));r=np.clip(arr-pred,-128,127).astype(float)
  M=c.impulse(a[bm[k]],n);z=r@M.T;v0=bk[k,:n]@M.T;ws=np.mean(w[p[:,None]+np.arange(n)],axis=1);err=np.sum((z-v0)**2,axis=1);gain=(z@v0)/(np.dot(v0,v0)+1e-8);bins=np.digitize(gain,np.quantile(gain,[.25,.5,.75]));vec=[]
  for j in range(4):
   ii=np.where(bins==j)[0]
   if len(ii):vec.append(np.average(r[ii],axis=0,weights=ws[ii]))
  for g in (.5,.72,1.35,1.8):vec.append(bk[k,:n]*g)
  for j in np.argsort(err*ws)[-min(5,len(hits)):]:
   ii=np.argsort(np.sum((z-z[j])**2,axis=1))[:max(1,min(25,len(hits)//4))];vec.append(np.average(r[ii],axis=0,weights=ws[ii]))
  for q in vec:
   q=np.clip(np.rint(q),-128,127).astype(np.int16);dist=np.sum((z-q@M.T)**2,axis=1);score=np.sum(np.maximum(err-dist,0)*ws)/(1+.025*n)
   if score>0:cand.append((score,q,int(bm[k]),int(n)))
 out=list(bk);maps=list(bm);ll=list(lens);seen={(int(m),int(n),tuple(q[:n])) for q,m,n in zip(bk,bm,lens)}
 for score,q,m,n in sorted(cand,key=lambda s:s[0],reverse=True):
  key=(m,n,tuple(q))
  if key in seen:continue
  seen.add(key);out.append(np.pad(q,(0,bk.shape[1]-n)));maps.append(m);ll.append(n)
  if len(out)>=limit:break
 return np.array(out,np.int16),np.array(maps,np.uint8),np.array(ll,np.int32)

def run(source,seed,mode,alpha=.1,limit=510):
 O=ROOT/mode;O.mkdir(exist_ok=True);t=prepare(source,mode);e.FS=FS;e.PERIOD=128;e.PULSES=20;e.LEVELS=77
 d=np.load(seed);tb,bk,bm,lens,idx=[d[k] for k in ('tb','bk','bm','lens','idx')];assert np.sum(lens[idx])==len(t)
 w=(uniform_filter1d(t*t,size=156)+12.)**(-alpha);w/=np.mean(w);y,h,over=reconstruct(t,tb,bk,bm,lens,idx);bk,bm,lens=extend(t,tb,bk,bm,lens,idx,h,w,limit);print('dictionary',len(bk),sum(lens),flush=True)
 prices=np.ones(len(bk),np.int16)*2;prices[np.argsort(-np.bincount(idx,minlength=len(bk)))[:254]]=1
 target=len(t)/FS*5000/8;lam=45.;xr=resample_poly(t/127,768,125);scale=.98/max(abs(xr));e.wav(O/'reference.wav',xr*scale)
 for it in range(2):
  best=None;lo=0.;hi=160.
  for s in range(7):
   ts=time.time();idx,cost=search(t,tb,bk,bm,lens,w,prices,lam);size=int(prices[idx].sum());print(mode,it,s,lam,size,round(time.time()-ts,1),flush=True)
   if best is None or abs(size-target)<abs(best[0]-target):best=(size,idx.copy(),lam)
   if abs(size-target)<65:break
   if size>target:lo=lam
   else:hi=lam
   lam=(lo+hi)/2
  size,idx,lam=best;y,h,over=reconstruct(t,tb,bk,bm,lens,idx);pwm=e.render(y);m=e.align_metric(e.lp(xr,3500),e.lp(pwm,3500));pcm=e.align_metric(e.lp(xr,3500),e.lp(resample_poly(y/127,768,125),3500));report=dict(bytes=size,kbps=size*8/(len(t)/FS)/1000,snr=m['snr'],stoi=m['stoi'],pcm_snr=pcm['snr'],pcm_stoi=pcm['stoi'],overflows=int(over),penalty=lam,extended=int(np.sum(prices[idx]==2)),symbols=len(idx),used_codes=len(set(idx)),codebook_bytes=int(sum(lens[np.unique(idx)])))
  print(report,flush=True);tag='pass'+str(it);(O/(tag+'.json')).write_text(json.dumps(report,indent=2));np.savez(O/(tag+'.npz'),idx=idx,tb=tb,bk=bk,bm=bm,lens=lens,y=y,prices=prices,target=t);e.wav(O/(tag+'.pwm.wav'),pwm/(2*38/128)*scale*128/127);e.wav(O/(tag+'.pcm.wav'),resample_poly(y/127,768,125)*scale)
  if it==1:break
  bk=train_refine(t,tb,bk,bm,lens,idx,h,w);prices[:]=2;prices[np.argsort(-np.bincount(idx,minlength=len(bk)))[:254]]=1
if __name__=='__main__':run(*sys.argv[1:4],*(map(float,sys.argv[4:5])),*(map(int,sys.argv[5:6])))

"""Offline LP20 experiment: signed 8/10/12-bit predictor states; VBR VQ,
closed-loop retraining, identical 7812.5 Hz source. No RAM-free CPU claim.
12-bit/10-bit state uses Q8 products rounded once at history update.
"""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import sys, time, json, math
from pathlib import Path
import numpy as np
from numba import njit
from scipy.ndimage import uniform_filter1d
from scipy.signal import resample_poly
import encode as e
from compact_container import exact_coeff
from encoder_core import design
ROOT=Path(__file__).resolve().parent.parent
FS=7812.5;SPAN=48 # 16..112 T; 96 discrete intervals, ideal fractional mode separate
@njit(cache=True)
def step(h,tab,r,bits):
    # tab returns Q8 products of signed integer/fractional history. All units
    # represented in signed Q8; history values are in Q(bits-8).
    k=bits-8; shift=8-k; s=int(r)<<shift; m=1<<(bits-1)
    for i in range(len(h)):s+=int(tab[i,h[i]+m])
    z=(s+(1<<(shift-1)))>>shift
    overflow=(z < -m or z >= m)
    v=max(-m,min(m-1,z))
    for i in range(len(h)-1,0,-1):h[i]=h[i-1]
    h[0]=v
    return v,overflow
@njit(cache=True)
def qout(v,bits,span,mode):
    s=1<<(bits-8)
    # output scale in old 8-bit sample units; constant duty, 1-T steps.
    if mode==0:return v/s
    return ((v*span+64*s)//(128*s))*128./span
@njit(cache=True)
def search(t,tb,bk,bm,lens,w,pen,bits,span,mode,width):
 n=len(t);order=tb.shape[1];best=np.full((n+1,width),1e30);hist=np.zeros((n+1,width,order),np.int16);ids=np.full((n+1,width),-1,np.int16);prev=np.zeros((n+1,width),np.uint8);best[0,0]=0;h=np.empty(order,np.int16)
 for p in range(n):
  for q in range(width):
   if best[p,q]>1e29:break
   pe=0. if p==0 else qout(hist[p,q,0],bits,span,mode)-t[p-1]
   for k in range(len(lens)):
    ln=lens[k];j=p+ln
    if j>n:continue
    err=best[p,q]+pen
    if err>=best[j,width-1]:continue
    h[:]=hist[p,q];old=pe
    for z in range(ln):
     y,wr=step(h,tb[bm[k]],bk[k,z],bits);d=qout(y,bits,span,mode)-t[p+z];low=.65*d+.35*old;err+=w[p+z]*(.65*d*d+.35*low*low)+250000.*wr;old=d
     if err>=best[j,width-1]:break
    if err>=best[j,width-1]:continue
    dup=-1
    for v in range(width):
     if best[j,v]>1e29:break
     same=True
     for a in range(order):
      if h[a]!=hist[j,v,a]:same=False;break
     if same:dup=v;break
    if dup>=0:
     if err>=best[j,dup]:continue
     at=dup
    else:at=width-1
    while at>0 and err<best[j,at-1]:
     best[j,at]=best[j,at-1];hist[j,at]=hist[j,at-1];ids[j,at]=ids[j,at-1];prev[j,at]=prev[j,at-1];at-=1
    best[j,at]=err;hist[j,at]=h;ids[j,at]=k;prev[j,at]=q
 seq=np.empty(n,np.int16);cnt=0;p=n;q=0
 while p>0:
  k=ids[p,q];assert k>=0;seq[cnt]=k;cnt+=1;q=prev[p,q];p-=lens[k]
 return seq[:cnt][::-1].copy()
@njit(cache=True)
def reconstruct(t,tb,bk,bm,lens,idx,bits):
 h=np.zeros(tb.shape[1],np.int16);y=np.empty(len(t),np.int16);start=np.empty((len(idx),tb.shape[1]),np.int16);p=0;over=0
 for i,k in enumerate(idx):
  start[i]=h
  for j in range(lens[k]):
   v,wr=step(h,tb[bm[k]],bk[k,j],bits);y[p]=v;p+=1;over+=wr
 return y,start,over
@njit(cache=True)
def refine(t,tb,bk,bm,lens,idx,start,w,bits,span,mode):
 out=bk.copy();loc=np.zeros(len(idx)+1,np.int64);loc[1:]=np.cumsum(lens[idx]);s=1<<(bits-8)
 for k in range(len(lens)):
  hits=np.where(idx==k)[0];ln=lens[k]
  if len(hits)==0:continue
  for j in range(ln):
   old=out[k,j];best=1e30;choice=old
   for d in (0,-s,s,-s//2,s//2,-1,1,-2*s,2*s):
    v=old+d
    if v < -128*s or v>128*s-1:continue
    out[k,j]=v;err=0.
    for b in hits:
     h=start[b].copy();p=loc[b];prev=0. if p==0 else qout(h[0],bits,span,mode)-t[p-1]
     for z in range(ln):
      y,wr=step(h,tb[bm[k]],out[k,z],bits);q=qout(y,bits,span,mode)-t[p+z];low=.65*q+.35*prev;err+=w[p+z]*(.65*q*q+.35*low*low)+250000.*wr;prev=q
    if err<best:best=err;choice=v
   out[k,j]=choice
 return out

def tables(a,bits):
 m=1<<(bits-1);shift=8-(bits-8);x=np.arange(-m,m,dtype=np.int32);whole=x>>(bits-8);frac=x-(whole<<(bits-8))
 # two components correspond to a ROM implementation using page lookups.
 return np.rint(a[:,:,None]*whole*256).astype(np.int32)+np.rint(a[:,:,None]*frac*(1<<shift)).astype(np.int32)

def render(y,bits,span,frac=False):
 s=1<<(bits-8);desired=64+y.astype(float)*span/(128*s)
 if frac:
  total=np.rint(desired*20).astype(np.int32);i=np.arange(21,dtype=np.int32);width=np.diff((total[:,None]*i[None,:]+10)//20,axis=1).ravel()
 else:width=np.repeat(np.floor(desired+.5).astype(np.int32),20)
 z=(np.clip(width[:,None]-np.arange(4)*32,0,32).astype(np.float32)/16-1).ravel();g=math.gcd(48000*32,20000000);return e.lp(resample_poly(z,48000*32//g,20000000//g),7000)

def save(name,t,a,tb,bk,bm,lens,idx,bits,lam,span=SPAN,mode=0):
 out=ROOT/name;out.mkdir(exist_ok=True);y,h,over=reconstruct(t,tb,bk,bm,lens,idx,bits);s=1<<(bits-8);xr=resample_poly(t/127,768,125);g=.98/max(abs(xr));ref=e.lp(xr,3500);pcm=resample_poly(y.astype(float)/(127*s),768,125);report=dict(bits=bits,order=tb.shape[1],banks=tb.shape[0],bytes=len(idx),kbps=len(idx)*8/(len(t)/FS)/1000,overflows=int(over),penalty=lam,history_min=int(y.min()),history_max=int(y.max()),pcm=e.align_metric(ref,e.lp(pcm,3500)))
 for frac in (False,True):
  z=render(y,bits,span,frac)/(2*span/128)*128/127;key='fractional' if frac else 'integer';report[key]=e.align_metric(ref,e.lp(z,3500));report[key]['raw_peak_duty_deviation']=float(np.max(np.abs(z))*2*span/128*127/128);e.wav(out/(key+'_pwm.wav'),z*g*min(1,.98/(np.max(abs(z))*g)))
 e.wav(out/'pcm.wav',pcm*g*min(1,.98/(np.max(abs(pcm))*g)));(out/'metrics.json').write_text(json.dumps(report,indent=2));np.savez(out/'training.npz',target=t,a=a,tb=tb,bk=bk,bm=bm,lens=lens,idx=idx,y=y,bits=bits);print(name,report,flush=True);return y,h

def main(bits,order=6,nb=8,mode=0,rounds=1,width=1):
 d=np.load(ROOT/'baseline_v4.npz');t=d['target'];bk,bm,lens=d['bk'],d['bm'],d['lens'];s=1<<(bits-8);a=np.array([[exact_coeff(x)/2**24 for x in row] for row in d['tb']]);idx=d['idx'];
 if order!=6 or nb!=8:
  from study_v4 import init
  oldtb,bk,bm,lens,_,_=init(t,order,nb);a=np.array([[exact_coeff(x)/2**24 for x in row] for row in oldtb]);idx=None
 tb=tables(a,bits);bk=bk*s;w=(uniform_filter1d(t*t,size=156)+12.)**(-.12);w/=w.mean();lam=22.;name=f'lpc{order}_{nb}banks_{bits}bit';target=len(t)/FS*5000/8
 for it in range(rounds+1):
  best=None
  for q in range(3):
   start=time.time();idx=search(t,tb,bk,bm,lens,w,lam,bits,SPAN,mode,width);print(name,it,q,lam,len(idx),time.time()-start,flush=True)
   if best is None or abs(len(idx)-target)<abs(len(best[0])-target):best=idx.copy(),lam
   if abs(len(idx)-target)<target*.012:break
   lam*=(len(idx)/target)**2.5
  idx,lam=best;y,h=save(name+f'_p{it}',t,a,tb,bk,bm,lens,idx,bits,lam,mode=mode)
  if it<rounds:bk=refine(t,tb,bk,bm,lens,idx,h,w,bits,SPAN,mode)
if __name__=='__main__':main(*map(int,sys.argv[1:]))

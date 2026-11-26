import numpy as np
from numba import njit
import encoder_core as c
@njit(cache=True)
def search(t,tb,bk,bm,lens,weights,prices,penalty):
 n=len(t);ord=tb.shape[1];best=np.full(n+1,1e30);hist=np.zeros((n+1,ord),np.int16);ids=np.full(n+1,-1,np.int16);prev=np.zeros(n+1,np.int32);best[0]=0;h=np.empty(ord,np.int16)
 for i in range(n):
  if best[i]>1e29:continue
  p=i
  for k in range(len(lens)):
   ln=lens[k];j=i+ln
   if j>n:continue
   h[:]=hist[i];err=best[i]+penalty*prices[k]
   for z in range(ln):
    y,w=c.samp(h,tb[bm[k]],bk[k,z]);d=c.qout(y,38)-t[p+z];err+=weights[p+z]*(d*d)+250000.*w
    if err>=best[j]:break
   if err<best[j]:best[j]=err;hist[j]=h;ids[j]=k;prev[j]=i
 seq=np.empty(n,np.int16);cnt=0;i=n
 while i>0:
  seq[cnt]=ids[i];cnt+=1;i=prev[i]
 return seq[:cnt][::-1].copy(),best[n]
@njit(cache=True)
def reconstruct(t,tb,bk,bm,lens,idx):
 h=np.zeros(tb.shape[1],np.int16);y=np.empty(len(t),np.int16);start=np.empty((len(idx),tb.shape[1]),np.int16);p=0;overflow=0
 for i,k in enumerate(idx):
  start[i]=h
  for j in range(lens[k]):
   v,w=c.samp(h,tb[bm[k]],bk[k,j]);y[p]=v;p+=1;overflow+=w
 return y,start,overflow
@njit(cache=True)
def train_refine(t,tb,bk,bm,lens,idx,start,weights):
 out=bk.copy();loc=np.zeros(len(idx)+1,np.int64);loc[1:]=np.cumsum(lens[idx]);order=tb.shape[1]
 for k in range(len(lens)):
  hits=np.where(idx==k)[0];ln=lens[k]
  if len(hits)==0:continue
  # approximate weighted residual at true history, then coordinate descent with closed-loop error
  # coordinate descent using stored starting history, no changes to predictor bank.
  for j in range(ln):
   old=out[k,j];best=1e30;choice=old
   for d in (0,-4,-2,-1,1,2,4):
    v=old+d
    if v < -128 or v>127:continue
    out[k,j]=v;err=0.
    for b in hits:
     h=start[b].copy();p=loc[b]
     for z in range(ln):
      y,w=c.samp(h,tb[bm[k]],out[k,z]);q=c.qout(y,38)-t[p+z];err+=weights[p+z]*q*q+250000.*w
    if err<best:best=err;choice=v
   out[k,j]=choice
 return out


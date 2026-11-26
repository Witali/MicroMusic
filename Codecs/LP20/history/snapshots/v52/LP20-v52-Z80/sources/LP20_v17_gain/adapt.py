#!/usr/bin/env python3
"""Gain adaptation with fixed token count, exact integer LPC and full PWM metric gate.
Scaled vectors pre-expanded on PC; no runtime multiply or added bits."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
import sys,json
import numpy as np
from numba import njit
ROOT=Path(__file__).resolve().parent;V16=ROOT.parent/'LP20_v16_factor';sys.path.insert(0,str(V16))
from refine import f,grads
from precision_study import step
@njit(cache=True)
def score(p,ln,vec,bank,y,tb,q,gr,gt,ex,ba,trust,sw,tail):
 h=np.zeros(6,np.int16)
 for k in range(6):
  if p>k:h[k]=y[p-k-1]
 a=0.;b=0.;c=0.
 for j in range(min(ln+tail,len(y)-p)):
  if j<ln:v,ov=step(h,tb[bank],vec[j],10)
  else:v,ov=step(h,tb[ba[p+j]],ex[p+j],10)
  if ov:return 1e25
  dx=q[v+512]-q[y[p+j]+512];a+=gr[p+j]*dx;b+=gt[p+j]*dx;c+=dx*dx
 return a-sw*b+trust*c
@njit(cache=True)
def evaluate(bm,lens,idx,loc,variants,valid,y,tb,q,gr,gt,ex,ba,trust,sw,tail):
 v=np.full((len(idx),variants.shape[1]),1e25)
 for i in range(len(idx)):
  k=idx[i]
  for g in range(variants.shape[1]):
   if valid[k,g]:v[i,g]=score(loc[i],lens[k],variants[k,g],bm[k],y,tb,q,gr,gt,ex,ba,trust,sw,tail)
 return v
@njit(cache=True)
def alternatives(bk,bm,lens,idx,loc,y,tb,q,gr,gt,ex,ba,trust,sw,tail):
 v=np.full(len(idx),1e25);which=np.full(len(idx),-1,np.int16)
 for i in range(len(idx)):
  old=idx[i];ln=lens[old]
  for k in range(len(lens)):
   if k==old or lens[k]!=ln:continue
   s=score(loc[i],ln,bk[k],bm[k],y,tb,q,gr,gt,ex,ba,trust,sw,tail)
   if s<v[i]:v[i]=s;which[i]=k
 return v,which

def propose(d,snap):
 bk,bm,lens=d['bk'],d['bm'],d['lens'];K,W=bk.shape
 opt=[(g,g) for g in [.5,.625,.75,.8125,.875,.9375,1.0625,1.125,1.1875,1.25,1.375,1.5,1.75,2.]]+[(.75,1.25),(1.25,.75),(.875,1.125),(1.125,.875)]
 v=np.zeros((K,len(opt),W),np.int16);valid=np.zeros((K,len(opt)),np.bool_)
 alph={int(b):np.array(sorted({int(r) for k in np.where(bm==b)[0] for r in bk[k,:lens[k]]})) for b in set(bm.tolist())}
 for k,n in enumerate(lens):
  x=bk[k,:n];a=alph[int(bm[k])]
  for i,(g0,g1) in enumerate(opt):
   if g0!=g1 and n<4:continue
   z=np.clip(np.rint(x*np.linspace(g0,g1,n)),-512,511).astype(np.int16)
   if snap:z=a[np.abs(z[:,None]-a).argmin(1)].astype(np.int16)
   if np.array_equal(z,x) or any(np.array_equal(z,v[k,j,:n]) for j in range(i) if valid[k,j]):continue
   v[k,i,:n]=z;valid[k,i]=True
 return v,valid,opt

def run():
 out=ROOT/'results';out.mkdir(exist_ok=True);d=dict(np.load(V16/'release/training.npz'));meta=json.loads((V16/'release/decoder.json').read_text());d['tb']=f.compact_tables(d['a']);base,_,_=f.measure(d,d['y'],meta);best=base.copy();log=[];accepted=[];print('BASE',base,f.booksize(d['bk'],d['bm'],d['lens']),flush=True)
 q=(np.array([sum(meta['patterns'][str(int(i))]) for i in f.lut10(d['ww10'])])-1280)*128/1120
 def attempt(bk,bm,ix,label,desc,coeff=None):
  nonlocal best,d
  bs,npair=f.booksize(bk,bm,d['lens'])
  if bs is None or bs>3180+350:return False
  a=d['a'] if coeff is None else coeff;tb=f.compact_tables(a);yy,ov=f.decode(tb,bk,bm,d['lens'],ix)
  if ov:return False
  m,r,z=f.measure(d,yy,meta);ok=m['snr']>=best['snr']-1e-10 and m['stoi']>=best['stoi']-1e-10 and (m['snr']>best['snr']+1e-7 or m['stoi']>best['stoi']+1e-7)
  rec=dict(phase=label,description=desc,book_unpacked_bytes=bs,pairs=npair,accepted=bool(ok),**m);log.append(rec)
  if ok:
   d.update(bk=bk.copy(),bm=bm.copy(),idx=ix.copy(),y=yy,a=a.copy(),tb=tb);best=m;accepted.append(rec);print('ACCEPT',rec,flush=True);np.savez(out/'training.npz',**d);f.audio(out/'pwm.wav',r,z)
  (out/'results.json').write_text(json.dumps(dict(baseline=base,best=best,accepted=accepted,trials=log),indent=2));return ok
 for rnd in range(2):
  def prep():
   gr,gt,_=grads(d,d['y'],meta);bk,bm,ix,lens,y=[d[k] for k in ('bk','bm','idx','lens','y')];loc=np.r_[0,np.cumsum(lens[ix])];ex=np.concatenate([bk[k,:lens[k]] for k in ix]);ba=np.repeat(bm[ix],lens[ix]);va,valid,opt=propose(d,rnd==0);args=(y,d['tb'],q,gr,gt,ex,ba,.15,.7,20);sc=evaluate(bm,lens,ix,loc,va,valid,*args);return bk,bm,ix,lens,loc,va,valid,opt,sc,args
  bk,bm,ix,lens,loc,va,valid,opt,sc,args=prep();choices=[]
  for k in range(len(bk)):
   h=np.flatnonzero(ix==k)
   if len(h):
    v=sc[h].sum(0)
    for g in np.argsort(v)[:2]:
     if v[g]<20:choices.append((float(v[g]),k,int(g)))
  choices.sort();print('DIRECT',rnd,len(choices),choices[:5],flush=True)
  for _,k,g in choices[:16]:
   nb=d['bk'].copy();nb[k]=va[k,g];attempt(nb,d['bm'],d['idx'],'word_gain',dict(round=rnd,word=k,gain=list(opt[g])))
  bk,bm,ix,lens,loc,va,valid,opt,sc,args=prep();cost,alt=alternatives(bk,bm,lens,ix,loc,*args);harm=np.array([sum(cost[ix==k]) for k in range(len(bk))]);cand=[]
  for k in range(len(bk)):
   hits=np.flatnonzero(ix==k)
   if not len(hits):continue
   for g in range(len(opt)):
    if not valid[k,g]:continue
    h=hits[sc[hits,g]<0]
    if len(h)<3:continue
    score0=float(sc[h,g].sum());victims=np.flatnonzero((lens==lens[k])&(np.arange(len(bk))!=k))
    for victim in victims[np.argsort(harm[victims])[:3]]:
     if score0+harm[victim]<100 and np.all(alt[ix==victim]>=0):cand.append((score0+harm[victim],k,g,int(victim),h))
  cand.sort(key=lambda x:x[0]);print('SPLIT',rnd,len(cand),[(float(x[0]),x[1],x[2],x[3],len(x[4])) for x in cand[:8]],flush=True)
  used=set();baseix=ix.copy();naccept=0;tried=0
  for _,k,g,victim,h in cand:
   if k in used or victim in used:continue
   if tried>=14 or naccept>=4:break
   jj=d['idx'].copy();vh=np.flatnonzero(jj==victim)
   if not np.array_equal(vh,np.flatnonzero(baseix==victim)) or np.any(jj[h]!=k) or np.any(np.isin(alt[vh],list(used))):continue
   jj[vh]=alt[vh];jj[h]=victim;nb=d['bk'].copy();nm=d['bm'].copy();nb[victim]=va[k,g];nm[victim]=bm[k];tried+=1
   if attempt(nb,nm,jj,'adaptive_gain',dict(round=rnd,shape=k,slot=victim,gain=list(opt[g]),blocks=len(h),replaced_blocks=len(vh))):used.update((k,victim));naccept+=1
 np.savez(out/'training.npz',**d);(out/'results.json').write_text(json.dumps(dict(baseline=base,best=best,accepted=accepted,trials=log),indent=2));print('FINAL',best,flush=True)
if __name__=='__main__':run()

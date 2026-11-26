#!/usr/bin/env python3
"""LP20 adaptive pitch-aware encoder. Same block lengths and byte count;
unchanged exact integer LPC, ROM dictionary and PWM. Encoder-side only."""
import os,sys,json,argparse,time
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
ROOT=Path(__file__).resolve().parent
V18=Path(os.environ.get('LP20_V18',ROOT.parent/'LP20_v18_noise'))
sys.path.insert(0,str(V18))
from noise_study import f,grads,step,aligned,pcm_aligned,FS,trellis
from reuse_context import decode_reuse
from scipy.ndimage import uniform_filter1d
from scipy.io.wavfile import read
from scipy.signal import resample_poly
from numba import njit
import numpy as np
import pitch

@njit(cache=True)
def fixed_search(tb,bk,bm,lens,alt,ab,active,th,bl,qid,extra,beam):
 hist=np.zeros((beam,6),np.int16);cost=np.full(beam,1e30);cost[0]=0;prev=np.zeros((len(bl),beam),np.int16);tok=np.full((len(bl),beam),-1,np.int16);p=0;hh=np.empty(6,np.int16)
 for bi in range(len(bl)):
  ln=bl[bi];nh=np.zeros((beam,6),np.int16);nc=np.full(beam,1e30)
  for j in range(beam):
   if cost[j]>=1e29:break
   ctx=hist[j,0]>=th or hist[j,0]<-th
   for k in range(len(lens)):
    if lens[k]!=ln:continue
    hh[:]=hist[j];s=cost[j];good=True;use=ctx and active[k];bank=ab[k] if use else bm[k];vec=alt[k] if use else bk[k]
    for z in range(ln):
     v,ov=step(hh,tb[bank],vec[z],10)
     if ov:good=False;break
     s+=extra[p+z,qid[v+512]]
     if s>=nc[-1]:good=False;break
    if not good:continue
    at=beam-1;dup=False
    for r in range(beam):
     if nc[r]>=1e29:break
     same=True
     for z in range(6):
      if hh[z]!=nh[r,z]:same=False;break
     if same:
      if s>=nc[r]:dup=True
      else:at=r
      break
    if dup:continue
    while at>0 and s<nc[at-1]:
     nc[at]=nc[at-1];nh[at]=nh[at-1];tok[bi,at]=tok[bi,at-1];prev[bi,at]=prev[bi,at-1];at-=1
    nc[at]=s;nh[at]=hh;tok[bi,at]=k;prev[bi,at]=j
  if nc[0]>=1e29:return np.empty(0,np.int16)
  cost=nc;hist=nh;p+=ln
 out=np.empty(len(bl),np.int16);j=0
 for i in range(len(bl)-1,-1,-1):out[i]=tok[i,j];j=prev[i,j]
 return out

def model(path):
 d=dict(np.load(path));d['tb']=f.compact_tables(d['a']);d.setdefault('ww10',d['ww'].astype(np.int16)*10);d.setdefault('alt',np.zeros_like(d['bk']));d.setdefault('ab',d['bm'].copy());d.setdefault('active',np.zeros(255,bool));d.setdefault('threshold',np.array(96));return d

def decode(d,ix):return decode_reuse(d['tb'],d['bk'],d['bm'],d['lens'],ix,d['alt'],d['ab'],d['active'],int(d['threshold']))
def qtables(d,m):
 nominal=f.lut10(d['ww10']);lev=(np.array([sum(m['patterns'][str(int(k))]) for k in d['ww10']])-1280)*128/1120
 qi=np.searchsorted(d['ww10'],nominal);return lev,qi,lev[qi]

def load_wav(p):
 import math
 fs,x=read(p);x=x.astype(float);x=x.mean(1) if x.ndim==2 else x;g=math.gcd(15625,2*fs);x=resample_poly(x,15625//g,2*fs//g);x-=x.mean();peak=max(abs(x));
 if len(x)<FS or not np.isfinite(peak) or peak<=1e-15:raise ValueError('Need at least one second of finite non-silent audio')
 x*=125.73/peak;return np.pad(x,(0,(-len(x))%8))

def new_baseline(d,t,m,bps=5019.):
 d=dict(d,target=t);lev,qi,q=qtables(d,m);n=len(t);budget=n/FS*bps/8;w=(uniform_filter1d(t*t,156)+12)**(-.35);w/=w.mean();extra=np.zeros((n,len(lev)),np.float32);lam=40.;lo=None;hi=None;best=None
 for it in range(6):
  ix=trellis(t,d['tb'],d['bk'],d['bm'],d['lens'],d['alt'],d['ab'],d['active'],int(d['threshold']),q,w,w*.45,w*.1,lam,extra,qi,1);nix=len(ix);print('BASE SEARCH',it,lam,nix,'target',budget,flush=True)
  if best is None or (nix<=budget and (len(best)>budget or nix>len(best))) or (len(best)>budget and nix<len(best)):best=ix.copy()
  if abs(nix-budget)<budget*.009:break
  if nix>budget:lo=(lam,nix)
  else:hi=(lam,nix)
  if lo and hi:
   frac=np.clip(np.log(lo[1]/budget)/max(1e-10,np.log(lo[0]/hi[1])),.12,.88);lam=np.exp((1-frac)*np.log(lo[0])+frac*np.log(hi[0]))
  else:lam*=max(.25,min(4.,(nix/budget)**1.7))
 y,ov=decode(d,best);assert not ov;return dict(d,idx=best,y=y)

def pad(x,n):return np.pad(x,(0,max(0,n-len(x))))[:n]
def rms(x):return np.sqrt(np.mean(x*x)+1e-25)
def inspect(d,y,m,pt=None):
 mm,x,v,r,z=aligned(d,y,m);n=len(d['y']);u=pad(pcm_aligned(x),n);vv=pad(pcm_aligned(v),n)
 if pt is None:pt=pitch.track(u)
 e=vv-u;mm.update(periodic_error=pitch.cost(pt,e),voiced_error=float(np.dot(pt['weight'],e*e)))
 return mm,pt,r,z,u,vv

def study(d,m,out,passes=1):
 out.mkdir(exist_ok=True,parents=True);n=len(d['y']);lev,qi,q=qtables(d,m);base,pt,r,z,u,vv=inspect(d,d['y'],m);s=pitch.summary(pt);print('PITCH',s,'BASE',base,flush=True)
 initial=d['idx'].copy();idx=initial.copy();y=d['y'].copy();bl=d['lens'][idx];pos=np.r_[0,np.cumsum(bl)];best=base.copy();log=[];f.audio(out/'baseline.wav',r,z);f.e.wav(out/'reference.wav',r*.98/max(abs(r)));np.savez(out/'pitch_track.npz',centers=pt['centers'],lag=pt['lag'],confidence=pt['confidence'],active=pt['active'],fs=FS);(out/'pitch.json').write_text(json.dumps(s,indent=2))
 def save():
  np.savez(out/'training.npz',**dict(d,idx=idx,y=y));(out/'results.json').write_text(json.dumps(dict(pitch=s,baseline=base,final=best,stream_bytes=len(idx),changes=int(np.sum(idx!=initial)),trials=log),indent=2));_,_,r,z,*_=inspect(d,y,m,pt);f.audio(out/'pwm.wav',r,z)
 def check(ix,tag):
  nonlocal best,idx,y
  yy,ov=decode(d,ix)
  if ov:return False
  mm,*_=inspect(d,yy,m,pt);ok=mm['snr']>=best['snr']-1e-10 and mm['stoi']>=best['stoi']-1e-10 and mm['periodic_error']<=best['periodic_error']+1e-12 and mm['voiced_error']<=best['voiced_error']+1e-12
  accepted=bool(ok and (mm['periodic_error']<best['periodic_error']-1e-9 or mm['snr']>best['snr']+1e-8 or mm['stoi']>best['stoi']+1e-8));rec=dict(tag=tag,accepted=accepted,changes=int(np.sum(ix!=idx)),**mm);log.append(rec)
  if accepted:best=mm;idx=ix.copy();y=yy;print('ACCEPT',rec,flush=True)
  return accepted
 save()
 for it in range(passes):
  mm,_,r,z,u,vv=inspect(d,y,m,pt);gr,gt,_=grads(d,y,m);gp=pitch.cost(pt,vv-u,True)[1];gp*=rms(gr)/rms(gp);gr=pad(gr,n);gt=pad(gt,n);old=q[y+512];w=(uniform_filter1d(d['target']**2,156)+12)**(-.25);w/=w.mean();dlt=lev[None,:]-old[:,None];alts=[]
  for ph,st,trust in [(0.,.6,3.),(.35,.6,3.),(.8,.6,3.),(1.6,.6,4.),(.8,.3,7.)]:
   ex=(gr-st*gt+ph*gp)[:,None]*dlt+trust*w[:,None]*dlt*dlt;ex-=ex.min(1,keepdims=True);ex=ex.astype(np.float32)
   ix=fixed_search(d['tb'],d['bk'],d['bm'],d['lens'],d['alt'],d['ab'],d['active'],int(d['threshold']),bl,qi,ex,3);del ex
   if not len(ix):continue
   yy,ov=decode(d,ix)
   if ov:continue
   met,_,_,_,uu,ww=inspect(d,yy,m,pt);print('CAND',it,ph,st,trust,met,flush=True);log.append(dict(tag=['candidate',it,ph,st,trust],accepted=False,**met));alts.append((ix,met,uu,ww,ph))
  del dlt
  for ix,met,uu,ww,ph in alts:
   if ph>0:check(ix,['whole',it,ph])
  mm,_,_,_,u,vv=inspect(d,y,m,pt);err=vv-u;per=err-pitch.pred(pt,err);wgt=pt['weight'];choices=[]
  for ix,met,uu,ww,ph in alts:
   if ph==0:continue
   ee=ww-uu;pe=ee-pitch.pred(pt,ee);gain=err*err-ee*ee;harm=wgt*(per*per-pe*pe);voiced=wgt*gain
   for l0 in range(0,n,round(FS*.36)):
    l,h=np.searchsorted(pos,[l0,min(n,l0+round(FS*.36))]);h=min(h,len(idx));
    if h<=l or np.array_equal(ix[l:h],idx[l:h]):continue
    a,b=int(pos[l]),min(len(err),int(pos[h]));sse=float(gain[a:b].sum());hp=float(harm[a:b].sum());vp=float(voiced[a:b].sum());
    if sse>0 and hp>0 and vp>=0:choices.append((sse/(np.sum(err*err)+1e-20)+hp/(best['periodic_error']+1e-20),l,h,ix,ph))
  choices.sort(key=lambda o:-o[0]);used=set();accepted=0;tries=0;selected=[]
  for gain,l,h,ix,ph in choices:
   if any(i in used for i in range(l,h)):continue
   used.update(range(l,h));selected.append((gain,l,h,ix,ph))
   if len(selected)>=28:break
  def batch(group):
   nonlocal accepted,tries
   if not group or tries>=35:return
   jj=idx.copy()
   for _,l,h,ix,ph in group:jj[l:h]=ix[l:h]
   if np.array_equal(jj,idx):return
   tries+=1
   if check(jj,['patch',it,[(int(l),int(h),ph) for _,l,h,_,ph in group]]):accepted+=len(group)
   elif len(group)>1:
    mid=len(group)//2;batch(group[:mid]);batch(group[mid:])
  for i in range(0,len(selected),6):batch(selected[i:i+6])
  print('ROUND',it,accepted,'patches',tries,best,flush=True);save()
 save();return dict(d,idx=idx,y=y),best

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('name');p.add_argument('--source');p.add_argument('--wav');p.add_argument('--passes',type=int,default=1);p.add_argument('--out');p.add_argument('--bps',type=float,default=5019.);p.add_argument('--reuse-baseline',action='store_true',help='reuse cached baseline only for the SAME input WAV');a=p.parse_args();src=a.source or str(V18/'release/compact/training.npz');d=model(src);m=json.loads((V18/'release/compact/decoder.json').read_text());out=Path(a.out) if a.out else ROOT/a.name
 d['ww10']=np.load(V18/'release/compact/training.npz')['ww10']
 if a.wav:
  out.mkdir(exist_ok=True,parents=True);cached=out/'baseline_model.npz';d=dict(np.load(cached)) if a.reuse_baseline and cached.exists() else new_baseline(d,load_wav(a.wav),m,a.bps);np.savez(cached,**d)
 yy,ov=decode(d,d['idx']);assert np.array_equal(yy,d['y']) and not ov
 study(d,m,out,a.passes)
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Rate-distortion search using context Huffman *bit costs*; host packing.
The exact integer LPC and existing PWM tables are unchanged. ROM builder can
expand the tokens, but a native Huffman bit reader is not implemented here.
"""
from harmonic import *
from numba import njit
from scipy.ndimage import uniform_filter1d
from study_pitch import step,grads
@njit(cache=True)
def search(t,tb,bk,bm,lens,alt,ab,active,th,q,w,wd,wl,pen,extra,qid,width,ctx,ll):
 n=len(t);best=np.full((n+1,width),1e30);hist=np.zeros((n+1,width,6),np.int16);ids=np.full((n+1,width),-1,np.int16);prev=np.zeros((n+1,width),np.uint8);best[0,0]=0;h=np.empty(6,np.int16)
 for p in range(n):
  for j in range(width):
   if best[p,j]>1e29:break
   old=q[hist[p,j,0]+512]-t[p-1] if p else 0.
   c=ctx[ids[p,j]] if p else 0
   cont=hist[p,j,0]>=th or hist[p,j,0]<-th
   for k in range(len(lens)):
    ln=lens[k];end=p+ln
    if end>n:continue
    err=best[p,j]+pen*ll[c,k]
    if err>=best[end,width-1]:continue
    h[:]=hist[p,j];pe=old;ok=True;use=cont and active[k];bank=ab[k] if use else bm[k];vec=alt[k] if use else bk[k]
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
     if ctx[k]!=ctx[ids[end,k2]]:continue
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

def size_bits(ix,ctx,ll):
 return int(ll[np.r_[0,ctx[ix[:-1]]],ix].sum())

def run(name):
 out=HERE/name;out.mkdir(exist_ok=True);d=model(ROOT/name/'training.npz');m=json.loads((V18/'release/compact/decoder.json').read_text());base,pt,r,z,u,v=inspect(d,d['y'],m);ix0=d['idx'];budget=len(ix0);t=d['target'];n=len(t);lev,qi,q=qtables(d,m);old=q[d['y']+512];ctx,ll=prefix.train(ix0,d['lens'],1);gr,gt,_=grads(d,d['y'],m);gr=np.pad(gr,(0,max(0,n-len(gr))))[:n];gt=np.pad(gt,(0,max(0,n-len(gt))))[:n]
 # Refit the base code lengths only after encoding. All size tests use the actual packed bytes.
 log=[];all_candidates=[];best=(base,ix0.copy(),d['y'].copy());maxbytes=budget
 def measure(ix,tag):
  nonlocal best
  yy,ov=decode(d,ix)
  if ov:return None
  b=pack(d,ix,256,[],1);mm,_,rr,zz,uu,vv=inspect(d,yy,m,pt);rec=dict(tag=tag,bytes=len(b),tokens=len(ix),kbps=len(b)*8*FS/n/1000,**mm);log.append(rec);print('CAND',rec,flush=True)
  if len(b)<=maxbytes and mm['snr']>=best[0]['snr'] and mm['stoi']>=best[0]['stoi']:
   best=(mm,ix.copy(),yy.copy());f.audio(out/'entropy.wav',rr,zz);(out/'entropy.ph20').write_bytes(b);np.savez(out/'entropy_training.npz',**dict(d,idx=ix,y=yy));print('ACCEPT',tag,flush=True)
  return rec,uu,vv
 for ex,hi,trust,sw in [(.2,.35,1.5,.7),(.4,.5,2.5,1.0),(.1,.2,1.,.5)]:
  w=(uniform_filter1d(t*t,156)+12.)**(-ex);w/=w.mean();delta=lev[None,:]-old[:,None];extra=((.2*gr-sw*gt)[:,None]*delta+trust*w[:,None]*delta**2);extra-=extra.min(1,keepdims=True);extra=extra.astype(np.float32);del delta
  # Seed lambda from v19 typical 56 penalty per byte; extra trust raises the cost.
  lam=7.0*(1+trust);goal=budget;lo=None;hh=None
  for it in range(3):
   a=search(t,d['tb'],d['bk'],d['bm'],d['lens'],d['alt'],d['ab'],d['active'],int(d['threshold']),q,w,w*hi,w*.1,lam,extra,qi,2,ctx,ll)
   res=measure(a,['full',ex,hi,trust,sw,lam]);
   if res is None:break
   rec,uu,vv=res;all_candidates.append((a,rec,uu,vv));ratio=rec['bytes']/goal
   if abs(ratio-1)<.008:break
   if ratio>1:lo=(lam,ratio)
   else:hh=(lam,ratio)
   if lo and hh:
    k=np.clip(np.log(lo[1])/max(1e-9,np.log(lo[1]/hh[1])),.12,.88);lam=np.exp((1-k)*np.log(lo[0])+k*np.log(hh[0]))
   else:lam*=np.clip(ratio**2.4,.4,2.5)
  del extra
 # Global choice of patches. Because candidates have different block boundaries,
 # only replace ranges whose exact sample positions coincide. Evaluate full signal.
 refpos=np.r_[0,np.cumsum(d['lens'][ix0])];baseerr=(u-v)**2;choices=[]
 for k,(ix,rec,uu,vv) in enumerate(all_candidates):
  pp=np.r_[0,np.cumsum(d['lens'][ix])];shared,ib,ic=np.intersect1d(refpos,pp,return_indices=True);ee=(uu-vv)**2
  for p in range(0,n,round(FS*.35)):
   l,r=np.searchsorted(shared,[p,min(n,p+round(FS*.35))]);r=min(len(shared)-1,r);l=min(l,r)
   if r<=l:continue
   p0,p1=shared[[l,r]];i0,i1=ib[[l,r]];j0,j1=ic[[l,r]]
   if p1-p0<80:continue
   gain=float(np.sum(baseerr[p0:p1]-ee[p0:p1]));dv=size_bits(ix[j0:j1],ctx,ll)-size_bits(ix0[i0:i1],ctx,ll)
   if gain>0:choices.append((gain,dv,int(i0),int(i1),ix[j0:j1].copy(),k))
 choices.sort(key=lambda x:-x[0]/max(1,1+x[1]/32));selected=[];used=set();basebytes=len(pack(d,ix0,256,[],1));freebits=(budget-basebytes)*8-64
 for gain,dv,i0,i1,x,k in choices:
  if any(i in used for i in range(i0,i1)) or dv>freebits:continue
  selected.append((gain,dv,i0,i1,x,k));used.update(range(i0,i1));freebits-=dv
  if len(selected)>=60:break
 print('PATCH POOL',len(selected),freebits,flush=True)
 accepted=[]
 def splice(s):
  a=[];p=0
  for _,_,l,r,x,k in sorted(s,key=lambda z:z[2]):a.extend([ix0[p:l],x]);p=r
  a.append(ix0[p:]);return np.concatenate(a)
 # Retain patches only if full metrics and real serialized length improve.
 def trial(s):
  if not s:return
  before=best[0].copy();res=measure(splice(accepted+s),['patch',[(a[2],a[3],a[5]) for a in s]])
  if res is not None and best[0]!=before:accepted.extend(s)
  elif len(s)>1:
   k=len(s)//2;trial(s[:k]);trial(s[k:])
 for k in range(0,len(selected),8):trial(selected[k:k+8])
 (out/'entropy.json').write_text(json.dumps(dict(baseline=base,base_bytes=budget,best=best[0],best_tokens=len(best[1]),best_packed_bytes=len(pack(d,best[1],256,[],1)),trials=log),indent=2));print('FINAL',name,best[0],len(best[1]),len(pack(d,best[1],256,[],1)),flush=True)
if __name__=='__main__':run(sys.argv[1])

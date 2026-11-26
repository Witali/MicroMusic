#!/usr/bin/env python3
"""Local bit allocation: preserve past LPC state; count exact packed bytes.
Only expanded token ROM is supported on Z80. No native Huffman decoder yet."""
from harmonic import *
from study_pitch import grads,step
from entropy_search import size_bits
from local_kernel import local_search
from numba import njit
from scipy.ndimage import uniform_filter1d
@njit(cache=True)
def local_decode(dtb,bk,bm,lens,alt,ab,active,th,ix,initial):
 h=initial.copy();y=np.empty(np.sum(lens[ix]),np.int16);p=0;over=0
 for k in ix:
  use=active[k] and (h[0]>=th or h[0]<-th);b=ab[k] if use else bm[k];vec=alt[k] if use else bk[k]
  for j in range(lens[k]):
   v,ov=step(h,dtb[b],vec[j],10);y[p]=v;p+=1;over+=ov
 return y,over

def run(name):
 out=HERE/name;d=model(ROOT/name/'training.npz');m=json.loads((V18/'release/compact/decoder.json').read_text());base,pt,r,z,u,v=inspect(d,d['y'],m);ix0=d['idx'];budget=len(ix0);t=d['target'];n=len(t);lev,qi,q=qtables(d,m);old=q[d['y']+512];ctx,ll=prefix.train(ix0,d['lens'],1);gr,gt,_=grads(d,d['y'],m);gr=np.pad(gr,(0,max(0,n-len(gr))))[:n];gt=np.pad(gt,(0,max(0,n-len(gt))))[:n];pos=np.r_[0,np.cumsum(d['lens'][ix0])];error=(u-v)**2;choices=[];windows=[];log=[]
 for p in range(0,n,1536):
  i,j=np.searchsorted(pos,[p,min(n,p+1536)]);j=min(j,len(ix0));i=min(i,j)
  if i==j:continue
  a,b=pos[[i,j]];windows.append((float(error[a:b].sum()),int(i),int(j)))
 # Concentrate compute on the worst 36 windows, and generate two alternatives
 # with different distortion / rate tradeoffs. Full-decode acceptance below.
 for _,i,j in sorted(windows,reverse=True)[:36]:
  a,b=pos[[i,j]];h=np.zeros(6,np.int16)
  for k in range(6):
   if a>k:h[k]=d['y'][a-k-1]
  ct=ctx[ix0[i-1]] if i else 0;s=slice(a,b);w=(uniform_filter1d(t[s]*t[s],min(156,b-a))+12)**(-.2);w/=w.mean();delta=lev[None,:]-old[s,None]
  extra=((.6*gr[s]-.8*gt[s])[:,None]*delta+1.5*w[:,None]*delta**2);extra-=extra.min(1,keepdims=True);extra=extra.astype(np.float32)
  for lam in (2.5,6.):
   ix=local_search(t[s],d['tb'],d['bk'],d['bm'],d['lens'],d['alt'],d['ab'],d['active'],int(d['threshold']),q,w,w*.35,w*.08,lam,extra,qi,2,ctx,ll,h,ct);yy,ov=local_decode(d['tb'],d['bk'],d['bm'],d['lens'],d['alt'],d['ab'],d['active'],int(d['threshold']),ix,h)
   if ov or len(yy)!=b-a:continue
   dx=q[yy+512]-old[s];de=float(np.sum((u[s]-v[s])**2-(u[s]-v[s]-dx*base['gain']/127)**2));ds=float(gt[s]@dx);db=size_bits(ix,ctx,ll)-size_bits(ix0[i:j],ctx,ll)
   if de>0:choices.append((de,ds,db,i,j,ix,lam))
  print('WINDOW',i,j,len(choices),flush=True)
 # Rank by SNR, favor predicted intelligibility, but exact whole-wave metrics
 # are authoritative. Preserve old file if no patch passes.
 choices.sort(key=lambda o:-(o[0]/max(1,1+o[2]/50))*(1.0 if o[1]>=0 else .7));selected=[];used=set();free=(budget-len(pack(d,ix0,256,[],1)))*8-32
 for c in choices:
  de,ds,db,i,j,ix,lam=c
  if db>free or any(k in used for k in range(i,j)):continue
  selected.append(c);used.update(range(i,j));free-=db
 print('SELECT',len(selected),free,flush=True)
 accepted=[];best=base.copy();bestix=ix0.copy()
 def try_group(gp):
  nonlocal best,bestix
  if not gp:return
  parts=[];p=0
  for _,_,_,i,j,ix,_ in sorted(accepted+gp,key=lambda c:c[3]):parts.extend([ix0[p:i],ix]);p=j
  parts.append(ix0[p:]);ix=np.concatenate(parts);b=pack(d,ix,256,[],1)
  if len(b)<=budget:
   yy,ov=decode(d,ix)
   if not ov:
    met,_,rr,zz,*_=inspect(d,yy,m,pt);rec=dict(patches=[(c[3],c[4],c[6]) for c in gp],bytes=len(b),tokens=len(ix),**met);log.append(rec);print('TRY',rec,flush=True)
    if met['snr']>=best['snr'] and met['stoi']>=best['stoi']:
     accepted.extend(gp);best=met;bestix=ix;f.audio(out/'local.wav',rr,zz);np.savez(out/'local_training.npz',**dict(d,idx=ix,y=yy));(out/'local.ph20').write_bytes(b);return
  if len(gp)>1:
   k=len(gp)//2;try_group(gp[:k]);try_group(gp[k:])
 for k in range(0,len(selected),5):try_group(selected[k:k+5])
 result=dict(base=base,best=best,tokens=len(bestix),packed_bytes=len(pack(d,bestix,256,[],1)),base_tokens=len(ix0),accepted=len(accepted),trials=log);(out/'local.json').write_text(json.dumps(result,indent=2));print('FINAL',name,result['best'],result['tokens'],result['packed_bytes'],result['accepted'],flush=True)
if __name__=='__main__':run(sys.argv[1])

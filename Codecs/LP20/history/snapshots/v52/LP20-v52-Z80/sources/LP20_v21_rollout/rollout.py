#!/usr/bin/env python3
"""Fixed-byte LP20 encoder refinement. Exact context-aware LPC rollout, unchanged ROM model."""
import os,sys,json,time,argparse
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent/'LP20_v20_study'))
from harmonic import *
HERE=Path(__file__).resolve().parent
from study_pitch import grads,step
from noise_study import Mask
from numba import njit
from scipy.ndimage import uniform_filter1d

@njit(cache=True,inline='always')
def token(h,k,p,tb,bk,bm,lens,alt,ab,active,th,q,old,g,w,trust,prev):
 use=active[k] and (h[0]>=th or h[0]<-th);b=ab[k] if use else bm[k];vec=alt[k] if use else bk[k];s=0.
 for z in range(lens[k]):
  v,ov=step(h,tb[b],vec[z],10)
  if ov:return 1e30,prev
  j=p+z;dx=q[v+512]-old[j];s+=g[j]*dx+trust*w[j]*(.82*dx*dx+.18*(.65*dx+.35*prev)**2);prev=dx
 return s,prev

@njit(cache=True)
def continuation(h,ix,loc,j,end,tb,bk,bm,lens,alt,ab,active,th,q,old,g,w,trust,prev,y):
 s=0.
 while j<len(ix) and loc[j]<end:
  same=loc[j]>=6 and prev==0
  if same:
   for z in range(6):
    if h[z]!=y[loc[j]-1-z]:same=False;break
  if same:break
  val,prev=token(h,ix[j],loc[j],tb,bk,bm,lens,alt,ab,active,th,q,old,g,w,trust,prev);s+=val
  if s>1e29:return s
  j+=1
 if j<len(ix):
  for z in range(6):
   if loc[j]>z:s+=.02*(float(h[z])-float(y[loc[j]-z-1]))**2
 return s

@njit(cache=True)
def propose(ix,loc,y,tb,bk,bm,lens,alt,ab,active,th,q,old,g,w,trust,tail,swaps,top):
 N=len(ix);score=np.zeros(N);a=ix.copy();b=np.full(N,-1,np.int16);ends=np.zeros(N,np.int32)
 init=np.zeros(6,np.int16);h=np.empty(6,np.int16);h2=np.empty(6,np.int16)
 for i in range(N):
  p=loc[i];orig=ix[i];ln=lens[orig];lim=loc[i+1]+tail
  for z in range(6):init[z]=y[p-z-1] if p>z else 0
  best=0.;bestk=orig;bestb=-1;end=lim
  for k in range(len(lens)):
   if k==orig or lens[k]!=ln:continue
   h[:]=init;s,prev=token(h,k,p,tb,bk,bm,lens,alt,ab,active,th,q,old,g,w,trust,0.)
   if s>1e29:continue
   s+=continuation(h,ix,loc,i+1,lim,tb,bk,bm,lens,alt,ab,active,th,q,old,g,w,trust,prev,y)
   if s<best:best=s;bestk=k;bestb=-1
  if swaps and i+1<N and ln!=lens[ix[i+1]] and ln+lens[ix[i+1]]<=40:
   ln2=lens[ix[i+1]];cost=np.full(top,1e30);short=np.full(top,-1,np.int16);pr=np.zeros(top);states=np.zeros((top,6),np.int16)
   for k in range(len(lens)):
    if lens[k]!=ln2:continue
    h[:]=init;s,prev=token(h,k,p,tb,bk,bm,lens,alt,ab,active,th,q,old,g,w,trust,0.)
    if s>=cost[-1]:continue
    j=top-1
    while j>0 and s<cost[j-1]:
     cost[j]=cost[j-1];short[j]=short[j-1];states[j]=states[j-1];pr[j]=pr[j-1];j-=1
    cost[j]=s;short[j]=k;states[j]=h;pr[j]=prev
   for j in range(top):
    if short[j]<0:break
    for k in range(len(lens)):
     if lens[k]!=ln:continue
     h2[:]=states[j];s,prev=token(h2,k,p+ln2,tb,bk,bm,lens,alt,ab,active,th,q,old,g,w,trust,pr[j]);s+=cost[j]
     if s>1e29:continue
     lim2=loc[i+2]+tail
     s+=continuation(h2,ix,loc,i+2,lim2,tb,bk,bm,lens,alt,ab,active,th,q,old,g,w,trust,prev,y)
     if s<best:best=s;bestk=short[j];bestb=k;end=lim2
  score[i]=best;a[i]=bestk;b[i]=bestb;ends[i]=end
 return score,a,b,ends

def run(name,passes,resume=False):
 source=HERE.parent/'LP20_v20_study'/name/'entropy_training.npz' if name=='first' else ROOT/name/'training.npz'
 out=HERE/name;out.mkdir(exist_ok=True);d=model(source);m=json.loads((V18/'release/compact/decoder.json').read_text());lev,qi,q=qtables(d,m);base,pt,r,z,u,v=inspect(d,d['y'],m);n=len(d['y']);mask=Mask(u);base.update(mask.analyze(v));best=base.copy();ix=d['idx'].copy();y=d['y'].copy();budget=len(ix);log=[];print('BASE',name,base,budget,flush=True)
 if resume:
  previous=json.loads((out/'results.json').read_text());checkpoint=model(out/'training.npz');ix=checkpoint['idx'].copy();y=checkpoint['y'].copy();best=previous['best'];log=previous['trials'];offset=1+max([x['iteration'] for x in log],default=-1)
 else:
  f.audio(out/'baseline.wav',r,z);offset=0
 def save():
  np.savez(out/'training.npz',**dict(d,idx=ix,y=y));(out/'results.json').write_text(json.dumps(dict(source=str(source.relative_to(HERE.parent)),base=base,best=best,tokens=budget,kbps=budget*8*FS/n/1000,trials=log),indent=2));mm,_,rr,zz,*_=inspect(d,y,m,pt);f.audio(out/'v21.wav',rr,zz)
 save()
 for it in range(offset,offset+passes):
  gr,gt,_=grads(d,y,m);gr=np.pad(gr,(0,max(0,n-len(gr))))[:n];gt=np.pad(gt,(0,max(0,n-len(gt))))[:n];_,_,_,_,u,v=inspect(d,y,m,pt);_,mg=mask.analyze(v,True);_,pg=pitch.cost(pt,v-u,True)
  rms=lambda x:np.sqrt(np.mean(x*x)+1e-30)
  mg*=rms(gr)/rms(mg);pg*=rms(gr)/rms(pg)
  old=q[y+512];loc=np.r_[0,np.cumsum(d['lens'][ix])];w=(uniform_filter1d(d['target']**2,156)+12)**(-.12);w/=w.mean();t0=time.time()
  sw,mw,pw,trust,swap=[(.12,.12,.1,1.8,False),(.15,.15,.12,1.8,True),(.25,.25,.2,1.3,True),(.4,.15,.2,2.,False),(.1,.2,.1,1.2,True)][it%5]
  g=gr-sw*gt+mw*mg+pw*pg
  scores,aa,bb,ends=propose(ix,loc,y,d['tb'],d['bk'],d['bm'],d['lens'],d['alt'],d['ab'],d['active'],int(d['threshold']),q,old,g,w,trust,64,swap,2)
  chosen=[];occupied=np.zeros(n+128,bool)
  for i in np.argsort(scores):
   if scores[i]>=-1e-6:break
   a0=int(loc[i]);b0=min(n,int(ends[i])+int(d['lens'].max()))
   if np.any(occupied[max(0,a0-6):b0]):continue
   occupied[max(0,a0-6):b0]=True;chosen.append(int(i))
  print('PROPOSE',it,len(chosen),'scores',float(scores.min()),'time',time.time()-t0,flush=True)
  def attempt(group,tag):
   nonlocal ix,y,best
   if not group:return False
   jj=ix.copy()
   for i in group:
    jj[i]=aa[i]
    if bb[i]>=0:jj[i+1]=bb[i]
   yy,ov=decode(d,jj)
   if ov or len(yy)!=n:return False
   mm,_,rr,zz,uu,vv=inspect(d,yy,m,pt);mm.update(mask.analyze(vv));ok=mm['snr']>=best['snr']-1e-9 and mm['stoi']>=best['stoi']-1e-9 and mm['periodic_error']<=best['periodic_error']+1e-9 and mm['masked_error']<=best['masked_error']+1e-9 and mm['voiced_high_error']<=best['voiced_high_error']+1e-9
   rec=dict(iteration=it,tag=tag,patches=len(group),swaps=int(sum(bb[i]>=0 for i in group)),accepted=bool(ok),**mm);log.append(rec);print('TRY',rec,flush=True)
   if ok:ix=jj;y=yy;best=mm;save();return True
   return False
  # The cheap surrogate is not an exact PWM error: measure the actual
  # full decoded candidate and isolate improvements by local output region.
  jj=ix.copy()
  for i in chosen:
   jj[i]=aa[i]
   if bb[i]>=0:jj[i+1]=bb[i]
  yy,ov=decode(d,jj)
  if not ov and chosen:
   mm,_,rr,zz,uu,vv=inspect(d,yy,m,pt)
   # Fix local comparison to the previous global gain (delay unchanged).
   if mm['delay']==best['delay']:
    vv=vv*best['gain']/mm['gain'];e=v-u;ee=vv-u;de=e*e-ee*ee
    ep=e-pitch.pred(pt,e);en=ee-pitch.pred(pt,ee);dp=pt['weight']*(ep*ep-en*en)
    # STFT metric difference at each frame; center assignment for ranking only.
    from numpy.lib.stride_tricks import sliding_window_view as sliding
    a=np.abs(np.fft.rfft((sliding(v,256)[::64][:len(mask.frames)]-mask.frames)*__import__('noise_study').WIN))**2
    b0=np.abs(np.fft.rfft((sliding(vv,256)[::64][:len(mask.frames)]-mask.frames)*__import__('noise_study').WIN))**2
    dm=(a-b0)*mask.weights;mh=np.zeros(n);vh=np.zeros(n);cent=mask.starts+128;mh[cent]=dm.sum(1);vh[cent]=(a-b0)[:,mask.voicefreq].sum(1)*mask.voiced
    # Region boundaries lie midway between consecutive edits. This avoids double counting.
    order=sorted(chosen,key=lambda i:loc[i]);cuts=[0]+[int((loc[i]+loc[j])//2) for i,j in zip(order[:-1],order[1:])]+[n];good=[];rank=[]
    for k,i in enumerate(order):
     l,h=cuts[k:k+2];l=max(l,int(loc[i])-128);h=min(h,int(ends[i])+256);sl=slice(l,h)
     ds=float(de[sl].sum());ps=float(dp[sl].sum());ms=float(mh[sl].sum());hs=float(vh[sl].sum());st=float(gt[sl]@(q[yy[sl]+512]-old[sl]));rank.append((i,ds,ps,ms,hs,st))
     if ds>0 and ps>=-1e-9 and ms>=-1e-9 and hs>=-1e-9:good.append(i)
    print('ACTUAL',len(good),'of',len(chosen), 'positive SSE',sum(z[1]>0 for z in rank),flush=True)
    # First try all locally positive changes; if STOI falls, require positive proxy.
    # Optimize the combined measured improvements with an explicit global
    # budget of each error metric, rather than requiring every patch to
    # independently improve every metric. Full decode remains authoritative.
    accepted_global=False
    if resume and rank:
     from scipy.optimize import milp,Bounds,LinearConstraint
     arr=np.asarray([r[1:] for r in rank],float).T
     # Normalize objective and constraints to the candidate pool's scale.
     scale=np.maximum(np.sum(np.maximum(arr,0),axis=1),1e-20);A=arr/scale[:,None]
     for weights in ([1.,.4,.45,.35,.12],[.5,.3,1.,.8,.2],[1.,.1,.15,.15,.35]):
      # Predicted local contributions are approximate; impose a margin
      # for STOI, and require nonnegative aggregate error reductions.
      c=-np.array(weights)@A;floor=np.array([0.,0.,0.,0.,.01]);res=milp(c,integrality=np.ones(len(rank)),bounds=Bounds(0,1),constraints=LinearConstraint(A,floor,np.inf),options={'time_limit':2.0,'mip_rel_gap':.03})
      if res.x is None:continue
      gp=[rank[j][0] for j in range(len(rank)) if res.x[j]>.5]
      print('GLOBAL',it,len(gp),'predicted',A[:,res.x>.5].sum(1).tolist(),flush=True)
      if attempt(gp,'global measured allocation'):
       accepted_global=True;break
    if not accepted_global and not attempt(good,'measured positive'):
     shortlist=[i for i,ds,ps,ms,hs,st in rank if i in good and st>=0]
     if not attempt(shortlist,'measured positive + STOI'):
      for k in range(0,len(good),max(1,len(good)//4)):attempt(good[k:k+max(1,len(good)//4)],'measured subgroup')
   else:attempt(chosen,'all, changed delay')
  save()
 print('FINAL',name,best,flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('name',choices=['first','second']);p.add_argument('--passes',type=int,default=3);p.add_argument('--resume',action='store_true');a=p.parse_args();run(a.name,a.passes,a.resume)

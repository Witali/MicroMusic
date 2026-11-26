"""Fractional duty patterns, 10 balanced pulse widths per sample. Train a
static 61-pattern quantizer. Model the actual per-period widths; measure on
the same 3.5 kHz filtered reference as v8. No runtime error accumulator.
"""
import study as s
import numpy as np, json, sys, math, time
from scipy.signal import resample_poly
from pathlib import Path
from functools import lru_cache
from precision_study import FS
import opt_build as b, build_h10 as h

@lru_cache(None)
def pattern(w10):
 w10=int(w10)
 if w10<1280:return tuple(256-v for v in pattern(2560-w10))
 lo,r=divmod(w10,10)
 # Centered Bresenham distribution; maximum difference 1 T.
 return tuple(lo+((i+1)*r+5)//10-(i*r+5)//10 for i in range(10))

def schedule_pattern(a,period,pat,stack=False):
 slots=[q for w in pat for q in (w-12,period-w-12)];ts=[0]
 for t,_,_ in a:ts.append(ts[-1]+t)
 tail=np.cumsum(slots[::-1])[::-1]
 @lru_cache(None)
 def rec(k,i):
  if k==len(slots):return () if i==len(a) else None
  if ts[-1]-ts[i]>tail[k]:return None
  js=[len(a)] if k==len(slots)-1 else range(len(a)-1,i-1,-1)
  for j in js:
   if j<i:continue
   p=b.pad(slots[k]-(ts[j]-ts[i]),stack)
   if p is None:continue
   r=rec(k+1,j)
   if r is not None:return ((i,j,p),)+r
  return None
 return rec(0,0)

def lut10(ww10):
 return np.array([min(ww10,key=lambda w:(abs(w-(1280+v*1120/512)),abs(w-1280))) for v in range(-512,512)],dtype=np.int32)

def render(y,ww10):
 w=lut10(ww10)[y+512];vals,inv=np.unique(w,return_inverse=True);p=np.array([pattern(int(v)) for v in vals],dtype=np.int16)[inv].ravel();z=(np.clip(p[:,None]-np.arange(4)*64,0,64).astype(np.float32)*2/64-1).ravel()
 return s.e.lp(resample_poly(z,96,625),7000)/.875*128/127

def measure(t,y,ww10):
 return s.e.align_metric(s.e.lp(resample_poly(t/127,768,125),3500),s.e.lp(render(y,ww10),3500))

def save(tag,d,ww10,m):
 p=s.ROOT/'results'/tag;p.mkdir(parents=True,exist_ok=True);np.savez(p/'training.npz',**dict(d,ww10=np.array(ww10,dtype=np.int16)));r=resample_poly(d['target']/127,768,125);z=render(d['y'],ww10);g=.98/max(abs(r));s.e.wav(p/'reference.wav',r*g);s.e.wav(p/'pwm.wav',z*g*min(1,.98/(max(abs(z))*g)));(p/'metrics.json').write_text(json.dumps(m,indent=2));return p

def run(src,tag):
 d=dict(np.load(src));t=d['target'];y=d['y'];ww=d['ww'];old=ww*10;base=measure(t,y,old);oldm=s.measure(t,y,ww);assert abs(base['snr']-oldm['snr'])<1e-6 and abs(base['stoi']-oldm['stoi'])<1e-6;print('BASE',base,flush=True)
 _,ol,_=s.lut_for(ww);g4,score=s.fb.grad_pwm(t,y,ol);g4*=len(t)
 # Fine candidates near zero and all previous integer widths. Some extreme
 # fractional patterns cannot schedule; their exact machine timings are
 # checked before acceptance, with a fallback to integer duty.
 half=np.unique(np.r_[np.arange(0,201,1),np.arange(205,501,5),np.arange(510,1121,10),(ww[ww>=128]-128)*10]);N=len(half);qv=np.arange(513)*1120/512.;ids=np.abs(y.astype(int));sg=np.where(y<0,-1.,1.);cnt=np.bincount(ids,minlength=513);xy=np.bincount(ids,weights=t*sg,minlength=513)
 gp=np.zeros((513,4));gn=gp.copy();np.add.at(gp,ids[y>=0],g4[y>=0]);np.add.at(gn,ids[y<0],g4[y<0]);wp=np.array([np.mean(np.clip(np.array(pattern(1280+int(v)))[:,None]-np.arange(4)*64,0,64)/32.-1.,axis=0) for v in half]);wn=np.array([np.mean(np.clip(np.array(pattern(1280-int(v)))[:,None]-np.arange(4)*64,0,64)/32.-1.,axis=0) for v in half]);grad=gp@wp.T+gn@wn.T
 oldlev=np.array([abs(ol[min(v,511)+512]-128)*128./112 for v in range(513)]);oldlev[512]=128;a=half*128./1120*base['gain'];u=half*128./1120;v=np.arange(513)/4.;acts=h.fix_actions(h.actions());
 # Precompute the nearest assignment boundaries for pairwise DP costs.
 l=np.searchsorted(qv,half,side='left');mid=np.searchsorted(qv,(half[:,None]+half[None,:])/2,side='right');ii,jj=np.triu_indices(N,1);K=len(ww)//2+1;best=base;bestw=old;log=[]
 for alpha,trust,refmix in ((0,.0,0),(0,.15,.25),(.15,.2,.25),(.5,.15,.25),(1.,.2,.4),(.5,.5,.6),(2.,.2,.4),(0,0,1.0)):
  # refmix = convex mix of original-target distortion and PCM quantizer
  # distortion. The STOI term is a first-order filtered-wave estimate.
  cost=(1-refmix)*(cnt[:,None]*a[None,:]**2-2*xy[:,None]*a[None,:])+refmix*cnt[:,None]*(u[None,:]-v[:,None])**2-alpha*grad+trust*cnt[:,None]*(u[None,:]-oldlev[:,None])**2
  prefix=np.vstack([np.zeros(N),np.cumsum(cost,axis=0)]);C=np.full((N,N),np.inf);k=mid[ii,jj];C[ii,jj]=prefix[k,ii]-prefix[l[ii],ii]+prefix[l[jj],jj]-prefix[k,jj]
  dp=np.full((K,N),np.inf);prev=np.zeros((K,N),int);dp[0,0]=0
  for i in range(1,K):
   z=dp[i-1,:,None]+C;prev[i]=z.argmin(0);dp[i]=z.min(0)
  j=N-1;sel=[j]
  for i in range(K-1,0,-1):j=prev[i,j];sel.append(j)
  hh=half[sel[::-1]];new=np.r_[1280-hh[:0:-1],1280+hh];assert len(new)==len(ww) and new[0]==160 and new[-1]==2400 and len(set(new))==len(new)
  m=measure(t,y,new);ok=m['snr']>=best['snr'] and m['stoi']>best['stoi'];rec=dict(alpha=alpha,trust=trust,refmix=refmix,**m,widths10=new.tolist(),accepted=False);print('TRIAL',alpha,trust,refmix,m,'pareto',ok,flush=True)
  if ok:
   bad=[int(w) for w in new if schedule_pattern(acts,256,pattern(int(w))) is None];rec['unscheduled']=bad
   if not bad:best,bestw=m,new;rec['accepted']=True;save(tag,d,bestw,dict(**m,bytes=len(d['idx']),kbps=len(d['idx'])*8/(len(t)/FS)/1000))
  log.append(rec)
 best.update(bytes=len(d['idx']),kbps=len(d['idx'])*8/(len(t)/FS)/1000,overflow=0);save(tag,d,bestw,best);(s.ROOT/'logs'/(tag+'.json')).write_text(json.dumps(dict(baseline=base,final=best,trials=log),indent=2));print('FINAL',best,'fractional levels',int(np.sum(bestw%10!=0)),flush=True)
if __name__=='__main__':run(*sys.argv[1:])

"""Train the static symmetric PWM width table for an already reconstructed
stream. Uses actual filtered-PWM STOI gradient, constrained nearest width,
fixed endpoints and 61 levels. This is NOT runtime noise shaping."""
import study as s
import numpy as np,json,sys,time
from precision_study import FS
from pathlib import Path

def run(src,tag):
 d=dict(np.load(src));t=d['target'];y=d['y'];ww=d['ww'];base=s.measure(t,y,ww);best=base;bestw=ww;print('BASE',base,flush=True)
 _,oldlut,_=s.lut_for(ww);g4,score=s.fb.grad_pwm(t,y,oldlut);g4*=len(t)
 # All feasible pulse widths, from exact instruction schedule.
 import opt_build as b,build_h10 as h
 acts=h.fix_actions(h.actions());good=[w for w in range(16,241) if b.schedule(acts,256,10,w,False) is not None];good=sorted(set(good)&{256-w for w in good});half=np.array([w-128 for w in good if w>=128]);assert half[0]==0 and half[-1]==112
 ids=np.abs(y.astype(int));sg=np.where(y<0,-1.,1.);cnt=np.bincount(ids,minlength=513);xy=np.bincount(ids,weights=t*sg,minlength=513);oldamp=np.abs(oldlut[y+512]-128)*128./112
 # Sum physical STOI gradient by signed decoder state.
 gp=np.zeros((513,4));gn=gp.copy();np.add.at(gp,ids[y>=0],g4[y>=0]);np.add.at(gn,ids[y<0],g4[y<0]);wp=np.clip((128+half[:,None])-np.arange(4)*64,0,64)/32.-1.;wn=np.clip((128-half[:,None])-np.arange(4)*64,0,64)/32.-1.;grad=gp@wp.T+gn@wn.T
 # Quadratic approximation in amplitude; retain the old quantizer as a trust centre.
 gain=base['gain'];a=half*128./112*gain;oldlev=np.array([abs(oldlut[min(v,511)+512]-128)*128./112 for v in range(513)]);oldlev[512]=112*128/112
 N=len(half);qv=np.arange(513)*112./512;log=[]
 for alpha,trust in ((0.,0.),(.2,.2),(.6,.4),(1.2,.7),(2.,1.0),(.8,2.)):
  cost=cnt[:,None]*a[None,:]**2-2*xy[:,None]*a[None,:]-alpha*grad+trust*cnt[:,None]*(a[None,:]-oldlev[:,None])**2
  # Each adjacent pair determines the nearest-width assignment between them.
  C=np.full((N,N),np.inf);prefix=np.vstack([np.zeros(N),np.cumsum(cost,axis=0)])
  for i in range(N-1):
   for j in range(i+1,N):
    l=np.searchsorted(qv,half[i],side='left');r=np.searchsorted(qv,half[j],side='left');k=np.searchsorted(qv,(half[i]+half[j])/2,side='right');C[i,j]=prefix[k,i]-prefix[l,i]+prefix[r,j]-prefix[k,j]
  K=len(ww)//2+1;dp=np.full((K,N),np.inf);prev=np.zeros((K,N),int);dp[0,0]=0
  for i in range(1,K):
   for j in range(i,N):
    z=dp[i-1,:j]+C[:j,j];p=z.argmin();dp[i,j]=z[p];prev[i,j]=p
  j=N-1;sel=[j]
  for i in range(K-1,0,-1):j=prev[i,j];sel.append(j)
  hh=half[sel[::-1]];new=np.r_[128-hh[:0:-1],128+hh];assert len(new)==len(ww)
  m=s.measure(t,y,new);ok=m['snr']>=best['snr'] and m['stoi']>best['stoi'];log.append(dict(alpha=alpha,trust=trust,widths=new.tolist(),accepted=bool(ok),**m));print('TRIAL',alpha,trust,m,'accept',ok,flush=True)
  if ok:best,bestw=m,new
 best.update(bytes=len(d['idx']),kbps=len(d['idx'])*8/(len(t)/FS)/1000,overflow=0);s.save(tag,dict(d,ww=bestw),d['idx'],y,best);(s.ROOT/'logs'/(tag+'.json')).write_text(json.dumps(dict(baseline=base,final=best,trials=log),indent=2));print('FINAL',best,flush=True)
if __name__=='__main__':run(*sys.argv[1:])

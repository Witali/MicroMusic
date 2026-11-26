from study_v4 import *
from numba import njit
@njit(cache=True)
def shaped97(t,tb,bk,bm,lens,weights,penalty,beta):
 n=len(t);ord=tb.shape[1];best=np.full(n+1,1e30);hist=np.zeros((n+1,ord),np.int16);ids=np.full(n+1,-1,np.int16);prev=np.zeros(n+1,np.int32);best[0]=0;h=np.empty(ord,np.int16)
 for p in range(n):
  if best[p]>1e29:continue
  pe=0. if p==0 else c.qout(hist[p,0],48)-t[p-1]
  for k in range(len(lens)):
   ln=lens[k];j=p+ln
   if j>n:continue
   err=best[p]+penalty
   if err>=best[j]:continue
   h[:]=hist[p];old=pe
   for z in range(ln):
    y,wr=c.samp(h,tb[bm[k]],bk[k,z]);d=c.qout(y,48)-t[p+z];low=.65*d+.35*old;err+=weights[p+z]*((1-beta)*d*d+beta*low*low)+250000.*wr;old=d
    if err>=best[j]:break
   if err<best[j]:best[j]=err;hist[j]=h;ids[j]=k;prev[j]=p
 seq=np.empty(n,np.int16);cnt=0;i=n
 while i>0:
  assert ids[i]>=0;seq[cnt]=ids[i];cnt+=1;i=prev[i]
 return seq[:cnt][::-1].copy(),best[n]

if __name__=='__main__':
 d=np.load(ROOT/'hybrid_refined'/'training.npz');t,tb,bk,bm,lens=[d[k] for k in ('target','tb','bk','bm','lens')];w=(uniform_filter1d(t*t,156)+12)**(-.12);w/=w.mean();lam=20.;best=None;target=len(t)/FS*5000/8
 for it in range(3):
  ix,cost=shaped97(t,tb,bk,bm,lens,w,lam,.35);n=len(ix);print('125 search',lam,n,flush=True)
  if best is None or abs(n-target)<abs(len(best[0])-target):best=(ix.copy(),lam)
  if abs(n-target)<target*.012:break
  lam*=(n/target)**2.5
 ix,lam=best;y,h,over=reconstruct(t,tb,bk,bm,lens,ix);out=ROOT/'pwm125';out.mkdir(exist_ok=True);np.savez(out/'training.npz',target=t,tb=tb,bk=bk,bm=bm,lens=lens,idx=ix,y=y)
 e.FS=FS;e.PERIOD=160;e.PULSES=16;e.LEVELS=97;xr=resample_poly(t/127,768,125);z=e.render(y)/(2*48/160)*128/127;g=.98/max(abs(xr));m=e.align_metric(e.lp(xr,3500),e.lp(z,3500));m.update(bytes=len(ix),kbps=len(ix)*8/(len(t)/FS)/1000,overflows=int(over));print('125 metrics',m,flush=True);(out/'metrics.json').write_text(json.dumps(m,indent=2));e.wav(out/'pwm.wav',z*g*min(1,.98/(max(abs(z))*g)));e.wav(out/'reference.wav',xr*g)
 try:build_packed.build(str(out/'training.npz'),str(out/'decoder'),160,16,97,1)
 except ValueError as exc:print('ROM build',str(exc),flush=True)

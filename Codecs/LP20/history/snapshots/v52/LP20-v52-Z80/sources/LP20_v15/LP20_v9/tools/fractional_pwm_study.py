"""Offline fractional-duty experiment. The current ROM generator does NOT implement this schedule."""
from study_v4 import *
from math import gcd
from numba import njit
@njit(cache=True)
def search_pcm(t,tb,bk,bm,lens,w,pen):
 n=len(t);order=tb.shape[1];best=np.full(n+1,1e30);hist=np.zeros((n+1,order),np.int16);ids=np.full(n+1,-1,np.int16);prev=np.zeros(n+1,np.int32);best[0]=0.;h=np.empty(order,np.int16)
 for p in range(n):
  if best[p]>1e29:continue
  pe=0. if p==0 else hist[p,0]-t[p-1]
  for k in range(len(lens)):
   ln=lens[k];j=p+ln
   if j>n:continue
   err=best[p]+pen
   if err>=best[j]:continue
   h[:]=hist[p];old=pe
   for z in range(ln):
    y,wr=c.samp(h,tb[bm[k]],bk[k,z]);d=y-t[p+z];low=.65*d+.35*old;err+=w[p+z]*(.65*d*d+.35*low*low)+250000.*wr;old=d
    if err>=best[j]:break
   if err<best[j]:best[j]=err;hist[j]=h;ids[j]=k;prev[j]=p
 seq=np.empty(n,np.int16);cnt=0;i=n
 while i>0:
  assert ids[i]>=0;seq[cnt]=ids[i];cnt+=1;i=prev[i]
 return seq[:cnt][::-1].copy()

def render_fractional(y):
 # Floor/ceil pulse widths, uniformly distributed, constant carrier 128T.
 # All 20 pulses stay within 1T of one another for a given PCM sample.
 desired=64+y.astype(float)*38/128;total=np.rint(desired*20).astype(np.int32);i=np.arange(21,dtype=np.int32)
 edges=(total[:,None]*i[None,:]+10)//20;ww=np.diff(edges,axis=1).ravel();assert ww.min()>=26 and ww.max()<=102
 z=(np.clip(ww[:,None]-np.arange(4)*32,0,32).astype(np.float32)/16-1).ravel();g=gcd(48000*32,20000000);z=resample_poly(z,48000*32//g,20000000//g);return e.lp(z,7000)/(2*38/128)*128/127

def main(seed):
 d=np.load(seed);t,tb,bk,bm,lens,idx,y=[d[k] for k in ('target','tb','bk','bm','lens','idx','y')];out=ROOT/'fractional_pwm';out.mkdir(exist_ok=True);xr=resample_poly(t/127,768,125);r=e.lp(xr,3500);g=.98/max(abs(xr));q=np.clip(np.rint(t),-128,127).astype(np.int16);report={}
 for name,v in [('oracle_8bit',q),('existing_stream',y)]:
  z=render_fractional(v);m=e.align_metric(r,e.lp(z,3500));report[name]=m;print(name,m,flush=True)
  if name=='existing_stream':e.wav(out/'existing_stream_fractional.wav',z*g*min(1,.98/(max(abs(z))*g)))
 w=(uniform_filter1d(t*t,size=156)+12.)**(-.12);w/=w.mean();target=len(t)/FS*5000/8;lam=22.;best=None
 for i in range(3):
  ix=search_pcm(t,tb,bk,bm,lens,w,lam);n=len(ix);print('fractional search',i,lam,n,flush=True)
  if best is None or abs(n-target)<abs(len(best)-target):best=ix.copy()
  if abs(n-target)<.012*target:break
  lam*=(n/target)**2.5
 y,h,over=reconstruct(t,tb,bk,bm,lens,best);z=render_fractional(y);m=e.align_metric(r,e.lp(z,3500));m.update(kbps=len(best)*8/(len(t)/FS)/1000,bytes=len(best),overflows=int(over));report['optimized_stream']=m;print('fractional optimized',m,flush=True)
 e.wav(out/'optimized_fractional.wav',z*g*min(1,.98/(max(abs(z))*g)));np.savez(out/'training.npz',target=t,tb=tb,bk=bk,bm=bm,lens=lens,idx=best,y=y);(out/'metrics.json').write_text(json.dumps(report,indent=2))
if __name__=='__main__':main(sys.argv[1])

"""Rate-distortion VBR trellis with multiple predictor histories per sample."""
from experiment import *
from numba import njit
@njit(cache=True)
def beam(t,tb,bk,bm,lens,w,prices,pen,beta,width):
 n=len(t);order=tb.shape[1];best=np.full((n+1,width),1e30);hist=np.zeros((n+1,width,order),np.int16);ids=np.full((n+1,width),-1,np.int16);prev=np.zeros((n+1,width),np.uint8);best[0,0]=0;h=np.empty(order,np.int16)
 for p in range(n):
  for q in range(width):
   if best[p,q]>1e29:break
   pe=0. if p==0 else c.qout(hist[p,q,0],38)-t[p-1]
   for k in range(len(lens)):
    ln=lens[k];j=p+ln
    if j>n:continue
    err=best[p,q]+pen*prices[k]
    if err>=best[j,width-1]:continue
    h[:]=hist[p,q];old=pe
    for z in range(ln):
     y,wr=c.samp(h,tb[bm[k]],bk[k,z]);d=c.qout(y,38)-t[p+z];low=.65*d+.35*old;err+=w[p+z]*((1-beta)*d*d+beta*low*low)+250000.*wr;old=d
     if err>=best[j,width-1]:break
    if err>=best[j,width-1]:continue
    dup=-1
    for v in range(width):
     if best[j,v]>1e29:break
     same=True
     for a in range(order):
      if h[a]!=hist[j,v,a]:same=False;break
     if same:dup=v;break
    if dup>=0:
     if err>=best[j,dup]:continue
     at=dup
    else:at=width-1
    while at>0 and err<best[j,at-1]:
     best[j,at]=best[j,at-1];hist[j,at]=hist[j,at-1];ids[j,at]=ids[j,at-1];prev[j,at]=prev[j,at-1];at-=1
    best[j,at]=err;hist[j,at]=h;ids[j,at]=k;prev[j,at]=q
 seq=np.empty(n,np.int16);cnt=0;p=n;q=0
 while p>0:
  k=ids[p,q];assert k>=0;seq[cnt]=k;cnt+=1;q=prev[p,q];p-=lens[k]
 return seq[:cnt][::-1].copy(),best[n,0]

def main(seed,mode='compact_beam',width=3,alpha=.12,beta=.5,lam=34.3):
 d=np.load(seed);t,tb,bk,bm,lens,oldidx=[d[k] for k in ('target','tb','bk','bm','lens','idx')];prices=d['prices'] if 'prices' in d else np.ones(len(bk),np.int16);O=ROOT/mode;O.mkdir(exist_ok=True);w=(uniform_filter1d(t*t,size=156)+12.)**(-alpha);w/=np.mean(w);e.FS=FS;e.PERIOD=128;e.PULSES=20;e.LEVELS=77;target=len(t)/FS*5000/8;xr=resample_poly(t/127,768,125);scale=.98/max(abs(xr));e.wav(O/'reference.wav',xr*scale)
 for it in range(2):
  ts=time.time();idx,cost=beam(t,tb,bk,bm,lens,w,prices,lam,beta,width);size=int(np.sum(prices[idx]));print('beam',it,width,lam,size,time.time()-ts,flush=True);y,h,over=reconstruct(t,tb,bk,bm,lens,idx);pwm=e.render(y);m=e.align_metric(e.lp(xr,3500),e.lp(pwm,3500));pcm=e.align_metric(e.lp(xr,3500),e.lp(resample_poly(y/127,768,125),3500));r=dict(bytes=size,kbps=size*8/(len(t)/FS)/1000,snr=m['snr'],stoi=m['stoi'],pcm_snr=pcm['snr'],pcm_stoi=pcm['stoi'],overflows=int(over),penalty=lam,beam_width=width,used_codes=len(set(idx)),codebook_bytes=int(sum(lens[np.unique(idx)])))
  print(r,flush=True);tag='pass'+str(it);(O/(tag+'.json')).write_text(json.dumps(r,indent=2));np.savez(O/(tag+'.npz'),idx=idx,tb=tb,bk=bk,bm=bm,lens=lens,y=y,prices=prices,target=t);e.wav(O/(tag+'.pwm.wav'),pwm/(2*38/128)*scale*128/127);e.wav(O/(tag+'.pcm.wav'),resample_poly(y/127,768,125)*scale)
  if abs(size-target)<150:break
  lam*= (size/target)**2.6
if __name__=='__main__':main(sys.argv[1],sys.argv[2],int(sys.argv[3]),*map(float,sys.argv[4:]))

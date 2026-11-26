"""LP2P-compatible offline gain/pitch vector dictionary training, no runtime RAM.
Pitch templates are ROM residual vectors, not an on-chip pitch oscillator.
"""
from experiment import *
from numba import njit
from scipy.signal import find_peaks
@njit(cache=True)
def shaped(t,tb,bk,bm,lens,weights,penalty,beta):
 n=len(t);ord=tb.shape[1];best=np.full(n+1,1e30);hist=np.zeros((n+1,ord),np.int16);ids=np.full(n+1,-1,np.int16);prev=np.zeros(n+1,np.int32);best[0]=0;h=np.empty(ord,np.int16)
 for p in range(n):
  if best[p]>1e29:continue
  pe=0. if p==0 else c.qout(hist[p,0],38)-t[p-1]
  for k in range(len(lens)):
   ln=lens[k];j=p+ln
   if j>n:continue
   err=best[p]+penalty
   if err>=best[j]:continue
   h[:]=hist[p];old=pe
   for z in range(ln):
    y,wr=c.samp(h,tb[bm[k]],bk[k,z]);d=c.qout(y,38)-t[p+z];low=.65*d+.35*old;err+=weights[p+z]*((1-beta)*d*d+beta*low*low)+250000.*wr;old=d
    if err>=best[j]:break
   if err<best[j]:best[j]=err;hist[j]=h;ids[j]=k;prev[j]=p
 seq=np.empty(n,np.int16);cnt=0;i=n
 while i>0:
  assert ids[i]>=0;seq[cnt]=ids[i];cnt+=1;i=prev[i]
 return seq[:cnt][::-1].copy(),best[n]

def pitch_templates(t,tb,bk,bm,lens,limit=150):
 order=tb.shape[1];target=np.clip(np.rint(t),-127,127).astype(np.int16);h=np.r_[np.zeros(order,np.int16),target]
 residuals=np.stack([np.clip(target-sum(tb[k,j,h[order-j-1:order-j-1+len(t)]&255] for j in range(order)),-128,127) for k in range(len(tb))],axis=1)
 cand=[]
 for p in range(160,len(t)-320,64):
  x=t[p-120:p+120];ener=np.dot(x,x)
  if ener<5000:continue
  lag=np.arange(20,101);scores=np.array([np.dot(x[:-l],x[l:])/np.sqrt(np.dot(x[:-l],x[:-l])*np.dot(x[l:],x[l:])+1e-8) for l in lag]);peaks=find_peaks(scores)[0]
  if not len(peaks):continue
  # Prefer the shortest lag close to the strongest peak to suppress octave errors.
  best=scores[peaks].max();peaks=peaks[scores[peaks]>=max(.72,best-.045)]
  if not len(peaks):continue
  P=int(lag[peaks[0]]);k=int(np.argmin(np.sum(residuals[p:p+P]**2,axis=0,dtype=float)));r=residuals[:,k]
  start=p+int(np.argmax(abs(r[p:p+P])));v=r[start:start+P].astype(np.int16)
  score=best*ener/(P**.3);cand.append((score,k,P,v))
 # One template per pitch/bank/amplitude cluster initially. Keep diversity.
 cand.sort(key=lambda a:a[0],reverse=True);out=[];seen={}
 for s,k,P,v in cand:
  key=(k,P//2,int(np.log2(1+np.sqrt(np.mean(v.astype(float)**2)))*2))
  if seen.get(key,0)>=2:continue
  seen[key]=seen.get(key,0)+1;out.append((k,P,v))
  if len(out)>=limit:break
 # Select a bounded count of data-driven noise/voiced amplitude variants from existing dictionary
 width=max(bk.shape[1],max((p for _,p,_ in out),default=1));B=list(np.pad(bk,((0,0),(0,width-bk.shape[1]))));M=list(bm);L=list(lens)
 for k,p,v in out:B.append(np.pad(v,(0,width-p)));M.append(k);L.append(p)
 return np.array(B,np.int16),np.array(M,np.uint8),np.array(L,np.int32),len(out)

def main(source,seed,mode='peak',alpha=.16,beta=.4):
 O=ROOT/('compact_'+mode);O.mkdir(exist_ok=True);t=prepare(source,mode);e.FS=FS;e.PERIOD=128;e.PULSES=20;e.LEVELS=77
 d=np.load(seed);tb,bk,bm,lens,idx=[d[k] for k in ('tb','bk','bm','lens','idx')];assert np.sum(lens[idx])==len(t)
 w=(uniform_filter1d(t*t,size=156)+12.)**(-alpha);w/=np.mean(w);y,h,over=reconstruct(t,tb,bk,bm,lens,idx)
 bk,bm,lens=extend(t,tb,bk,bm,lens,idx,h,w,380);bk,bm,lens,n_pitch=pitch_templates(t,tb,bk,bm,lens,120);print('dictionary candidates',len(bk),'pitch',n_pitch,flush=True)
 ts=time.time();ix,cost=shaped(t,tb,bk,bm,lens,w,45.,beta);hits=np.bincount(ix,minlength=len(bk));print('initial search',len(ix),time.time()-ts,flush=True)
 # Keep most used templates, with a mild preference for longer phrases to save rate.
 # Keep enough single-sample entries for edge cases. Drop rare long entries to fit ROM.
 scores=hits*(1+.3*np.log2(lens));scores[lens==1]*=1.2
 sel=np.argsort(-scores)[:255];pitch_count=int(np.sum(sel>=len(bk)-n_pitch));print('selected pitch vectors',pitch_count,'book bytes',sum(lens[sel]),flush=True)
 bk,bm,lens=bk[sel],bm[sel],lens[sel]
 target=len(t)/FS*5000/8;lam=45.;xr=resample_poly(t/127,768,125);scale=.98/max(abs(xr));e.wav(O/'reference.wav',xr*scale)
 for it in range(2):
  best=None;lo=0;hi=1e9
  for z in range(4):
   ts=time.time();idx,cost=shaped(t,tb,bk,bm,lens,w,lam,beta);size=len(idx);print(mode,it,z,lam,size,time.time()-ts,flush=True)
   if best is None or abs(size-target)<abs(best[0]-target):best=(size,idx.copy(),lam)
   if abs(size-target)<70:break
   if size>target:lo=lam
   else:hi=lam
   est=lam*(size/target)**2.6
   lam=(lo+hi)/2 if not lo<est<hi else est
  size,idx,lam=best;y,h,over=reconstruct(t,tb,bk,bm,lens,idx);pwm=e.render(y);m=e.align_metric(e.lp(xr,3500),e.lp(pwm,3500));pcm=e.align_metric(e.lp(xr,3500),e.lp(resample_poly(y/127,768,125),3500));report=dict(bytes=size,kbps=size*8/(len(t)/FS)/1000,snr=m['snr'],stoi=m['stoi'],pcm_snr=pcm['snr'],pcm_stoi=pcm['stoi'],overflows=int(over),penalty=lam,used_codes=len(set(idx)),codebook_bytes=int(sum(lens)),pitch_templates=pitch_count,pitch_symbols=int(np.sum(sel[idx]>=len(hits)-n_pitch)))
  print(report,flush=True);tag='pass'+str(it);(O/(tag+'.json')).write_text(json.dumps(report,indent=2));np.savez(O/(tag+'.npz'),idx=idx,tb=tb,bk=bk,bm=bm,lens=lens,y=y,target=t);e.wav(O/(tag+'.pwm.wav'),pwm/(2*38/128)*scale*128/127);e.wav(O/(tag+'.pcm.wav'),resample_poly(y/127,768,125)*scale)
  if it==0:bk=train_refine(t,tb,bk,bm,lens,idx,h,w)
if __name__=='__main__':main(*sys.argv[1:4],*(map(float,sys.argv[4:6])))

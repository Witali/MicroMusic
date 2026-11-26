"""Voicing-aware excitation search, PC-expanded residual templates, no RAM on Z80."""
from experiment import *
from compact_gain_pitch import shaped,pitch_templates
from compact_container import pack
from beam_vbr import beam
from scipy.signal import find_peaks
import build_packed
rng=np.random.default_rng(42)
e.FS=FS;e.PERIOD=128;e.PULSES=20;e.LEVELS=77

def init(t,order=6,nb=8):
 a,assign,X=c.design(t,order,nb,80);tb=c.tables(a)
 q=np.r_[np.zeros(order,np.int16),np.clip(np.rint(t),-127,127).astype(np.int16)]
 r=np.clip(np.rint(t[:,None]-np.stack([sum(tb[b,i,q[order-1-i:order-1-i+len(t)]&255] for i in range(order)) for b in range(nb)],axis=1)),-128,127)
 B=[];M=[];L=[]
 for ln,budget in zip([1,2,4,8,16,32,64,128],[16,24,39,52,55,37,23,9]):
  starts=np.arange(0,len(t)-ln+1,max(1,ln//4));labels=assign[starts];mass=np.array([np.sqrt(max(1,np.sum(r[assign==j,j]**2))*max(1,np.sum(labels==j))) for j in range(nb)])
  q=budget*mass/mass.sum();counts=q.astype(int);counts[np.argsort(-(q-counts))[:budget-counts.sum()]]+=1
  for j,k in enumerate(counts):
   if not k:continue
   z=starts[labels==j];z=rng.choice(z,min(6000,len(z)),replace=False) if len(z)>6000 else z
   book=c.init_book(r[z[:,None]+np.arange(ln),j],a[j],k,2045+ln+j)
   B.extend(np.pad(book,((0,0),(0,128-ln))));M.extend([j]*k);L.extend([ln]*k)
 return tb,np.array(B,np.int16),np.array(M,np.uint8),np.array(L,np.int32),r,assign

def rate(t,tb,bk,bm,lens,w,lam,width=1,tries=3):
 target=len(t)/FS*5000/8;best=None
 for i in range(tries):
  ts=time.time()
  if width==1:ix,cost=shaped(t,tb,bk,bm,lens,w,lam,.35)
  else:ix,cost=beam(t,tb,bk,bm,lens,w,np.ones(len(lens),np.int16),lam,.35,width)
  n=len(ix);print('search',width,i,round(lam,3),n,round(time.time()-ts,1),flush=True)
  if best is None or abs(n-target)<abs(len(best[0])-target):best=(ix.copy(),lam)
  if abs(n-target)<target*.012:break
  lam*= (n/target)**2.5
 return best

def save(tag,t,tb,bk,bm,lens,ix,lam):
 out=ROOT/tag;out.mkdir(exist_ok=True);y,h,over=reconstruct(t,tb,bk,bm,lens,ix);np.savez(out/'training.npz',target=t,tb=tb,bk=bk,bm=bm,lens=lens,idx=ix,y=y)
 xr=resample_poly(t/127,768,125);g=.98/max(abs(xr));pwm=e.render(y)/(2*38/128)*128/127
 a=e.lp(xr,3500);b=e.lp(pwm,3500);m=e.align_metric(a,b);pcm=e.align_metric(a,e.lp(resample_poly(y/127,768,125),3500));strict=10*np.log10(np.sum(a*a)/np.sum((a-b)**2))
 d=dict(bytes=len(ix),kbps=len(ix)*8/(len(t)/FS)/1000,snr=m['snr'],stoi=m['stoi'],strict_snr=float(strict),pcm_snr=pcm['snr'],pcm_stoi=pcm['stoi'],overflows=int(over),penalty=lam,book_bytes=int(sum(lens)),used_codes=len(set(ix)),rms_dbfs=float(20*np.log10(np.sqrt(np.mean((xr*g)**2)))))
 (out/'metrics.json').write_text(json.dumps(d,indent=2));print(tag,d,flush=True)
 for name,z in [('reference',xr),('pcm',resample_poly(y/127,768,125)),('pwm',pwm)]:e.wav(out/(name+'.wav'),z*g*min(1,.98/(np.max(abs(z))*g)))
 return y,h,d

def candidates(t,tb,bk,bm,lens,ix,h,w,r,assign):
 B,M,L=extend(t,tb,bk,bm,lens,ix,h,w,390);n_gain=len(B)-len(bk);B,M,L,n_pitch=pitch_templates(t,tb,B,M,L,90);K=['original']*len(bk)+['gain']*n_gain+['pitch']*n_pitch;B=list(B);M=list(M);L=list(L)
 # Short noise-like windows classified by normalized autocorrelation. Include
 # actual unvoiced residual vectors plus spectral-tilt matched random vectors.
 seen=set();count=0
 for p in np.argsort(-uniform_filter1d(t*t,240))[::79]:
  if p<120 or p+120>=len(t):continue
  x=t[p-120:p+120];ac=max(np.dot(x[:-l],x[l:])/np.sqrt(np.dot(x[:-l],x[:-l])*np.dot(x[l:],x[l:])+1e-8) for l in range(22,110,2))
  if ac>.45:continue
  b=int(assign[p]);v=r[p:p+32,b];amp=np.sqrt(np.mean(v*v));key=(b,int(np.log2(1+amp)*3))
  if key in seen or amp<.4:continue
  seen.add(key)
  for n in (8,16,32):
   z=v[:n];B.append(np.pad(z,(0,len(B[0])-n)));M.append(b);L.append(n);K.append('unvoiced')
   white=rng.normal(size=n);rho=np.clip(np.dot(z[1:],z[:-1])/(np.dot(z,z)+1e-9),-.8,.8)
   for j in range(1,n):white[j]+=rho*white[j-1]
   white*=amp/(np.sqrt(np.mean(white*white))+1e-9);B.append(np.pad(np.clip(np.rint(white),-128,127),(0,len(B[0])-n)));M.append(b);L.append(n);K.append('noise')
  count+=1
  if count>=12:break
 return np.array(B,np.int16),np.array(M,np.uint8),np.array(L,np.int32),np.array(K)

def build(tag):
 p=ROOT/tag;pack(p/'training.npz',p/'sound.lp2c')
 try:build_packed.build(str(p/'training.npz'),str(p/'decoder'),128,20,77,1)
 except ValueError as exc:print('ROM build',tag,str(exc),flush=True)

def main():
 t=prepare(ROOT/'source_mono.wav','peak');print('samples',len(t),'duration',len(t)/FS,flush=True);w=(uniform_filter1d(t*t,size=156)+12.)**(-.12);w/=w.mean()
 tb,bk,bm,lens,r,assign=init(t);print('init',len(bk),sum(lens),flush=True)
 ix,lam=rate(t,tb,bk,bm,lens,w,20.,tries=4);y,h,metrics=save('baseline',t,tb,bk,bm,lens,ix,lam)
 bk=train_refine(t,tb,bk,bm,lens,ix,h,w);ix,lam=rate(t,tb,bk,bm,lens,w,lam,tries=2);y,h,metrics=save('baseline_refined',t,tb,bk,bm,lens,ix,lam)
 build('baseline_refined')
 B,M,L,K=candidates(t,tb,bk,bm,lens,ix,h,w,r,assign);print('candidates',dict(zip(*np.unique(K,return_counts=True))),flush=True)
 ii,ll=rate(t,tb,B,M,L,w,lam,tries=1);counts=np.bincount(ii,minlength=len(B));score=counts*(1+.18*np.log2(L));score[L==1]*=1.25;sel=np.argsort(-score)[:255]
 if not np.any(L[sel]==1):sel[-1]=np.flatnonzero(L==1)[0]
 bk,bm,lens=B[sel],M[sel],L[sel];K=K[sel];print('selected',dict(zip(*np.unique(K,return_counts=True))),flush=True)
 ix,lam=rate(t,tb,bk,bm,lens,w,ll,tries=3);y,h,metrics=save('hybrid',t,tb,bk,bm,lens,ix,lam)
 bk=train_refine(t,tb,bk,bm,lens,ix,h,w);ix,lam=rate(t,tb,bk,bm,lens,w,lam,tries=2,width=2);y,h,metrics=save('hybrid_refined',t,tb,bk,bm,lens,ix,lam)
 (ROOT/'hybrid_refined'/'template_types.json').write_text(json.dumps({str(k):dict(entries=int(np.sum(K==k)),tokens=int(np.sum(K[ix]==k)),samples=int(np.sum(lens[ix][K[ix]==k]))) for k in np.unique(K)},indent=2));build('hybrid_refined')
if __name__=='__main__':main()

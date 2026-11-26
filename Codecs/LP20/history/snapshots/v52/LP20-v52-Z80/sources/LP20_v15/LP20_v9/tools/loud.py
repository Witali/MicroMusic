"""Fresh LP2P training for lookahead limited, +3 dB louder input."""
from experiment import *
from compact_gain_pitch import shaped
from scipy.ndimage import maximum_filter1d

def main(source,db=3.):
 O=ROOT/'loud';O.mkdir(exist_ok=True);t=prepare(source,'peak');x=t/127
 # A 20 ms peak envelope, bounded gain, smooth lookahead limiter (no sample clipping).
 cap=.99/np.maximum(maximum_filter1d(abs(x),size=157),.001);g=np.minimum(10**(db/20),cap);g=np.minimum(g,gaussian_filter1d(g,78));x*=g;x*=.99/max(abs(x));t=x*127
 order=8;nb=8;lengths=[1,2,4,8,16,32,64];budgets=[18,31,55,65,42,28,16];a,assign,X=c.design(t,order,nb,64);tb=c.tables(a);h=np.r_[np.zeros(order,np.int16),np.clip(np.rint(t),-128,127).astype(np.int16)];pred=np.stack([sum(tb[j,i,h[order-1-i:order-1-i+len(t)]&255] for i in range(order)) for j in range(nb)],axis=1);r=np.clip(np.rint(t[:,None]-pred),-128,127);books=[];maps=[];ll=[]
 for ln,budget in zip(lengths,budgets):
  starts=np.arange(0,len(t)-ln+1);labels=assign[starts];mass=np.array([np.sqrt(max(1,np.sum(r[assign==j,j]**2))*max(1,np.sum(labels==j))) for j in range(nb)]);counts=np.full(nb,1);q=(budget-counts.sum())*mass/mass.sum();counts+=q.astype(int)
  for j in np.argsort(-(q-q.astype(int)))[:budget-counts.sum()]:counts[j]+=1
  for j in range(nb):
   z=starts[labels==j];rr=r[z[:,None]+np.arange(ln),j];book=c.init_book(rr,a[j],counts[j],2045+ln+j);books.extend(np.pad(book,((0,0),(0,max(lengths)-ln))));maps.extend([j]*len(book));ll.extend([ln]*len(book))
 bk,bm,lens=np.asarray(books,np.int16),np.array(maps,np.uint8),np.array(ll,np.int32);print('trained',len(bk),flush=True)
 w=(uniform_filter1d(t*t,size=156)+12.)**(-.12);w/=np.mean(w);target=len(t)/FS*5000/8;lam=65.;xr=resample_poly(x,768,125);scale=.98/max(abs(xr));e.wav(O/'reference.wav',xr*scale);e.FS=FS;e.PERIOD=128;e.PULSES=20;e.LEVELS=77
 for it in range(2):
  best=None;lo=0;hi=1e9
  for z in range(4):
   ts=time.time();idx,cost=shaped(t,tb,bk,bm,lens,w,lam,.45);size=len(idx);print(it,z,lam,size,time.time()-ts,flush=True)
   if best is None or abs(size-target)<abs(best[0]-target):best=(size,idx.copy(),lam)
   if abs(size-target)<100:break
   if size>target:lo=lam
   else:hi=lam
   est=lam*(size/target)**2.5;lam=(lo+hi)/2 if not lo<est<hi else est
  size,idx,lam=best;y,h,over=reconstruct(t,tb,bk,bm,lens,idx);pwm=e.render(y);m=e.align_metric(e.lp(xr,3500),e.lp(pwm,3500));pcm=e.align_metric(e.lp(xr,3500),e.lp(resample_poly(y/127,768,125),3500));report=dict(bytes=size,kbps=size*8/(len(t)/FS)/1000,snr=m['snr'],stoi=m['stoi'],pcm_snr=pcm['snr'],pcm_stoi=pcm['stoi'],overflows=int(over),penalty=lam,used_codes=len(set(idx)),codebook_bytes=int(sum(lens)),reference_rms_db=20*np.log10(np.sqrt(np.mean((xr*scale)**2))))
  print(report,flush=True);tag='pass'+str(it);(O/(tag+'.json')).write_text(json.dumps(report,indent=2));np.savez(O/(tag+'.npz'),idx=idx,tb=tb,bk=bk,bm=bm,lens=lens,y=y,target=t);e.wav(O/(tag+'.pwm.wav'),pwm/(2*38/128)*scale*128/127);e.wav(O/(tag+'.pcm.wav'),resample_poly(y/127,768,125)*scale)
  if it==0:bk=train_refine(t,tb,bk,bm,lens,idx,h,w)
if __name__=='__main__':main(sys.argv[1],float(sys.argv[2]) if len(sys.argv)>2 else 3.)

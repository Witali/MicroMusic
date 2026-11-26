#!/usr/bin/env python3
"""Rate-distortion search for independent context dictionaries and longer records.
Actual ROM keeps one byte/index; 7-bit size is only a hypothetical packed payload.
"""
from repack import *
from scipy.ndimage import uniform_filter1d
from scipy.cluster.vq import kmeans2
from noise_study import Mask

@njit(cache=True)
def search(t,tb,recs,lens,th,q,w,pen,cap):
 n=len(t);cost=np.full(n+1,1e30);hist=np.zeros((n+1,6),np.int16);ids=np.full(n+1,-1,np.int16);length=np.zeros(n+1,np.int16);cost[0]=0.;h=np.empty(6,np.int16)
 for p in range(n):
  if cost[p]>1e29:continue
  c=255*int(hist[p,0]>=th or hist[p,0]<-th);old=q[hist[p,0]+512]-t[p-1] if p else 0.
  for k in range(cap):
   j=c+k;ln=lens[j];end=p+ln
   if end>n:continue
   err=cost[p]+pen
   if err>=cost[end]:continue
   h[:]=hist[p];pe=old;good=True
   for i in range(ln):
    b,r=recs[j,i];v,ov=step(h,tb[b],r,10)
    if ov:good=False;break
    e=q[v+512]-t[p+i];err+=w[p+i]*(e*e+.28*(e-pe)**2);pe=e
    if err>=cost[end]:good=False;break
   if good:
    cost[end]=err;hist[end]=h;ids[end]=k;length[end]=ln
 if ids[n]<0:return np.empty(0,np.int16)
 out=np.empty(n,np.int16);p=n;z=0
 while p:
  out[z]=ids[p];z+=1;p-=length[p]
 return out[:z][::-1].copy()

def make_book(d,cap,add):
 old=records(d);raw,loc=actual(d,old);raw=np.array(raw,np.int16);y=d['y'];th=int(d['threshold']);ctx=np.r_[0,(y[:-1]>=th)|(y[:-1]<-th)];cnt=np.bincount(d['idx']+255*ctx[loc[:-1]],minlength=510);books=[];rng=np.random.default_rng(42)
 for c in range(2):
  keep=sorted(range(255),key=lambda k:(len(old[c*255+k])!=1,-cnt[c*255+k],k))[:cap-add];base=[old[c*255+k] for k in keep];existing=set(base);p=loc[:-1][ctx[loc[:-1]]==c];new=[]
  for ln in (24,32,48):
   nadd=add//3+(ln==32)*(add%3);cand=p[p+ln<=len(y)];# exclude zero stretches, select segments with distinct waveform shapes
   if not len(cand) or not nadd:continue
   if len(cand)>2800:cand=rng.choice(cand,2800,replace=False)
   arr=y[cand[:,None]+np.arange(ln)].astype(np.float64);energy=np.sqrt(np.mean(arr**2,1));valid=energy>5;cand=cand[valid];arr=arr[valid];energy=energy[valid]
   if len(cand)<nadd:continue
   # target-state-aware waveform feature, including first differences and magnitude
   x=arr/(20+energy[:,None]);x=np.c_[x,0.5*np.diff(x,axis=1),0.2*np.log1p(energy[:,None])]
   cent,labels=kmeans2(x,nadd,iter=14,minit='++',rng=rng)
   for i,center in enumerate(cent):
    ix=np.flatnonzero(labels==i)
    if not len(ix):continue
    order=ix[np.argsort(np.sum((x[ix]-center)**2,1))]
    for j in order:
     r=tuple(map(tuple,raw[cand[j]:cand[j]+ln].tolist()))
     if r in existing:continue
     new.append(r);existing.add(r);break
  if len(new)<add:
   for k in range(255):
    r=old[c*255+k]
    if r not in existing:new.append(r);existing.add(r)
    if len(new)==add:break
  b=base+new[:add];assert len(b)==cap;books.extend(b+[b[0]]*(255-cap))
 lens=np.array(list(map(len,books)),np.int32);mat=np.zeros((510,max(lens),2),np.int16)
 for i,r in enumerate(books):mat[i,:len(r)]=r
 return dict(d,records=mat,lengths=lens)

def run(name,cap,add,rate):
 out=HERE/name/f'long{cap}_{add}_{rate:g}';out.mkdir(exist_ok=True,parents=True);base=model(HERE.parent/'LP20_v21_rollout'/name/'training.npz');m=json.loads((HERE.parent/'LP20_v21_rollout'/name/'decoder.json').read_text());d=make_book(base,cap,add);tb=f.compact_tables(d['a']);lev,qi,q=qtables(d,m);t=d['target'];w=(uniform_filter1d(t*t,156)+12)**(-.22);w/=w.mean();budget=rate*1000*len(t)/FS/8;lam=50.;lo=None;hi=None;trials=[];best=None
 for i in range(5):
  ix=search(t,tb,d['records'],d['lengths'],int(d['threshold']),q,w,lam,cap)
  if not len(ix):raise ValueError('no path')
  y,ov=raw_decode(tb,d['records'],d['lengths'],ix,int(d['threshold']));assert not ov and len(y)==len(t)
  met,r,z=f.measure(d,y,m);met.update(tokens=len(ix),kbps=len(ix)*8*FS/len(t)/1000,penalty=lam,packed7_kbps=len(ix)*7*FS/len(t)/1000 if cap==128 else None);trials.append(met);print('RATE',name,cap,add,i,met,flush=True)
  if best is None or (len(ix)<=budget and (len(best[0])>budget or met['snr']>best[2]['snr'])) or (len(best[0])>budget and len(ix)<len(best[0])):best=(ix.copy(),y.copy(),met.copy());np.savez(out/'candidate.npz',**dict(d,idx=ix,y=y));(out/'trials.json').write_text(json.dumps(trials,indent=2))
  if abs(len(ix)-budget)<budget*.012:break
  if len(ix)>budget:lo=(lam,len(ix))
  else:hi=(lam,len(ix))
  if lo and hi:
   x=np.clip((lo[1]-budget)/(lo[1]-hi[1]),.12,.88);lam=np.exp((1-x)*np.log(lo[0])+x*np.log(hi[0]))
  else:lam*=np.clip((len(ix)/budget)**2.5,.35,3.5)
 ix,y,met=best;dd=dict(d,idx=ix,y=y);raw,loc=actual(dd,records(dd));ctx=np.r_[0,(y[:-1]>=d['threshold'])|(y[:-1]<-d['threshold'])];cnt=np.bincount(ix+255*ctx[loc[:-1]],minlength=510);r=records(dd);r=[z if cnt[i] else r[0] for i,z in enumerate(r)];ll=np.array(list(map(len,r)),np.int32);a=np.zeros((510,max(ll),2),np.int16)
 for i,z in enumerate(r):a[i,:len(z)]=z
 dd.update(records=a,lengths=ll);assert np.array_equal(decode_records(dd)[0],y);(out/'result.json').write_text(json.dumps(met,indent=2));mm,r,z=f.measure(dd,y,m);f.audio(out/'v22.wav',r,z);buildcheck(dd,out,m)
if __name__=='__main__':run(sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),float(sys.argv[4]))

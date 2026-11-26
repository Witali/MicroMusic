#!/usr/bin/env python3
"""Reuse context-local unused tokens for scaled excitation, same byte count.
Context is computed from high byte of last reconstructed sample (no multiply).
"""
from adapt import *
@njit(cache=True)
def decode_reuse(tb,bk,bm,lens,idx,alt,ab,active,threshold):
 h=np.zeros(6,np.int16);y=np.empty(np.sum(lens[idx]),np.int16);p=0;ov=0
 for k in idx:
  c=h[0]>=threshold or h[0]<-threshold
  v=alt[k] if c and active[k] else bk[k];bank=ab[k] if c and active[k] else bm[k]
  for j in range(lens[k]):
   z,b=step(h,tb[bank],v[j],10);y[p]=z;p+=1;ov+=b
 return y,ov

def run_reuse():
 out=ROOT/'reuse';out.mkdir(exist_ok=True);d=dict(np.load(V16/'release/training.npz'));meta=json.loads((V16/'release/decoder.json').read_text());d['tb']=f.compact_tables(d['a']);base,_,_=f.measure(d,d['y'],meta);q=(np.array([sum(meta['patterns'][str(int(i))]) for i in f.lut10(d['ww10'])])-1280)*128/1120
 gr,gt,_=grads(d,d['y'],meta);bk,bm,ix,lens,y=[d[k] for k in ('bk','bm','idx','lens','y')];loc=np.r_[0,np.cumsum(lens[ix])];ex=np.concatenate([bk[k,:lens[k]] for k in ix]);ba=np.repeat(bm[ix],lens[ix]);va,valid,opt=propose(d,False)
 hist=np.r_[0,y[loc[1:-1]-1]];sc=evaluate(bm,lens,ix,loc,va,valid,y,d['tb'],q,gr,gt,ex,ba,.75,1.,24);log=[];overall=base;bestmode=None
 for th in [96,128]:
  ctx=(hist>=th)|(hist< -th);ct=np.bincount(ix[ctx],minlength=len(bk));free=np.flatnonzero(ct==0);print('CONTEXT',th,'free',len(free),'high blocks',sum(ctx),flush=True);choices=[]
  for k in range(len(bk)):
   hs=np.flatnonzero((ix==k)&ctx)
   if not len(hs) or not np.any(lens[free]==lens[k]):continue
   for g in range(len(opt)):
    if not valid[k,g]:continue
    h=hs[sc[hs,g]<0]
    if not len(h):continue
    v=sc[h,g].sum();choices.append((float(v),k,g,h))
  choices.sort(key=lambda x:x[0]);print('CANDIDATES',len(choices),[(float(x[0]),int(x[1]),int(x[2]),len(x[3])) for x in choices[:6]],flush=True);alt=np.zeros_like(bk);ab=bm.copy();active=np.zeros(len(bk),bool);jj=ix.copy();best=base.copy();tried=0;accepted=0
  for _,k,g,hs in choices:
   if tried>=25 or accepted>=12:break
   if np.any(jj[hs]!=k):continue
   avail=free[(lens[free]==lens[k])&(~active[free])]
   if not len(avail):continue
   victim=int(avail[0]);aa=alt.copy();bb=ab.copy();ac=active.copy();nn=jj.copy();aa[victim]=va[k,g];bb[victim]=bm[k];ac[victim]=True;nn[hs]=victim
   pairs={(int(bm[i]),int(r)) for i,n in enumerate(lens) for r in bk[i,:n]};pairs.update((int(bb[i]),int(r)) for i in np.flatnonzero(ac) for r in aa[i,:lens[i]])
   if len(pairs)>254 or sum(lens[ac]+1)>600:continue
   yy,ov=decode_reuse(d['tb'],bk,bm,lens,nn,aa,bb,ac,th)
   if ov:continue
   tried+=1;mm,r,z=f.measure(d,yy,meta);ok=mm['snr']>=best['snr'] and mm['stoi']>=best['stoi'] and (mm['snr']>best['snr']+1e-8 or mm['stoi']>best['stoi']+1e-8);rec=dict(threshold=th,shape=int(k),slot=victim,scale=list(opt[g]),hits=len(hs),accepted=bool(ok),**mm);log.append(rec)
   if ok:alt=aa;ab=bb;active=ac;jj=nn;best=mm;accepted+=1;print('ACCEPT',rec,flush=True)
   if ok and mm['snr']>=overall['snr'] and mm['stoi']>=overall['stoi']:
    overall=mm;bestmode=th;np.savez(out/'best.npz',**dict(d,alt=alt,ab=ab,active=active,threshold=th,idx=jj,y=yy));f.audio(out/'pwm.wav',r,z)
   (out/'results.json').write_text(json.dumps(dict(baseline=base,best=overall,bestmode=bestmode,trials=log),indent=2))
  print('MODE FINAL',th,best,flush=True)
 print('FINAL',overall,bestmode,flush=True)
if __name__=='__main__':run_reuse()

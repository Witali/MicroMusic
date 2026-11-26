#!/usr/bin/env python3
"""LP4V encoder-only refinement. Use pair-optimized PWM targets, adaptive weights,
coefficient-level moves, and evaluate the actual filtered PWM waveform.
Fixed predictor headers and scale indices, fixed format, strict stream byte cap.
"""
import sys, os
from pathlib import Path
ROOT48=Path(__file__).resolve().parent
V48=ROOT48.parent/"LP20-v48"
V47=ROOT48.parent/"LP20-v47"
sys.path.insert(0,str(V47))
from joint_pwm import *
from repack47 import stats,build
from scipy.ndimage import gaussian_filter1d
from viterbi49 import optimize
from compress46 import read_lengths
from adaptive45 import (BASE,decode_v,write_v,rbits,choose,SCALES,G,M,TYP,HEADER42,FS,struct,dct,idct,quant)
import time,csv,pickle

def batch_filter(a):
 return sosfiltfilt(H35,sosfiltfilt(H7,resample_poly(a,24,125,axis=-1),axis=-1),axis=-1)

def alloc(B,E,budget):
 ii=np.arange(len(B));lo=0.;hi=1.;best=None
 for _ in range(52):
  la=(lo+hi)/2;j=(E+la*B).argmin(axis=1);bits=int(B[ii,j].sum())
  if bits<=budget:hi=la;best=j;used=bits
  else:lo=la
 if best is None:return None,None
 # greedily fill leftover bits with actual cost reductions; no larger budget.
 for _ in range(100):
  db=B-B[ii,best,None];de=E[ii,best,None]-E;ok=(db>0)&(db<=budget-used)&(de>0);ratio=np.divide(de,db,out=np.full_like(de,-np.inf),where=ok);k=np.argmax(ratio)
  if not np.isfinite(ratio.flat[k]):break
  i,j=np.unravel_index(k,ratio.shape);used+=int(db[i,j]);best[i]=j
 return best,used

def alloc_scale(cc,budget,weight):
 costs=[];bs=[];groups=[]
 for ls in cc:
  a=np.array([[x[0],x[1],x[3],x[4]] for x in ls]);bs.append(a[:,0].astype(int));sc=a[:,1].astype(int);costs.append(a[:,2]+weight*a[:,3]);ss=np.unique(sc);groups.append((ss,[np.flatnonzero(sc==s) for s in ss]))
 def solve(lam):
  prev=np.array([0]);v=np.array([0.]);parents=[];sels=[];nb=np.array([0])
  for i,(ss,ix) in enumerate(groups):
   a=costs[i]+lam*bs[i];j=np.array([j[np.argmin(a[j])] for j in ix]);tb=np.where(abs(prev[:,None]-ss[None,:])<=7,4,11) if i else np.full((1,len(ss)),7);c=v[:,None]+lam*tb;p=c.argmin(axis=0);rng=np.arange(len(ss));v=c[p,rng]+a[j];nb=nb[p]+tb[p,rng]+bs[i][j];parents.append(p);sels.append(j);prev=ss
  j=v.argmin();used=nb[j];sel=[]
  for i in range(len(cc)-1,-1,-1):sel.append(sels[i][j]);j=parents[i][j]
  return sel[::-1],int(used)
 lo=0.;hi=1.;best=None
 for _ in range(29):
  la=(lo+hi)/2;sel,num=solve(la)
  if num<=budget:hi=la;best=(sel,num)
  else:lo=la
 assert best is not None
 return best

def run(clip,profile,iteration=1,inputrate=6.):
 base,d,meta,ref,lv,x=data(clip);out=ROOT48/clip;book=(base/'book.bin').read_bytes();md=model(d,meta);raw,rep,uniq,K,H,_=md;path=V48/clip/'Recommended.lp4v';h=struct.unpack_from(HEADER42,path.read_bytes())[1:];ln=read_lengths(path);z,frames,oldbits=decode_v(path,book);n=h[0];baseline=render(z,d,meta);assert np.array_equal(baseline,wavfile.read(path.with_suffix('.wav'))[1]);r=filt(ref.astype(float)/32768);r-=r.mean();origraw=raw(z).reshape(-1,32);y0,lag,beta=align(r,filt_raw(origraw.ravel()));err=y0-r;hf=sosfiltfilt(HH,err);w,hw=weights(r,True);peak=np.max(abs(r));threshold=.065*peak;thlow=.035*peak
 # Constrained-to-existing-templates direct target, initialized from the compressed signal.
 ideal=np.load(out/'compressed-target.npy') if (out/'compressed-target.npy').exists() else optimize(z,d,meta,ref,md,'peak',((4,96,0,False),(5,96,48,True)))[0]
 np.save(out/'compressed-target.npy',ideal)
 ideal_level=raw(ideal).reshape(-1,32).mean(axis=1)*128/.875;level=origraw.mean(axis=1)*128/.875
 delta=ideal_level-level
 # Back-project the globally aligned waveform error with approximate inverse hold.
 # Use the fitted raw gain for conversion to internal levels, not a per-block normalization.
 e_back=resample_poly(-err,125,768)*128/.875/beta
 e_back=pre(e_back[:n],.75);assert len(e_back)==n
 heads=oldbits-sum(int(rbits(f[-1],ln,G,M)) for f in frames)-7-sum(4 if abs(a[4]-b[4])<=7 else 11 for a,b in zip(frames,frames[1:]));cc=[];pos=0;t0=time.time();pk=18. if profile=='Peak' else 1.5
 for i,f in enumerate(frames):
  nominal,m,par,p,s,q=f;nn=len(q);sc=SCALES[s];fr=np.arange(nn)/nn*FS/2;W=np.maximum(1/(1+(fr/3500)**10)**2,.05)*np.sinc(fr/FS)**2;zz=z[pos:pos+nn];bb=int(rbits(q,ln,G,M));cands={(s,q.tobytes()):(bb,s,q)}
  def add(v,ss=s):
   v=np.asarray(v,np.int32);b=int(rbits(v,ln,G,M));
   if b<=max(bb+64,bb*1.6):cands[(ss,v.tobytes())]=(b,ss,v)
  # Multiple coefficient trajectories, not just inverse-filtered continuous PCM.
  c0=q*sc;d0=dct(delta[pos:pos+nn],norm='ortho');d1=dct(e_back[pos:pos+nn],norm='ortho');grp=int(np.count_nonzero(q)>=36)
  for dv in (d0,d1,.5*(d0+d1)):
   for alpha in (.5,1.0):
    c=c0+alpha*dv
    for fa in (.20,.65,1.5):add(choose(c,sc,sc*sc*fa,ln,G,M,grp,W))
    v=q.copy();ix=np.flatnonzero(q);v[ix]=np.rint(c[ix]/sc).astype(np.int32);add(v)
  # Refit residual scale; both unchanged and adjusted coefficient support.
  for ss in sorted(set(np.clip([s-4,s-2,s-1,s+1,s+2,s+4],0,127))):
   ss=int(ss);sc1=SCALES[ss];c=c0+.75*d1;ix=np.flatnonzero(q);v=np.zeros(nn,np.int32);v[ix]=np.rint(c[ix]/sc1).astype(np.int32);add(v,ss)
   for fac in (.32,1.05):add(choose(c,sc1,sc1*sc1*fac,ln,G,M,grp,W),ss)
  # Search sparse correction moves; also create cheaper variants to allocate bits globally.
  dd=(d0+d1)/2;order=np.argsort(abs(dd)*W)[-6:][::-1]
  for j in order:
   v=q.copy();v[j]+=1 if dd[j]>0 else -1;add(v)
  for k in (2,4,8):
   v=q.copy();ix=np.argsort(abs(dd)*W)[-k:];v[ix]+=np.sign(dd[ix]).astype(np.int32);add(v)
  ix=np.flatnonzero(q);order=ix[np.argsort(W[ix]*(abs(q[ix])*sc)**2+2*dd[ix]*q[ix]*sc)]
  for k in (1,3,6):
   if len(order)>=k:
    v=q.copy();v[order[:k]]=0;add(v)
  # Exact template waveform candidates, padded and aligned to polyphase grid.
  left=max(0,(pos-48)//125*125);right=min(n,((pos+nn+48+124)//125)*125);dpos=pos-left;offset=left*768//125-lag;count=(right-left)*32;lo=max(0,-offset);hi=min(int(np.ceil(count*24/125)),len(r)-offset);ix=slice(offset+lo,offset+hi);eb=err[ix];hh=hf[ix];ww=w[ix];wh=hw[ix]
  a=list(cands.values());qq=np.array([v*SCALES[ss] for _,ss,v in a]);vv=p[None,:]+idct(qq,norm='ortho',axis=-1);dd=raw(vv).reshape(len(a),nn*32)-origraw[pos:pos+nn].ravel()[None,:];dr=np.zeros((len(a),count),np.float32);dr[:,dpos*32:(dpos+nn)*32]=dd;dy=batch_filter(dr)*beta;dh=sosfiltfilt(HH,dy,axis=-1)[:,lo:hi];dy=dy[:,lo:hi];ee=eb[None,:]+dy
  cost=np.sum(ww*dy*(dy+2*eb),axis=1)+np.sum(wh*dh*(dh+2*hh),axis=1)
  p0=np.maximum(abs(eb)-threshold,0);p1=np.maximum(abs(ee)-threshold,0);cost+=pk*(np.sum(p1*p1,axis=1)-np.sum(p0*p0));cost+=.3*(np.sum(np.maximum(abs(ee)-thlow,0)**2,axis=1)-np.sum(np.maximum(abs(eb)-thlow,0)**2));cost+=(25 if profile=='Peak' else 1.)*(np.max(p1,axis=1)**2-np.max(p0)**2)
  # Extra cost for error in local spectral valleys (proxy for audibility).
  N=len(eb);window=np.ones(N);edge=min(100,N//6);window[:edge]=np.sin(np.linspace(0,np.pi/2,edge))**2;window[-edge:]=window[:edge][::-1];rf=np.fft.rfft(r[ix]*window);power=abs(rf)**2;env=gaussian_filter1d(power,3);floor=max(power.max()*1e-4,1e-12);sw=np.clip((env+floor)/(power+floor),0,8);freq=np.fft.rfftfreq(N,1/48000);sw*=((freq>=300)&(freq<=3500));ef=np.fft.rfft(eb*window);df=np.fft.rfft(dy*window,axis=1);valley=2/N*np.sum(sw*(abs(df)**2+2*np.real(df*np.conj(ef))),axis=1)
  cc.append([(b,ss,v,float(c),float(e)) for (b,ss,v),c,e in zip(a,cost,valley)]);pos+=nn
  if (i+1)%200==0:print(clip,profile,iteration,'blocks',i+1,round(time.time()-t0,2),flush=True)
 with (out/'candidates.pkl').open('wb') as fp:pickle.dump((h,ln,frames,heads,cc),fp)
 for rate in (6.,5.9):
  for mode,weight in (('base',0.),('spectral',.25)) if rate==6 else (('spectral',.25),):
   budget=(int(n*rate*1000/(8*FS))-struct.calcsize(HEADER42)-3-(ln.size+1)//2)*8-heads
   selected,used=alloc_scale(cc,budget,weight);final=[(*f[:4],cc[i][j][1],cc[i][j][2]) for i,(f,j) in enumerate(zip(frames,selected))];name=f'Viterbi-{mode}-{rate:g}k';p=out/(name+'.lp4v');b1=write_v(p,h,final,ln.tolist(),True);assert b1==heads+used,(b1,heads+used)
   ln2=build(stats(final),G,M,TYP);p2=out/(name+'-tmp.lp4v');write_v(p2,h,final,ln2,True)
   if p2.stat().st_size<p.stat().st_size:p2.replace(p)
   else:p2.unlink()
   assert p.stat().st_size<=int(n*rate*1000/(8*FS));z2,_,b2=decode_v(p,book);assert np.array_equal(z2,np.concatenate([p+idct(q*SCALES[s],norm='ortho') for _,_,_,p,s,q in final]));wav=render(z2,d,meta);wavfile.write(out/(name+'.wav'),48000,wav);m=evaluate(ref,wav,True);row=dict(clip=clip,profile=name,bytes=p.stat().st_size,kbps=p.stat().st_size*8*FS/n/1000,changed_scale=int(sum(f[4]!=a[4] for f,a in zip(frames,final))),changed_blocks=int(sum(not np.array_equal(f[-1],a[-1]) or f[4]!=a[4] for f,a in zip(frames,final))),candidates=sum(map(len,cc)),**m);(out/(name+'.json')).write_text(json.dumps(row,indent=2));print('RESULT',row,flush=True)
if __name__=='__main__':run(sys.argv[1],sys.argv[2],int(sys.argv[3]) if len(sys.argv)>3 else 1,float(sys.argv[4]) if len(sys.argv)>4 else 6.)

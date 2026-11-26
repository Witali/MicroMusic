#!/usr/bin/env python3
"""Encoder-only local optimization against the actual bin-averaged PWM waveform.
Fixed LP4V predictor/scale headers. Linear waveform delta with 125-sample alignment and halo.
Full selected bitstreams decoded and rendered again for final metrics.
"""
from compress46 import *
from scipy.signal import sosfiltfilt, resample_poly
H7=butter(5,7000,fs=48000,output='sos');H35=butter(5,3500,fs=48000,output='sos');HH=butter(5,[1500,3500],fs=48000,btype='bandpass',output='sos')

def make_raw(d,meta):
 w,q=levels(d,meta);lv,lo=np.unique(q,return_index=True);hi=np.r_[lo[1:]-1,len(q)-1];bw=meta['period']//4;v=np.array([meta['patterns'][str(int(i))] for i in w],np.int16);lut=(np.clip(v[:,:,None]-np.arange(4)*bw,0,bw).astype(np.float32)*2/bw-1).reshape(-1,32)
 def raw(z):
  j=np.clip(np.searchsorted(lv,z),1,len(lv)-1);j-=abs(z-lv[j-1])<=abs(z-lv[j]);idx=np.clip(np.rint(z*4).astype(int)+512,lo[j],hi[j]);return lut[idx].ravel()
 return raw

def filt_raw(v):return sosfiltfilt(H35,sosfiltfilt(H7,resample_poly(v,24,125)))

def run(clip,tag,mode):
 base,d,meta,ref,lv,x=data(clip);out=ROOT/clip;book=(base/'book.bin').read_bytes();path=(V45/clip/'adaptive-refit.lp4v') if tag=='v45' else out/(tag+'.lp4v');rawfile=path.read_bytes();h=struct.unpack_from(HEADER42,rawfile)[1:];ln=read_lengths(path);z,frames,oldbits=decode_v(path,book);n=h[0];g=1.0 if tag=='v45' else float(tag.split('-g')[1].split('-')[0]);raw=make_raw(d,meta);origraw=raw(z).reshape(-1,32);r=filt(ref.astype(float)/32768);r-=r.mean();y0=filt_raw(origraw.ravel());y0,lag,beta=align(r,y0);err=y0-r;hf=sosfiltfilt(HH,err);threshold=.08*np.max(abs(r));thlow=.035*np.max(abs(r));pos=0;oldn=0;heads=oldbits-sum(int(rbits(f[-1],ln,G,M)) for f in frames);cc=[];output=[];e_back=resample_poly(-err,125,768)*np.max(abs(x))*g/np.max(abs(r));start=time.time()
 # compatible alternative streams (fixed gain+scale+predictor partition)
 alts=[]
 for p in [V45/clip/'adaptive-refit.lp4v',out/'pre-g1.0-p0.65-ns1.lp4v',out/'pre-g1.0-p0.65-ns0.lp4v']:
  if p.exists():
   _,a,_=decode_v(p,book)
   if len(a)==len(frames):alts.append(a)
 for i,f in enumerate(frames):
  nominal,m,par,p,s,q=f;nn=len(q);sc=SCALES[s];fr=np.arange(nn)/nn*FS/2;W=np.maximum(1/(1+(fr/3500)**10)**2,.05)*np.sinc(fr/FS)**2;zz=z[pos:pos+nn];cands={};bb=int(rbits(q,ln,G,M));cands[q.tobytes()]=q
  def add(v):
   v=np.asarray(v,np.int32);b=int(rbits(v,ln,G,M));
   if b<=max(bb+48,bb*1.5):cands[v.tobytes()]=v
  for alt in alts:
   a=alt[i]
   if a[:3]==f[:3] and a[4]==s and len(a[-1])==nn:add(a[-1])
  # new proposals from full PWM residual, conventional precompensation, and shaped target.
  grp=int(np.count_nonzero(q)>=36)
  # pre() once, see below: compensate residual via approximate inverse hold.
  e=e_back[pos:pos+nn];cf=dct(zz+.75*pre(e,.75)-p,norm='ortho');cbase=dct(zz-p,norm='ortho');dc=cf-cbase
  for alpha in (.5,1.0,1.5):
   c=cbase+alpha*dc
   for fa in (.25,.8,2.):add(choose(c,sc,sc*sc*fa,ln,G,M,grp,W))
   # adjust only existing nonzero magnitudes, or add a few strongest error bins
   v=q.copy();ix=np.flatnonzero(q);v[ix]=np.rint(c[ix]/sc).astype(np.int32);add(v)
   for k in (2,5):
    v=q.copy();ix=np.argsort(abs(dc))[-k:];v[ix]=np.rint(c[ix]/sc).astype(np.int32);add(v)
  # waveform delta over fixed-length block plus halo; start aligned to 125 PCM samples.
  left=max(0,(pos-48)//125*125);right=min(n,((pos+nn+48+124)//125)*125);dpos=pos-left;offset=left*768//125-lag;count=(right-left)*32;lo=max(0,-offset);hi=min(int(np.ceil(count*24/125)),len(r)-offset);ix=slice(offset+lo,offset+hi);eb=err[ix];hh=hf[ix]
  rows=[];wpk=0. if mode=='snr' else 6.;whf=.15 if mode=='snr' else .25
  pk0=np.maximum(abs(eb)-threshold,0);pl0=np.maximum(abs(eb)-thlow,0)
  for v in cands.values():
   b=int(rbits(v,ln,G,M));
   if np.array_equal(v,q):rows.append((b,0.,v));continue
   zz2=p+idct(v*sc,norm='ortho');a=raw(zz2).reshape(-1,32)-origraw[pos:pos+nn];delta0=np.zeros(count,np.float32);delta0[dpos*32:(dpos+nn)*32]=a.ravel();delta=filt_raw(delta0)*beta;dd=delta[lo:hi];ee=eb+dd;dh=sosfiltfilt(HH,delta)[lo:hi];cost=float(np.dot(dd,dd+2*eb))+whf*float(np.dot(dh,dh+2*hh));pk=np.maximum(abs(ee)-threshold,0);pl=np.maximum(abs(ee)-thlow,0);cost+=wpk*float(np.dot(pk,pk)-np.dot(pk0,pk0))+.25*float(np.dot(pl,pl)-np.dot(pl0,pl0));rows.append((b,cost,v))
  cc.append(rows);pos+=nn
  if (i+1)%200==0:print(clip,tag,mode,'blocks',i+1,round(time.time()-start,2),flush=True)
 # Exact rate with fixed headers. Pick independent local candidate costs, budget enforced.
 budget=int(n*6000/(8*FS))*8-(struct.calcsize(HEADER42)+3+(ln.size+1)//2)*8-heads
 B=np.full((len(cc),max(map(len,cc))),1e8);E=np.full_like(B,np.inf)
 for i,ls in enumerate(cc):
  for j,(b,e,q) in enumerate(ls):B[i,j]=b;E[i,j]=e
 lo=0.;hi=1.;best=None
 for _ in range(48):
  la=(lo+hi)/2;j=(E+la*B).argmin(axis=1);bits=int(B[np.arange(len(j)),j].sum())
  if bits<=budget:hi=la;best=j;used=bits
  else:lo=la
 assert best is not None
 final=[(*f[:-1],cc[i][j][2]) for i,(f,j) in enumerate(zip(frames,best))];name=f'out-{tag}-{mode}';p=out/(name+'.lp4v');b1=write_v(p,h,final,ln.tolist(),True);assert b1==heads+used;assert p.stat().st_size<=int(n*6000/(8*FS));z2,_,b2=decode_v(p,book);assert b2==b1;assert np.array_equal(z2,np.concatenate([p+idct(q*SCALES[s],norm='ortho') for _,_,_,p,s,q in final]));wav=render(z2,d,meta);wavfile.write(out/(name+'.wav'),48000,wav);m=evaluate(ref,wav,True);row=dict(clip=clip,profile=name,bytes=p.stat().st_size,kbps=p.stat().st_size*8*FS/n/1000,changed_blocks=int(sum(not np.array_equal(f[-1],a[-1]) for f,a in zip(frames,final))),**m);(out/(name+'.json')).write_text(json.dumps(row,indent=2));print('RESULT',row,flush=True)
if __name__=='__main__':run(*sys.argv[1:])

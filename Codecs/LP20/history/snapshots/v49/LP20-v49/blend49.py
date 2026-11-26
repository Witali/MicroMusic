#!/usr/bin/env python3
"""Mix complete compatible coefficient frames from Viterbi and v48; exact byte accounting."""
from refine49 import *
import shutil

def run(c):
 base,d,meta,ref,lv,x=data(c);out=ROOT48/c;path=V48/c/'Recommended.lp4v';book=(base/'book.bin').read_bytes();h=struct.unpack_from(HEADER42,path.read_bytes())[1:];ln=read_lengths(path);z,frames,oldbits=decode_v(path,book);n=len(z);raw=make_raw(d,meta);orig=raw(z).reshape(-1,32);r=filt(ref.astype(float)/32768);r-=r.mean();y0,lag,beta=align(r,filt_raw(orig.ravel()));err=y0-r;hf=sosfiltfilt(HH,err);w,hw=weights(r,True);peak=np.max(abs(r));threshold=.065*peak
 alts=[decode_v(p,book)[1] for p in sorted(out.glob('Viterbi-*.lp4v'))];assert all(len(f)==len(frames) for f in alts)
 heads=oldbits-sum(int(rbits(f[-1],ln,G,M)) for f in frames)-7-sum(4 if abs(a[4]-b[4])<=7 else 11 for a,b in zip(frames,frames[1:]));pos=0;cc=[]
 for i,f in enumerate(frames):
  nominal,m,par,p,s,q=f;nn=len(q);cand={}
  for a in [f]+[a[i] for a in alts]:
   assert a[:3]==f[:3] and np.array_equal(a[3],p)
   ss,v=a[4:];cand[(ss,v.tobytes())]=(int(rbits(v,ln,G,M)),ss,v)
  aa=list(cand.values());left=max(0,(pos-48)//125*125);right=min(n,((pos+nn+48+124)//125)*125);off=left*768//125-lag;count=(right-left)*32;lo=max(0,-off);hi=min(int(np.ceil(count*24/125)),len(r)-off);ix=slice(off+lo,off+hi);eb=err[ix];hh=hf[ix];ww=w[ix];wh=hw[ix]
  qq=np.array([v*SCALES[ss] for _,ss,v in aa]);vv=p[None,:]+idct(qq,norm='ortho',axis=-1);dd=raw(vv).reshape(len(aa),nn*32)-orig[pos:pos+nn].ravel()[None,:];dr=np.zeros((len(aa),count),np.float32);dr[:,(pos-left)*32:(pos-left+nn)*32]=dd;dy=batch_filter(dr)*beta;dh=sosfiltfilt(HH,dy,axis=-1)[:,lo:hi];dy=dy[:,lo:hi];ee=eb[None,:]+dy;pk0=np.maximum(abs(eb)-threshold,0);pk1=np.maximum(abs(ee)-threshold,0)
  cost=np.sum(ww*dy*(dy+2*eb),axis=1)+np.sum(wh*dh*(dh+2*hh),axis=1)+18*(np.sum(pk1*pk1,axis=1)-np.sum(pk0*pk0))
  # Separate spectral-envelope criterion (not a replacement for full STOI measurement).
  N=len(eb);window=np.hanning(N);rf=np.fft.rfft(r[ix]*window);power=abs(rf)**2;env=gaussian_filter1d(power,3);floor=max(power.max()*1e-4,1e-12);sw=np.clip((env+floor)/(power+floor),0,8);freq=np.fft.rfftfreq(N,1/48000);sw*=((freq>=300)&(freq<=3500));ef=np.fft.rfft(eb*window);df=np.fft.rfft(dy*window,axis=1);valley=2/N*np.sum(sw*(abs(df)**2+2*np.real(df*np.conj(ef))),axis=1)
  Y=np.fft.rfft(y0[ix]*window);af=np.abs(rf);floor2=max(af.max()*.01,1e-8);band=(freq>=150)&(freq<=3500);a0=np.log(np.maximum(abs(Y),floor2)/np.maximum(af,floor2));a1=np.log(np.maximum(abs(Y[None,:]+df),floor2)/np.maximum(af[None,:],floor2));ls=np.mean(a1[:,band]**2-a0[None,band]**2,axis=1);sc=max(np.sum((r[ix]*window)**2),1e-6)*.03
  cc.append([(b,ss,v,float(co),float(va),float(l*sc)) for (b,ss,v),co,va,l in zip(aa,cost,valley,ls)]);pos+=nn
 for weight in (0.,.5,2.):
  alt=[[(b,s,q,cost+.2*valley,ls) for b,s,q,cost,valley,ls in ls0] for ls0 in cc]
  budget=(int(n*6000/(8*FS))-struct.calcsize(HEADER42)-3-(ln.size+1)//2)*8-heads
  sel,used=alloc_scale(alt,budget,weight);final=[(*f[:4],cc[i][j][1],cc[i][j][2]) for i,(f,j) in enumerate(zip(frames,sel))];name=f'Blend-{weight:g}';p=out/(name+'.lp4v');b1=write_v(p,h,final,ln.tolist(),True);assert b1==heads+used;ln2=build(stats(final),G,M,TYP);p2=p.with_name(p.stem+'-tmp.lp4v');write_v(p2,h,final,ln2,True)
  if p2.stat().st_size<p.stat().st_size:p2.replace(p)
  else:p2.unlink()
  assert p.stat().st_size<=int(n*6000/(8*FS));zz,_,_=decode_v(p,book);assert np.array_equal(zz,np.concatenate([a+idct(q*SCALES[s],norm='ortho') for _,_,_,a,s,q in final]));wav=render(zz,d,meta);wavfile.write(p.with_suffix('.wav'),48000,wav);mm=evaluate(ref,wav,True);row=dict(clip=c,profile=name,bytes=p.stat().st_size,kbps=p.stat().st_size*8*FS/n/1000,changed_blocks=sum(int(a[4]!=b[4] or not np.array_equal(a[-1],b[-1])) for a,b in zip(frames,final)),**mm);p.with_suffix('.json').write_text(json.dumps(row,indent=2));print('RESULT',row,flush=True)
if __name__=='__main__':run(sys.argv[1])

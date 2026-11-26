#!/usr/bin/env python3
"""Encoder-side precompensation, fixed v45 partition, actual LP4V bit budget."""
from study46 import *

def read_lengths(path):
 raw=path.read_bytes();o=struct.calcsize(HEADER42)+3;tr=Reader(raw[o:o+108]);return np.array([[tr.get(4) for _ in range(36)] for _ in range(nc(TYP))],np.int32)

def shiftgain(g,delta):return (g&128)|max(0,min(127,(g&127)+delta))
def pred_gain(f,wt,st,g):
 nominal,m,par,p,s,q=f;nn=len(q);delta=int(round(12*np.log2(g)))
 if not m:return par,p
 pa=list(par);pa[3]=shiftgain(pa[3],delta);v=wave(wt[pa[1]],st[pa[0]],pa[2],pa[3],nn)
 if m>=2:
  pa[6]=shiftgain(pa[6],delta);a=np.linspace(0,1,nn);v=v*(1-a)+wave(wt[pa[4]],st[pa[0]],pa[5],pa[6],nn)*a
 return tuple(pa),v

def run(clip,g,amount,shaping):
 base,d,meta,ref,lv,x=data(clip);out=ROOT/clip;out.mkdir(exist_ok=True);path=V45/clip/'adaptive-refit.lp4v';book=(base/'book.bin').read_bytes();raw=path.read_bytes();h=struct.unpack_from(HEADER42,raw)[1:];ln=read_lengths(path);assert ln.shape==(nc(TYP),36),ln.shape
 z0,frames,_=decode_v(path,book);assert np.array_equal(render(z0,d,meta),wavfile.read(V45/clip/'adaptive-refit.wav')[1]);n,_,grid,K,L,b=h;wt=wave_table(unpack_book(book,K,L,b));st=steps(grid)
 t=pre(x*g,amount);pos=0;heads=0;oldm=0;oldp=();oldn=0;olds=None;cc=[];outframes=[];threshold=.065*np.max(abs(x))*g
 for f in frames:
  nominal,m,par,p,s,q=f;nn=len(q);target=t[pos:pos+nn];pa,pnew=pred_gain(f,wt,st,g);ss=int(np.clip(s+round(10*np.log2(g)),0,127));sc=SCALES[ss];fr=np.arange(nn)/nn*FS/2;W=np.maximum(1/(1+(fr/3500)**10)**2,.05)*np.sinc(fr/FS)**2
  heads+=length_fields(nominal)[1]+sum(w for _,w in fields(m,pa,oldm,oldp,grid,K,oldn,st))+(7 if olds is None else sum(w for _,w in delta(ss,olds,7,4)));oldm,oldp,oldn,olds=m,pa,nn,ss
  outframes.append((nominal,m,pa,pnew,ss));cand={}
  def add(q1):
   q1=q1.astype(np.int32);key=q1.tobytes()
   if key in cand:return
   z=pnew+idct(q1*sc,norm='ortho');e=quant(z,lv)-target;e=sosfiltfilt(FILT,e) if nn>24 else e
   cost=float(e@e)+2*float(np.sum(np.maximum(abs(e)-threshold,0)**2));bits=int(rbits(q1,ln,G,M));cand[key]=(bits,cost,q1)
  add(q);add(np.zeros(nn,np.int32));c=dct(target-pnew,norm='ortho');grp=int(np.count_nonzero(q)>=36)
  for fct in (.12,.35,.8,1.8,4.):add(choose(c,sc,sc*sc*fct,ln,G,M,grp,W))
  for dz in (.6,1.15,1.8):add(np.where(abs(c)>=sc*dz,np.rint(c/sc),0))
  z=pnew+idct(q*sc,norm='ortho');qe=quant(z,lv)-z
  # Encoder-only error-feedback target: use shaped desired waveform, then fit coefficients.
  if shaping:
   zsh=shape(target,lv,.35,0.);cf=dct(target+.7*(zsh-quant(target,lv))-.65*qe-pnew,norm='ortho')
  else:cf=dct(target-.8*qe-pnew,norm='ortho')
  for fct in (.25,.65,1.5,3.):add(choose(cf,sc,sc*sc*fct,ln,G,M,grp,W))
  vals=list(cand.values());cc.append(vals);pos+=nn
  if len(cc)%200==0:print(clip,g,amount,shaping,'blocks',len(cc),flush=True)
 budget=int(n*6000/(8*FS))*8-(struct.calcsize(HEADER42)+3+(ln.size+1)//2)*8-heads
 B=np.full((len(cc),max(map(len,cc))),1e8);E=np.full_like(B,np.inf)
 for i,ls in enumerate(cc):
  for j,(b,e,q) in enumerate(ls):B[i,j]=b;E[i,j]=e
 lo=0.;hi=max(1.,np.nanmax(E[np.isfinite(E)]));best=None
 for _ in range(40):
  la=(lo+hi)/2;j=(E+la*B).argmin(axis=1);bits=int(B[np.arange(len(j)),j].sum())
  if bits<=budget:hi=la;best=j;used=bits
  else:lo=la
 assert best is not None
 final=[(*f,cc[i][j][2]) for i,(f,j) in enumerate(zip(outframes,best))];tag=f'pre-g{g}-p{amount}-ns{int(shaping)}';p=out/(tag+'.lp4v');b1=write_v(p,h,final,ln.tolist(),True);assert b1==used+heads,(b1,used+heads);assert p.stat().st_size<=int(n*6000/(8*FS));z,fr,b2=decode_v(p,book);assert b1==b2;assert np.array_equal(z,np.concatenate([p+idct(q*SCALES[s],norm='ortho') for _,_,_,p,s,q in final]));w=render(z,d,meta);wavfile.write(out/(tag+'.wav'),48000,w);mm=evaluate(ref,w,True);r=dict(clip=clip,profile=tag,kbps=p.stat().st_size*8*FS/n/1000,bytes=p.stat().st_size,input_gain=g,preemphasis=amount,shaping=shaping,**mm);(out/(tag+'.json')).write_text(json.dumps(r,indent=2));print('RESULT',r,flush=True)
if __name__=='__main__':run(sys.argv[1],float(sys.argv[2]),float(sys.argv[3]),bool(int(sys.argv[4])))

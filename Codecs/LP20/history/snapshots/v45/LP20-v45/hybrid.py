#!/usr/bin/env python3
"""LP20 v41 software-only pilot: cross-recording sampled waveform dictionary,
log-pitch DDS, optional two-template morph, sparse transform residual, VBR.
All transmitted parameters are included in the actual bitstream.
"""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
import sys,math,json,struct,time,argparse
import numpy as np
from scipy.signal import butter,sosfiltfilt,correlate,find_peaks,resample
from scipy.ndimage import spline_filter,map_coordinates
from scipy.fft import dct,idct
from sklearn.cluster import KMeans
from numba import njit
FS=7812.5; P=256
SCALES=.125*2.**(np.arange(128)/10.)
GAINS=.125*2.**(np.arange(128)/12.)
MAGBITS=np.zeros(32768,np.int16);MAGBITS[1:]=2*np.floor(np.log2(np.arange(1,32768))).astype(np.int16)+2
HEADER='<4sIHHBB'
class Writer:
 def __init__(self):self.bits=[]
 def put(self,v,n):
  assert 0<=int(v)<(1<<n);self.bits.extend((int(v)>>i)&1 for i in range(n-1,-1,-1))
 def unary(self,v):self.bits.extend([0]*int(v)+[1])
 def eg(self,v):
  w=int(v)+1;l=w.bit_length()-1;self.unary(l);self.put(w-(1<<l),l)
 def bytes(self):return np.packbits(np.array(self.bits,np.uint8)).tobytes()
class Reader:
 def __init__(self,b):self.bits=np.unpackbits(np.frombuffer(b,np.uint8));self.pos=0
 def get(self,n):
  if self.pos+n>len(self.bits):raise ValueError('truncated bitstream')
  v=0
  for x in self.bits[self.pos:self.pos+n]:v=(v<<1)|int(x)
  self.pos+=n;return v
 def unary(self):
  n=0
  while not self.get(1):n+=1
  return n
 def eg(self):
  n=self.unary();return (1<<n)+self.get(n)-1

def pitch_analysis(x,centers):
 low=sosfiltfilt(butter(4,1100,fs=FS,output='sos'),x);W=392;lo=int(FS/450);hi=int(FS/70);lags=np.arange(hi+2);gate=np.max(low*low)*10**(-35/10);out=[];s=np.pad(low,(W//2,W//2))
 for c in centers:
  a=s[c:c+W].copy();a-=a.mean()
  if np.mean(a*a)<gate:out.append((0.,0.));continue
  ac=correlate(a,a,mode='full',method='fft')[W-1:W+hi+1];cs=np.r_[0,np.cumsum(a*a)];ac/=np.sqrt(np.maximum(cs[W-lags]*(cs[W]-cs[lags]),1e-20));peaks=find_peaks(ac)[0];peaks=peaks[(peaks>=lo)&(peaks<=hi)]
  if not len(peaks) or ac[peaks].max()<.68:out.append((0.,0.));continue
  k=peaks[np.flatnonzero(ac[peaks]>=max(.68,ac[peaks].max()*.93))[0]];a,b,z=ac[k-1:k+2];den=a-2*b+z;off=.5*(a-z)/den if den<0 else 0.;freq=FS/(k+off);out.append((freq if 70<=freq<=450 else 0.,float(b)))
 return np.array(out)
def train(x,K,L):
 centers=np.arange(256,len(x)-256,78);ps=pitch_analysis(x,centers);coef=spline_filter(x);cycles=[]
 for c,(fr,score) in zip(centers,ps):
  if fr==0 or score<.76:continue
  T=FS/fr
  for shift in [-.55,.45]:
   w=map_coordinates(coef,[c+shift*T+np.arange(256)*T/256],order=3,prefilter=False);w-=w.mean();ft=np.fft.rfft(w);phase=np.angle(ft[1]);ft*=np.exp(-1j*np.arange(len(ft))*phase);w=np.fft.irfft(ft,256);w=resample(w,L);norm=np.linalg.norm(w)
   if norm>.1:cycles.append(w/norm)
 cycles=np.asarray(cycles);assert len(cycles)>=K
 b=KMeans(n_clusters=K,n_init=3,random_state=42).fit(cycles).cluster_centers_;b/=np.maximum(np.max(np.abs(b),axis=1,keepdims=True),1e-12);return np.clip(np.rint(b*127),-127,127).astype(np.int8),len(cycles)
def wave_table(book):
 L=book.shape[1];a=np.arange(P)*L/P;j=a.astype(int);return (book[:,j]*(1-(a-j))+book[:,(j+1)%L]*(a-j))/127.
def steps(grid):return np.rint(65536*np.geomspace(70,450,grid)/FS).astype(np.int32)
def wave(w,step,p,g,n):
 phase=(np.arange(n,dtype=np.int64)*int(step)+p*256)&65535;j=phase>>8;frac=(phase&255)/256.;return ((1-frac)*w[j]+frac*w[(j+1)%P])*(GAINS[g&127]*(-1 if g>=128 else 1))
def fit(x,weight,step,wt,fft):
 n=len(x);phase=(np.arange(n,dtype=np.int64)*int(step))&65535;j=phase>>8;frac=(phase&255)/256.;j1=(j+1)%P
 a=np.bincount(j,x*weight*(1-frac),P)+np.bincount(j1,x*weight*frac,P);b=np.bincount(j,weight**2*(1-frac)**2,P)+np.bincount(j1,weight**2*frac**2,P);c=np.bincount(j,weight**2*2*frac*(1-frac),P)
 dot=np.fft.irfft(np.conj(np.fft.rfft(a))[None,:]*fft[0],n=P,axis=1);en=np.maximum(np.fft.irfft(np.conj(np.fft.rfft(b))[None,:]*fft[1]+np.conj(np.fft.rfft(c))[None,:]*fft[2],n=P,axis=1),1e-12)
 gain=dot/en;gc=np.clip(np.rint(np.log2(np.maximum(abs(gain),GAINS[0])/GAINS[0])*12),0,127).astype(int);g=GAINS[gc]*np.sign(gain);score=2*g*dot-g*g*en;idx,p=np.unravel_index(np.argmax(score),score.shape);code=int(gc[idx,p])+128*int(gain[idx,p]<0)
 return (int(idx),int(p),code),wave(wt[idx],step,p,code,n)
def pred(x,f,wt,fft,grid):
 if not f:return []
 q=int(np.clip(np.rint(np.log(f/70)/np.log(450/70)*(grid-1)),0,grid-1));st=steps(grid);cands=[];one=np.ones(len(x));alpha=np.linspace(0,1,len(x))
 for i in range(max(0,q-2),min(grid,q+3)):
  par,y=fit(x,one,st[i],wt,fft);cands.append((float(np.dot(x-y,x-y)),i,par,y))
 cands.sort(key=lambda z:z[0]);_,i,par,y=cands[0];out=[(1,(i,*par),y)]
 a=1-alpha;b=alpha;pa=pb=par;ya=yb=y.copy()
 for _ in range(2):pa,ya=fit(x-b*yb,a,st[i],wt,fft);pb,yb=fit(x-a*ya,b,st[i],wt,fft)
 out.append((2,(i,*pa,*pb),a*ya+b*yb));return out
@njit(cache=True)
def quant_choices(c,maxbits,scales,mb):
 n=len(c);best=np.full(maxbits+1,1e30);bs=np.full(maxbits+1,-1,np.int16);bk=np.full(maxbits+1,-1,np.int8)
 for i in range(len(scales)):
  s=scales[i];q=np.rint(c/s).astype(np.int32);err=np.sum((c-q*s)**2);costs=np.full(4,10,np.int32);prev=-1
  for j in range(n):
   z=abs(q[j]);
   if z==0:continue
   if z>=len(mb):z=len(mb)-1
   gap=j-prev-1;prev=j
   for k in range(4):costs[k]+=1+(gap>>k)+1+k+mb[z]
  k=np.argmin(costs);cost=costs[k]
  if cost<=maxbits and err<best[cost]:best[cost]=err;bs[cost]=i;bk[cost]=k
 err=np.sum(c*c)
 if err<best[10]:best[10]=err;bs[10]=-2;bk[10]=0
 for b in range(1,maxbits+1):
  if best[b-1]<best[b]:best[b]=best[b-1];bs[b]=bs[b-1];bk[b]=bk[b-1]
 return bs,bk,best
def encode_packet(mode,par,coeff,scale,rice,grid,K):
 w=Writer();w.put(mode,2)
 if mode:
  w.put(par[0],int(math.log2(grid)));a=1
  for _ in range(mode):w.put(par[a],int(math.log2(K)));w.put(par[a+1],8);w.put(par[a+2],8);a+=3
 w.put(max(scale,0),7);w.put(rice,2);q=np.zeros(len(coeff),int) if scale==-2 else np.rint(coeff/SCALES[scale]).astype(int);prev=-1
 for j in np.flatnonzero(q):
  z=q[j];gap=j-prev-1;prev=j;w.put(1,1);w.unary(gap>>rice);w.put(gap&((1<<rice)-1),rice);w.eg(abs(z)-1);w.put(int(z<0),1)
 w.put(0,1);return w.bytes()
def decode_packet(buf,wt,n,grid,K):
 r=Reader(buf);mode=r.get(2);p=np.zeros(n)
 if mode:
  st=steps(grid)[r.get(int(math.log2(grid)))];waves=[];assert mode in (1,2)
  for _ in range(mode):i=r.get(int(math.log2(K)));a=r.get(8);g=r.get(8);waves.append(wave(wt[i],st,a,g,n))
  p=waves[0] if mode==1 else waves[0]*(1-np.linspace(0,1,n))+waves[1]*np.linspace(0,1,n)
 scale=r.get(7);rice=r.get(2);q=np.zeros(n);j=-1
 while r.get(1):
  gap=(r.unary()<<rice)|r.get(rice);j+=gap+1
  if j>=n:raise ValueError('bad coefficient position')
  mag=r.eg()+1;q[j]=mag*(-1 if r.get(1) else 1)
 assert not r.bits[r.pos:].any();return p+idct(q*SCALES[scale],norm='ortho'),mode

def make_candidates(x,fr,wt,fft,grid,K,maxbyte):
 preds=[(0,(),np.zeros(len(x)))]+pred(x,fr,wt,fft,grid);out=[]
 for mode,par,p in preds:
  c=dct(x-p,norm='ortho');head=2+(int(math.log2(grid))+mode*(int(math.log2(K))+16) if mode else 0);bs,bk,err=quant_choices(c,maxbyte*8-head,SCALES,MAGBITS);prev=None
  for budget in range(2,maxbyte+1):
   b=budget*8-head
   if b<0 or bs[b]==-1:continue
   key=(int(bs[b]),int(bk[b]))
   if key==prev:continue
   prev=key;buf=encode_packet(mode,par,c,*key,grid,K);assert len(buf)<=budget
   # Orthogonal transform exact coefficient SSE; check full selected stream later.
   out.append((len(buf)+1,float(err[b]),buf,mode))
 return out

def allocate(candidates,budget):
 lo=0.;hi=max(1.,max(max(c[1] for c in a) for a in candidates));best=None
 for _ in range(34):
  mid=(lo+hi)/2;ix=[min(range(len(a)),key=lambda j:a[j][1]+mid*a[j][0]) for a in candidates];size=sum(a[i][0] for a,i in zip(candidates,ix))
  if size<=budget:hi=mid;best=ix
  else:lo=mid
 assert best is not None
 size=sum(a[i][0] for a,i in zip(candidates,best));rem=budget-size
 while rem:
  choices=[]
  for k,(a,i) in enumerate(zip(candidates,best)):
   for j,c in enumerate(a):
    db=c[0]-a[i][0];dg=a[i][1]-c[1]
    if 0<db<=rem and dg>0:choices.append((dg/db,dg,k,j,db))
  if not choices:break
  _,_,k,j,db=max(choices);best[k]=j;rem-=db
 return [a[i] for a,i in zip(candidates,best)]
def decode_file(path,book):
 raw=Path(path).read_bytes();magic,n,frame,grid,K,L=struct.unpack_from(HEADER,raw);assert magic==b'LP41' and book.shape==(K,L);p=struct.calcsize(HEADER);wt=wave_table(book);out=[];m=[];pos=0
 while pos<n:
  l=raw[p];p+=1;nn=min(frame,n-pos);z,mode=decode_packet(raw[p:p+l],wt,nn,grid,K);p+=l;out.append(z);m.append(mode);pos+=nn
 assert p==len(raw);return np.concatenate(out),np.array(m)
def run(clip,train_path,test_path,out,K=64,L=64,grid=512,frame=128):
 out=Path(out);out.mkdir(exist_ok=True,parents=True);d=dict(np.load(test_path));x=d['target'];trainx=np.load(train_path)['target'];book,count=train(trainx,K,L);book.tofile(out/'book.bin');wt=wave_table(book);fft=[np.fft.rfft(w,axis=1) for w in (wt,wt*wt,wt*np.roll(wt,-1,axis=1))];p0=np.arange(0,len(x),frame);f0=pitch_analysis(x,np.minimum(p0+frame//2,len(x)-1));cands=[];start=time.time()
 for k,(p,(fr,score)) in enumerate(zip(p0,f0)):
  a=make_candidates(x[p:p+frame],fr,wt,fft,grid,K,40);cands.append(a)
  if k%200==199:print(clip,'candidates',k+1,'seconds',round(time.time()-start,1),flush=True)
 header=struct.pack(HEADER,b'LP41',len(x),frame,grid,K,L);budget=int(len(x)*1000/FS)-len(header);results=[]
 for tag,modes in [('transform',(0,)),('sample',(0,1)),('morph',(0,1,2))]:
  a=[[c for c in v if c[-1] in modes] for v in cands];sel=allocate(a,budget);path=out/(tag+'.lp41');path.write_bytes(header+b''.join(bytes([len(c[2])])+c[2] for c in sel));z,m=decode_file(path,book);err=x-z;met=dict(clip=clip,profile=tag,frame=frame,grid=grid,K=K,L=L,train_cycles=count,bytes=path.stat().st_size,kbps=path.stat().st_size*8*FS/len(x)/1000,book_bytes=book.nbytes,dds_table_bytes=grid*2,frame_count=len(m),mode_counts=np.bincount(m,minlength=3).tolist(),pcm_snr=10*np.log10(np.dot(x,x)/np.dot(err,err)));assert met['kbps']<=8;assert np.isclose(np.dot(err,err),sum(c[1] for c in sel),rtol=1e-6);np.save(out/(tag+'.npy'),z);results.append(met);print('RESULT',met,flush=True)
 (out/'results.json').write_text(json.dumps(results,indent=2));return results
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('clip');ap.add_argument('train');ap.add_argument('test');ap.add_argument('out');ap.add_argument('--k',type=int,default=64);ap.add_argument('--length',type=int,default=64);ap.add_argument('--grid',type=int,default=512);ap.add_argument('--frame',type=int,default=128);a=ap.parse_args();run(a.clip,a.train,a.test,a.out,a.k,a.length,a.grid,a.frame)

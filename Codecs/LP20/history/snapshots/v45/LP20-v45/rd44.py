#!/usr/bin/env python3
"""Rate-distortion search for the actual LP4S joint prefix code.
Keeps predictor parameters, waveform table, DDS and PWM fixed. PC only.
Searches sparse coefficient positions and magnitudes in the context-dependent
Huffman cost model; final actual bitstream length and PCM verified.
"""
from lp4s import *
from scipy.signal import resample_poly,butter,sosfiltfilt
from scipy.io import wavfile
from scipy.ndimage import gaussian_filter1d
import csv,shutil

@njit(cache=True)
def eg(v):
 z=v+1;l=0
 while z>1:z>>=1;l+=1
 return 2*l+1

@njit(cache=True)
def band(p):return int(p>=32)+int(p>=96)

@njit(cache=True)
def choose(c,scale,lam,ln,G,M,group,weight):
 # Predecessor cost is independent of magnitude within each capped gap class.
 n=len(c);d=np.full(n,1e100);parent=np.full(n,-1,np.int32);vals=np.zeros(n,np.int32);end=-1;best=0.
 for j in range(n):
  pp=np.full((3,G+1),1e100);pi=np.full((3,G+1),-1,np.int32)
  for i in range(-1,j):
   g=j-i-1;gg=min(g,G);cc=band(i);v=(d[i] if i>=0 else 0.)+lam*(eg(g-G) if g>=G else 0)
   if v<pp[cc,gg]:pp[cc,gg]=v;pi[cc,gg]=i
  a=abs(c[j]);ideal=max(1,int(np.rint(a/scale)));vbest=1e100;iv=-1;mv=1
  for mc in range(1,M+1):
   q=mc;extra=0
   if mc==M:
    # Escape EG categories: best value in each interval, including the nearest.
    vmag=1e100;qq=M
    l=0;low=M
    while True:
     high=M+(1<<(l+1))-2;vv=min(max(ideal,low),high);cost=weight[j]*((a-scale*vv)**2-a*a)+lam*(2*l+1)
     if cost<vmag:vmag=cost;qq=vv
     if high>=ideal:break
     l+=1;low=high+1
    q=qq;extra=eg(q-M)
   er=weight[j]*((a-scale*q)**2-a*a)+lam*(1+extra+1/32.)
   for cc in range(3):
    for gg in range(G+1):
     z=pp[cc,gg]+lam*ln[cc+3*group,gg*M+mc-1]+er
     if z<vbest:vbest=z;iv=pi[cc,gg];mv=q
  d[j]=vbest;parent[j]=iv;vals[j]=mv if c[j]>=0 else -mv
  if vbest<best:best=vbest;end=j
 q=np.zeros(n,np.int32)
 while end>=0:q[end]=vals[end];end=parent[end]
 return q

@njit(cache=True)
def rbits(q,ln,G,M):
 cnt=np.count_nonzero(q);prev=-1;nb=6+(cnt>>5);grp=3*int(cnt>=36)
 for j in range(len(q)):
  if q[j]:
   g=j-prev-1;mag=abs(q[j]);nb+=ln[band(prev)+grp,min(g,G)*M+min(mag,M)-1]+1
   if g>=G:nb+=eg(g-G)
   if mag>=M:nb+=eg(mag-M)
   prev=j
 return nb

def levels(d,meta):
 vals=d['ww10'];w=np.array([min(vals,key=lambda w:(abs(w-(1280+v*1120/512)),abs(w-1280))) for v in range(-512,512)])
 q=(np.array([sum(meta['patterns'][str(int(i))]) for i in w])-1280)*128/1120
 return w,q

def quant(z,lv):
 j=np.clip(np.searchsorted(lv,z),1,len(lv)-1);j-=abs(z-lv[j-1])<=abs(z-lv[j]);return lv[j]

def render(z,d,meta):
 # Exact legacy bin-averaged PWM render, same widths / filter as v42.
 w,q=levels(d,meta);lv,lo=np.unique(q,return_index=True);hi=np.r_[lo[1:]-1,len(q)-1];j=np.clip(np.searchsorted(lv,z),1,len(lv)-1);j-=abs(z-lv[j-1])<=abs(z-lv[j]);y=(np.clip(np.rint(z*4).astype(int)+512,lo[j],hi[j])-512).astype(np.int16)
 v,inv=np.unique(w[y+512],return_inverse=True);p=meta['period'];widths=np.array([meta['patterns'][str(int(k))] for k in v],dtype=np.int16)[inv].ravel();bw=p//4;g=math.gcd(48000*bw,20000000)
 a=(np.clip(widths[:,None]-np.arange(4)*bw,0,bw).astype(np.float32)*2/bw-1).ravel();a=resample_poly(a,48000*bw//g,20000000//g);a=sosfiltfilt(butter(5,7000,fs=48000,output='sos'),a)/.875*128/127;r=resample_poly(d['target']/127,768,125);gain=.98/max(abs(r));a=a*gain*min(1,.98/(max(abs(a))*gain));return np.clip(np.rint(a*32767),-32768,32767).astype(np.int16)

def metrics(ref,out):
 from peak_audit import filt,align,metrics as peak_metrics
 from scipy.signal import stft
 from pystoi import stoi
 x=filt(ref.astype(float)/32768);x-=x.mean();v=filt(out.astype(float)/32768);m=peak_metrics(x,v);y,_,_=align(x,v);sl=slice(480,-480);e=y-x
 f,tt,S=stft(x,48000,nperseg=1536,noverlap=1152,nfft=2048);_,_,Y=stft(y,48000,nperseg=1536,noverlap=1152,nfft=2048);band=(f>=150)&(f<=3500);L=960;fr=x[:len(x)//L*L].reshape(-1,L);power=np.mean(fr**2,axis=1);active=power>=power.max()*10**(-3.5);fi=np.minimum((tt*48000/L).astype(int),len(fr)-1);A=abs(S[band][:,active[fi]]);Z=abs(Y[band][:,active[fi]]);floor=np.maximum(A.max(axis=0)*10**(-45/20),np.max(A)*10**(-65/20));ac=np.zeros(len(fr));pitch=np.zeros(len(fr))
 for i in np.flatnonzero(active):
  u=fr[i,::6];u=u-u.mean();r=np.array([np.dot(u[:-j],u[j:])/np.sqrt(np.dot(u[:-j],u[:-j])*np.dot(u[j:],u[j:])+1e-24) for j in range(20,101)]);ac[i]=r.max();peaks=np.flatnonzero((r[1:-1]>=r[:-2])&(r[1:-1]>=r[2:])&(r[1:-1]>=.9*ac[i]))+1;lag=int(peaks[0] if len(peaks) else r.argmax())+20;pitch[i]=8000/lag
 voice=active&(ac>=.65);vm=np.pad(np.repeat(voice,L),(0,len(x)-len(fr)*L));hf=sosfiltfilt(butter(5,[1500,3500],fs=48000,btype='bandpass',output='sos'),e);fh,th,EH=stft(e,48000,nperseg=3072,noverlap=2304,nfft=4096);fi2=np.minimum((th*48000/L).astype(int),len(fr)-1);p=np.maximum(pitch[fi2],1);dist=abs(fh[:,None]/p[None,:]-np.rint(fh[:,None]/p[None,:]))*p[None,:];valley=(dist>=np.maximum(30,.23*p)[None,:])&(fh[:,None]>=300)&(fh[:,None]<=3500)&voice[fi2][None,:]
 m.update(stoi=float(stoi(x[sl],y[sl],48000,extended=False)),lsd_db=float(np.mean(np.sqrt(np.mean((20*np.log10(np.maximum(Z,floor[None,:])/np.maximum(A,floor[None,:])))**2,axis=0)))),spectral_convergence_pct=float(100*np.linalg.norm(A-Z)/np.linalg.norm(A)),hf_voiced_error_power=float(np.mean(hf[vm]**2)),valley_error_power=float(np.mean(abs(EH[valley])**2)),corr=float(np.corrcoef(x[sl],y[sl])[0,1]));return m

def search_frame(f,t,lv,ln,G,M,threshold):
 m,par,p,s,k,q,_=f;z=p+idct(q*SCALES[s],norm='ortho');feedback=quant(z,lv)-z;n=len(q);freq=np.arange(n)/n*FS/2
 # Relative response of legacy output band; slight protection of upper speech band.
 W=1/(1+(freq/3500)**10)**2;W=np.maximum(W,.05);W*=np.sinc(freq/FS)**2
 cand={};seen=set()
 def add(q1,s1):
  key=(s1,q1.tobytes());
  if key in seen:return
  seen.add(key);v=p+idct(q1*SCALES[s1],norm='ortho');err=quant(v,lv)-t
  e=sosfiltfilt(FILT,err) if len(err)>24 else err
  cost=float(e@e);peak=float(np.max(abs(e)));peakpen=float(np.sum(np.maximum(abs(e)-threshold,0)**2));hf=float(np.dot(np.diff(e),np.diff(e)))
  bits=int(rbits(q1,ln,G,M));row=(bits,cost,peakpen,hf,peak,s1,q1)
  # Keep multiple criteria per bit count.
  for tag,val in [(0,cost),(1,cost+3*peakpen),(2,cost+.35*hf+3*peakpen)]:
   key=(bits,s1,tag)
   if key not in cand or val<cand[key][0]:cand[key]=(val,row)
 add(q,s)
 for s1 in range(max(0,s-4),min(128,s+5),2):
  for alpha in (0.,.8):
   c=dct(t-alpha*feedback-p,norm='ortho');sc=SCALES[s1]
   for factor in (.08,.18,.40,.80,1.6,3.2):
    # Test both count classes close to the threshold, otherwise observed class.
    groups=(0,1) if 26<=np.count_nonzero(q)<=48 else (int(np.count_nonzero(q)>=36),)
    for grp in groups:add(choose(c,sc,sc**2*factor,ln,G,M,grp,W),s1)
 return [v[1] for v in cand.values()]

FILT=butter(3,3500,fs=FS,output='sos')
def allocate(frames,cc,ln,h,rate,weight,pkweight):
 # Exact Viterbi across scale transitions: DP over last scale, Lagrangian byte price.
 n,fr,grid,K,L,b=h;pm=0;pp=();st=steps(grid);heads=0
 for m,par,*_ in frames:heads+=sum(w for _,w in fields(m,par,pm,pp,grid,K,fr,st));pm,pp=m,par
 budget=(int(n*rate*1000/(8*FS))-struct.calcsize(HEADER42)-3-(ln.size+1)//2)*8-heads
 # Collapse duplicates to cheapest error per scale/rate.
 candidates=[]
 for c in cc:
  c2={}
  for a in c:
   key=(a[0],a[5]);v=a[1]+pkweight*a[2]+weight*a[3]
   if key not in c2 or v<c2[key][0]:c2[key]=(v,a)
  candidates.append(list(c2.values()))
 def solve(lam):
  last=np.array([0]);cost=np.array([0.]);back=[];sels=[];bits=[]
  for i,c in enumerate(candidates):
   sc=np.array([a[1][5] for a in c]);bs=np.array([a[1][0] for a in c]);es=np.array([a[0] for a in c]);ss=np.unique(sc);trans=np.where(abs(last[:,None]-ss[None,:])<=7,4,11) if i else np.full((1,len(ss)),7);z=cost[:,None]+lam*trans;pr=np.argmin(z,axis=0);base=z[pr,np.arange(len(ss))];inds=[]
   for a in ss:
    ix=np.flatnonzero(sc==a);inds.append(ix[np.argmin(es[ix]+lam*bs[ix])])
   inds=np.array(inds);cost=base+es[inds]+lam*bs[inds];last=ss;back.append(pr);sels.append(inds);bits.append(trans[pr,np.arange(len(ss))]+bs[inds])
  j=int(np.argmin(cost));out=[];used=0
  for i in range(len(candidates)-1,-1,-1):
   out.append(candidates[i][sels[i][j]][1]);used+=int(bits[i][j]);j=back[i][j]
  return out[::-1],used
 lo=0.;hi=max(1.,max(v[0] for c in candidates for v in c));sel=None
 for _ in range(30):
  lam=(lo+hi)/2;a,num=solve(lam)
  if num<=budget:hi=lam;sel=a;used=num
  else:lo=lam
 assert sel is not None
 return sel,used,budget

def run(clip):
 root=Path(__file__).resolve().parent;base=root/'input';dest=root/clip;other='second' if clip=='first' else 'first';h,frames=read_frames(base/clip/'morph.lp42',(base/clip/'book.bin').read_bytes());_,tr=read_frames(base/other/'morph.lp42',(base/other/'book.bin').read_bytes());G=2;M=12;typ=3;ln=np.array(build(pairs(tr),G,M,typ),np.int32);model=base/clip;d=dict(np.load(model/'model.npz'));meta=json.loads((model/'decoder.json').read_text());x=d['target'];_,q=levels(d,meta);lv=np.unique(q);threshold=.07*np.max(abs(x));book=(base/clip/'book.bin').read_bytes();ref=wavfile.read(model/'reference.wav')[1];start=time.time();z0,_,_=decode(base/clip/'morph.lp42',book);v0=render(z0,d,meta);old=wavfile.read(model/'baseline.wav')[1];print('RENDER CHECK',clip, 'max wav difference',np.max(abs(old.astype(int)-v0.astype(int))),flush=True);assert np.max(abs(old.astype(int)-v0.astype(int)))<=2
 cc=[]
 for i,f in enumerate(frames):
  cc.append(search_frame(f,x[i*h[1]:i*h[1]+len(f[2])],lv,ln,G,M,threshold))
  if i%100==99:print('CANDIDATES',clip,i+1,round(time.time()-start,1),flush=True)
 rows=[];row=dict(clip=clip,profile='LP4S baseline',bytes=(base/clip/'morph.lp4s').stat().st_size,kbps=(base/clip/'morph.lp4s').stat().st_size*8*FS/h[0]/1000,**metrics(ref,v0));rows.append(row);print('BASE',row,flush=True)
 for rate,weight,pkweight,tag in [(6.,0.,0.,'6k-SNR'),(6.,.12,4.,'6k-Peak'),(6.5,0.,0.,'65k-SNR'),(6.5,.12,4.,'65k-Peak')]:
  sel,used,budget=allocate(frames,cc,ln,h,rate,weight,pkweight);f2=[(f[0],f[1],f[2],a[5],0,a[6],None) for f,a in zip(frames,sel)];p=dest/(tag+'.lp4s');write_file(h,f2,ln.tolist(),G,M,typ,p);zz,mm,_,rec=decode_s(p,book);expected=np.concatenate([f[2]+idct(f[5]*SCALES[f[3]],norm='ortho') for f in f2]);assert np.array_equal(zz,expected);assert all((a[0],a[1],a[3])==b[:3] and np.array_equal(a[5],b[3]) for a,b in zip(f2,rec));sz=p.stat().st_size;assert sz<=int(h[0]*rate*1000/(8*FS));wav=render(zz,d,meta);wavfile.write(dest/(tag+'.wav'),48000,wav);row=dict(clip=clip,profile=tag,bytes=sz,kbps=sz*8*FS/h[0]/1000,**metrics(ref,wav));rows.append(row);print('RESULT',row,flush=True);(dest/'rd_results.json').write_text(json.dumps(rows,indent=2))
if __name__=='__main__':run(sys.argv[1])

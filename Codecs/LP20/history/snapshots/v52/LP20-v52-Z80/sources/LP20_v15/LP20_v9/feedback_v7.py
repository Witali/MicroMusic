import sys,math,json,os,time
os.environ["OPENBLAS_NUM_THREADS"]="1"
sys.path.insert(0,os.environ.get("LP20_BASE",os.path.join(os.path.dirname(os.path.abspath(__file__)),"base"))+"/tools")
from pathlib import Path
import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import resample_poly
from numba import njit
from precision_study import ROOT,FS,step,reconstruct
import opt_build as b, build_h10 as h, encode as e
@njit(cache=True)
def trellis(t,tb,bk,bm,lens,w,wd,pen,qlut,qid,extra,width):
 n=len(t);order=tb.shape[1];best=np.full((n+1,width),1e30);hist=np.zeros((n+1,width,order),np.int16);ids=np.full((n+1,width),-1,np.int16);prev=np.zeros((n+1,width),np.uint8);best[0,0]=0;hh=np.empty(order,np.int16)
 for p in range(n):
  for q in range(width):
   if best[p,q]>1e29:break
   pe=0. if p==0 else qlut[hist[p,q,0]+512]-t[p-1]
   for k in range(len(lens)):
    ln=lens[k];j=p+ln
    if j>n:continue
    err=best[p,q]+pen
    if err>=best[j,width-1]:continue
    hh[:]=hist[p,q];old=pe
    for z in range(ln):
     y,wr=step(hh,tb[bm[k]],bk[k,z],10);d=qlut[y+512]-t[p+z];low=.65*d+.35*old;err+=w[p+z]*d*d+wd[p+z]*(d-old)**2+extra[p+z,qid[y+512]]+250000.*wr;old=d
     if err>=best[j,width-1]:break
    if err>=best[j,width-1]:continue
    dup=-1
    for v in range(width):
     if best[j,v]>1e29:break
     same=True
     for aa in range(order):
      if hh[aa]!=hist[j,v,aa]:same=False;break
     if same:dup=v;break
    if dup>=0:
     if err>=best[j,dup]:continue
     at=dup
    else:at=width-1
    while at>0 and err<best[j,at-1]:
     best[j,at]=best[j,at-1];hist[j,at]=hist[j,at-1];ids[j,at]=ids[j,at-1];prev[j,at]=prev[j,at-1];at-=1
    best[j,at]=err;hist[j,at]=hh;ids[j,at]=k;prev[j,at]=q
 seq=np.empty(n,np.int16);cnt=0;p=n;q=0
 while p>0:
  k=ids[p,q];assert k>=0;seq[cnt]=k;cnt+=1;q=prev[p,q];p-=lens[k]
 return seq[:cnt][::-1].copy()
# Direct STOI gradient after PWM reconstruction; approximate adjoint of resampling.
import importlib
import nonuniform_h10 as nu
OUT=Path(__file__).resolve().parent
nu.ROOT=OUT

def gradient_stoi(x,y):
 import torch
 torch.set_num_threads(1)
 st=importlib.import_module('pystoi.stoi')
 xx=torch.from_numpy(np.ascontiguousarray(x)); yy=torch.from_numpy(np.ascontiguousarray(y)).requires_grad_()
 win=torch.from_numpy(np.hanning(258)[1:-1]);xf=xx.unfold(0,256,128)[:len(range(0,len(x)-256,128))];yf=yy.unfold(0,256,128)[:len(xf)]
 energy=torch.linalg.vector_norm(xf*win,dim=1);mask=20*torch.log10(energy+1e-15)>20*torch.log10(energy.max()+1e-15)-40
 def ola(f):
  f=f[mask]*win;ind=torch.arange(f.shape[0])[:,None]*128+torch.arange(256)[None,:];return torch.zeros((f.shape[0]-1)*128+256,dtype=f.dtype).index_add(0,ind.ravel(),f.ravel())
 def band(x):
  f=x.unfold(0,256,128)[:len(range(0,len(x)-256,128))];p=torch.fft.rfft(f*win,n=512).abs().square();return (p@torch.from_numpy(st.OBM.T)).clamp_min(1e-24).sqrt().T.unfold(1,30,1)
 X,Y=band(ola(xf)),band(ola(yf));yn=Y*(X.norm(dim=-1,keepdim=True)/(Y.norm(dim=-1,keepdim=True)+1e-15));yn=torch.minimum(yn,X*(1+10**.75));X=X-X.mean(dim=-1,keepdim=True);yn=yn-yn.mean(dim=-1,keepdim=True);score=((X*yn).sum(dim=-1)/((X.norm(dim=-1)+1e-15)*(yn.norm(dim=-1)+1e-15))).mean();score.backward();return score.item(),yy.grad.detach().numpy()

def grad_pwm(t,y,lut):
 from pystoi import utils
 ref=e.lp(resample_poly(t/127,768,125),3500);out=e.lp(nu.render_actual(lut[y+512],256,10)/.875*128/127,3500);L=min(len(ref),len(out));ref=ref[:L];out=out[:L];ref-=ref.mean();out-=out.mean();m=e.align_metric(ref,out);delay=m['delay'];gain=m['gain']
 if delay>=0:a=ref[:L-delay];b=out[delay:]*gain
 else:a=ref[-delay:];b=out[:L+delay]*gain
 a10=utils.resample_oct(resample_poly(a,1,3),5,8);b10=utils.resample_oct(resample_poly(b,1,3),5,8);score,g=gradient_stoi(a10,b10);print('STOI gradient check',score,m,flush=True)
 g16=utils.resample_oct(g,8,5)*5/8;g48=resample_poly(g16,3,1)/3;gg=np.zeros(L);start=max(0,delay);length=min(len(b),len(g48));gg[start:start+length]=g48[:length]*gain;gg-=gg.mean();gg=e.lp(e.lp(gg,3500),7000);gb=resample_poly(gg,625,96)*96/625/.875*128/127
 ng=len(t)*40;gb=np.pad(gb,(0,max(0,ng-len(gb))))[:ng];return gb.reshape(len(t),10,4).sum(axis=1),score

def prepare(src,dst):
 d=np.load(src);t=d['target'];ww=d['ww'];y=d['y'];qid=np.array([min(range(len(ww)),key=lambda i:(abs(ww[i]-(128+v*112/512)),abs(ww[i]-128))) for v in range(-512,512)],dtype=np.int16);lut=ww[qid];g4,score=grad_pwm(t,y,lut);wave=np.clip(ww[:,None]-np.arange(4)*64,0,64)/32.-1.;old=wave[qid[y+512]];g4*=len(t);proj=g4@wave.T;proj-=np.sum(g4*old,axis=1)[:,None];print('gradient stats',np.percentile(np.abs(proj),[0,25,50,75,90,99,100]),flush=True);np.savez(dst,proj=proj.astype(np.float32),qid=qid,score=score,g4=g4)

def run(src,grad,tag,alpha,trust,exponent=.55,high=.9,lam=27.,width=2):
 d=np.load(src);t,a,tb,bk,bm,lens,ww,y=[d[k] for k in ('target','a','tb','bk','bm','lens','ww','y')];g=np.load(grad);qid=g['qid'];lut=ww[qid].astype(np.int32);qlut=(lut-128)*128./112;lev=(ww-128)*128./112;w=(uniform_filter1d(t*t,size=156)+12.)**(-exponent);w/=w.mean();dt=np.diff(t,prepend=0);wd=(uniform_filter1d(dt*dt,size=156)+6.)**(-exponent);wd=wd/wd.mean()*high
 extra=-alpha*g['proj']+trust*w[:,None]*(lev[None,:]-qlut[y+512,None])**2;extra-=extra.min(axis=1)[:,None];extra=extra.astype(np.float32);target=len(t)/FS*5000/8;best=None
 for j in range(4):
  start=time.time();ix=trellis(t,tb,bk,bm,lens,w,wd,lam,qlut,qid,extra,width);print(tag,j,lam,len(ix),time.time()-start,flush=True)
  if best is None or abs(len(ix)-target)<abs(len(best[0])-target):best=(ix.copy(),lam)
  if abs(len(ix)-target)<target*.009:break
  lam*=(len(ix)/target)**2.5
 ix,lam=best;yy,hh,ov=reconstruct(t,tb,bk,bm,lens,ix,10);assert not ov
 m=nu.measure(tag,t,yy,lut,256,10);m.update(bytes=len(ix),kbps=len(ix)*8/(len(t)/FS)/1000,alpha=alpha,trust=trust,exponent=exponent,high=high,penalty=lam,beam=width,overflow=ov,source=str(src));p=OUT/tag;(p/'metrics.json').write_text(json.dumps(m,indent=2));np.savez(p/'training.npz',target=t,a=a,tb=tb,bk=bk,bm=bm,lens=lens,idx=ix,y=yy,bits=10,ww=ww);print('RESULT',tag,m,flush=True)
if __name__=='__main__':
 if sys.argv[1]=='prepare':prepare(*sys.argv[2:])
 else:run(*sys.argv[2:5],*map(float,sys.argv[5:10]),*map(int,sys.argv[10:]))

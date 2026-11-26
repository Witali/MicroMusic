#!/usr/bin/env python3
"""Encoder-only search of existing PWM templates; direct test is uncompressed."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parent
V46=ROOT.parent/'LP20-v46';sys.path.insert(0,str(V46))
from local46 import make_raw,filt_raw,H7,H35,HH
from study46 import data,evaluate,pre,align,filt,render,wavfile,np,njit
from scipy.signal import sosfiltfilt,resample_poly
from scipy.ndimage import uniform_filter1d
R=64

def model(d,meta):
 raw=make_raw(d,meta);grid=np.arange(-512,512)/4
 A=raw(grid).reshape(-1,32);uniq,inds,inv=np.unique(A,axis=0,return_index=True,return_inverse=True)
 order=np.argsort(inds);uniq=uniq[order];inv=np.argsort(order)[inv.ravel()];rep=grid[inds[order]];assert np.array_equal(raw(rep).reshape(-1,32),uniq)
 inp=np.zeros((125,4000),np.float32);c=1500;inp[np.arange(125),c+np.arange(125)]=1
 h=sosfiltfilt(H35,sosfiltfilt(H7,resample_poly(inp,24,125,axis=-1),axis=-1),axis=-1);hh=sosfiltfilt(HH,h,axis=-1);ks=[];kh=[]
 for n in range(125):
  off=n*768//125;mat=[];m2=[]
  for j in range(32):
   pos=n*32+j;rr=pos%125;sh=(pos*24)//125-off;ix=(c+rr)*24//125+np.arange(-R,R+1)-sh;mat.append(h[rr,ix]);m2.append(hh[rr,ix])
  ks.append(uniq@np.asarray(mat));kh.append(uniq@np.asarray(m2))
 K=np.asarray(ks);H=np.asarray(kh);n=179;arr=np.zeros(512*32,np.float32);arr[n*32:(n+1)*32]=uniq[0]-uniq[-1];t=n*768//125
 delta=filt_raw(arr);pred=K[n%125,0]-K[n%125,-1];rel=np.linalg.norm(delta[t-R:t+R+1]-pred)/np.linalg.norm(pred);assert rel<1e-5,rel
 return raw,rep,uniq,K,H,float(rel)

def ids(z,raw,uniq):
 a=raw(z).reshape(-1,32);lookup={v.tobytes():i for i,v in enumerate(uniq)}
 return np.array([lookup[v.tobytes()] for v in a],np.int32)

@njit(cache=True)
def sweep(idx,err,eh,K,H,beta,lag,weight,hfw,threshold,pk,back,pair):
 n=len(idx);m=len(err);changes=0
 for it in range(48,n-48-int(pair)):
  i=n-it-1-int(pair) if back else it;p=i%125;j0=idx[i];a=i*768//125-lag-R
  p2=(i+1)%125;k0=idx[i+1];shift=(i+1)*768//125-i*768//125;length=2*R+1+shift*int(pair)
  if a<0 or a+length>m:continue
  best=0.;bj=j0;bk=k0
  for j in range(max(0,j0-1),min(K.shape[1],j0+2)):
   lo=max(0,k0-1) if pair else k0;hi=min(K.shape[1],k0+2) if pair else k0+1
   for k in range(lo,hi):
    if j==j0 and k==k0:continue
    cost=0.
    for t in range(length):
     dv=0.;dh=0.
     if t<2*R+1:
      dv=K[p,j,t]-K[p,j0,t];dh=H[p,j,t]-H[p,j0,t]
     if pair and t>=shift and t-shift<2*R+1:
      dv+=K[p2,k,t-shift]-K[p2,k0,t-shift];dh+=H[p2,k,t-shift]-H[p2,k0,t-shift]
     dv*=beta;dh*=beta;v=err[a+t];v2=v+dv;cost+=weight[a+t]*dv*(2*v+dv)+hfw[a+t]*dh*(2*eh[a+t]+dh)
     if pk:
      u=max(abs(v)-threshold,0);u2=max(abs(v2)-threshold,0);cost+=pk*(u2*u2-u*u)
    if cost<best:best=cost;bj=j;bk=k
  if bj!=j0 or bk!=k0:
   changes+=int(bj!=j0)+int(bk!=k0)
   for t in range(length):
    dv=0.;dh=0.
    if t<2*R+1:dv=K[p,bj,t]-K[p,j0,t];dh=H[p,bj,t]-H[p,j0,t]
    if pair and t>=shift and t-shift<2*R+1:dv+=K[p2,bk,t-shift]-K[p2,k0,t-shift];dh+=H[p2,bk,t-shift]-H[p2,k0,t-shift]
    err[a+t]+=dv*beta;eh[a+t]+=dh*beta
   idx[i]=bj
   if pair:idx[i+1]=bk
 return changes

def weights(r,adaptive):
 power=uniform_filter1d(r*r,961);hf=sosfiltfilt(HH,r);hp=uniform_filter1d(hf*hf,961)
 w=np.ones(len(r));hw=np.zeros(len(r))
 if adaptive:
  hw=.08+.32*(1-np.minimum(1,hp/(power+1e-7)*5));w=1+.12*np.clip(np.sqrt(np.max(power)/(power+np.max(power)*.002))-1,0,3)
 return w,hw

def opt(z,d,meta,ref,md,mode,passes):
 raw,rep,uniq,K,H,_=md;r=filt(ref.astype(float)/32768);r-=r.mean();idx=ids(z,raw,uniq);w,hw=weights(r,mode!='snr');pk=18. if mode=='peak' else 0.;history=[]
 for p in range(passes):
  v=filt_raw(uniq[idx].ravel());ya,lag,beta=align(r,v);e=ya-r;eh=sosfiltfilt(HH,e);change=sweep(idx,e,eh,K,H,beta,lag,w,hw,.065*np.max(abs(r)),pk,p%2!=0,p>=1);zz=rep[idx];ww=render(zz,d,meta);m=evaluate(ref,ww);history.append(dict(passno=p+1,changes=int(change),**m));print('sweep',mode,p+1,change,round(m['snr_db'],4),round(m['peak_error_pct'],4),flush=True)
 return rep[idx],history

def main(clip):
 _,d,meta,ref,lv,x=data(clip);out=ROOT/clip;out.mkdir(exist_ok=True);md=model(d,meta);rows=[]
 print(clip,'templates',len(md[1]),'kernel error',md[-1],flush=True)
 for mode in ('snr','peak','adaptive'):
  z=np.load(V46/clip/f'direct-{"peak" if mode=="peak" else "snr"}.npy');m0=evaluate(ref,render(z,d,meta));zz,h=opt(z,d,meta,ref,md,mode,3);w=render(zz,d,meta);np.save(out/f'direct-{mode}.npy',zz);wavfile.write(out/f'direct-{mode}.wav',48000,w);rows.append(dict(mode=mode,baseline=m0,passes=h));(out/'direct.json').write_text(json.dumps(rows,indent=2))
if __name__=='__main__':main(sys.argv[1])

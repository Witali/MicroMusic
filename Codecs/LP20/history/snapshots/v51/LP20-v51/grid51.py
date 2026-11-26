#!/usr/bin/env python3
"""Expanded-grid PWM study; 255 shared patterns, encoder-only Viterbi target."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import sys,time,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent; BASE51=ROOT.parent
sys.path.insert(0,str(BASE51/'LP20-v50'))
import study50 as s50
sys.path.insert(0,str(BASE51/'LP20-v49'))
from viterbi49 import trellis
from joint_pwm import R,weights,filt_raw,H35,H7,HH
from study46 import evaluate
from peak_audit import align,filt
from scipy.signal import sosfiltfilt,resample_poly
from scipy.io import wavfile
import numpy as np

def grid():
 p=np.load(BASE51/'LP20-v50/first/255-power1.7.npz')['patterns'];p2=np.load(BASE51/'LP20-v50/second/255-power1.7.npz')['patterns'];assert np.array_equal(p,p2);return p

def make_model(p):
 lut=s50.lut(p);lv=(p.sum(1)-1280)*128/1120
 # Use a reachable quarter-unit input for every pattern (if a pattern is unreachable, refuse).
 # The renderer chooses the nearest achievable duty after rounding internal PCM.
 grid=np.arange(-512,512)/4;rep=np.array([grid[np.flatnonzero(lut==i)[np.argmin(abs(grid[lut==i]-lv[i]))]] for i in range(len(p))]);assert np.array_equal(lut[np.clip(np.rint(rep*4).astype(int)+512,0,1023)],np.arange(len(p)))
 uniq=(np.clip(p[:,:,None]-np.arange(4)*80,0,80).astype(np.float32)*2/80-1).reshape(-1,32)
 def raw(z):return uniq[lut[np.clip(np.rint(z*4).astype(int)+512,0,1023)]].ravel()
 inp=np.zeros((125,4000),np.float32);c=1500;inp[np.arange(125),c+np.arange(125)]=1
 h=sosfiltfilt(H35,sosfiltfilt(H7,resample_poly(inp,24,125,axis=-1),axis=-1),axis=-1);hh=sosfiltfilt(HH,h,axis=-1);ks=[];kh=[]
 for n in range(125):
  off=n*768//125;mat=[];m2=[]
  for j in range(32):
   pos=n*32+j;rr=pos%125;sh=(pos*24)//125-off;ix=(c+rr)*24//125+np.arange(-R,R+1)-sh;mat.append(h[rr,ix]);m2.append(hh[rr,ix])
  ks.append(uniq@np.asarray(mat));kh.append(uniq@np.asarray(m2))
 K=np.asarray(ks);H=np.asarray(kh);n=179;arr=np.zeros(512*32,np.float32);arr[n*32:(n+1)*32]=uniq[0]-uniq[-1];t=n*768//125;delta=filt_raw(arr);pred=K[n%125,0]-K[n%125,-1];rel=np.linalg.norm(delta[t-R:t+R+1]-pred)/np.linalg.norm(pred);assert rel<1e-5,rel
 return raw,rep,uniq,K,H,lut,rel

def render_new(z,d,p):return s50.render_raw(s50.raw(z,p),d)

def opt(z,d,ref,md,mode='peak',configs=((4,96,0,False),(5,96,48,True))):
 raw,rep,uniq,K,H,lut,_=md;r=filt(ref.astype(float)/32768);r-=r.mean();idx=lut[np.clip(np.rint(z*4).astype(int)+512,0,1023)].copy();w,hw=weights(r,mode!='snr');pk=18. if mode=='peak' else 0.;rows=[]
 for M,B,phase,back in configs:
  t=time.time();ya,lag,beta=align(r,filt_raw(uniq[idx].ravel()));e=ya-r;eh=sosfiltfilt(HH,e);ch,ok,tot=trellis(idx,e,eh,K,H,beta,lag,w,hw,.065*np.max(abs(r)),pk,M,B,phase,back);zz=rep[idx];wav=s50.render_raw(raw(zz),d);m=evaluate(ref,wav);row=dict(memory=M,states=3**M,window=B,changes=int(ch),accepted=int(ok),windows=int(tot),seconds=time.time()-t,**m);rows.append(row);print('VITERBI',mode,row,flush=True)
 return rep[idx],rows

def pack_grid(p,out):
 w=np.array(s50.W);ids=np.searchsorted(w,p);assert np.array_equal(w[ids],p);packed=(ids[:,::2]<<4)|ids[:,1::2];b=packed.astype(np.uint8).tobytes();assert len(b)==4*len(p);c=np.frombuffer(b,np.uint8).reshape(-1,4);j=np.empty((len(p),8),np.uint8);j[:,::2]=c>>4;j[:,1::2]=c&15;assert np.array_equal(w[j],p);out.write_bytes(b)

if __name__=='__main__':
 c=sys.argv[1];d,m,r,z=s50.load(c);p=grid();md=make_model(p);out=ROOT/c;out.mkdir(exist_ok=True);baseline=render_new(z,d,p);assert np.array_equal(baseline,wavfile.read(BASE51/'LP20-v50'/c/'255-power1.7.wav')[1]);pack_grid(p,ROOT/'pwm255.bin');np.save(ROOT/'pwm255.npy',p);print(c,'baseline',evaluate(r,baseline),flush=True)
 rows={}
 # Direct test: previous best headroom and precompensated input; starting at new nearest levels.
 old=np.load(BASE51/'LP20-v49'/c/'direct-729.npy');w=render_new(old,d,p);rows['direct_start']=evaluate(r,w);zz,h=opt(old,d,r,md,'snr');rows['direct_passes']=h;np.save(out/'direct.npy',zz);wavfile.write(out/'direct.wav',48000,render_new(zz,d,p))
 zz,h=opt(z,d,r,md,'peak');rows['compressed_target_passes']=h;np.save(out/'compressed-target.npy',zz);wavfile.write(out/'target-unconstrained.wav',48000,render_new(zz,d,p));(out/'direct.json').write_text(json.dumps(rows,indent=2))

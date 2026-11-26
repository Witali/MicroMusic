"""Symmetric nonuniform PWM LUT + closed-loop LP20 10-bit encoder.
Width selection uses weighted scalar quantizer dynamic programming, with
rail endpoints fixed. All chosen widths must admit the actual ROM schedule.
"""
import sys,math,json,os,time
from pathlib import Path
import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import resample_poly
from numba import njit
from precision_study import ROOT,FS,step,reconstruct
import opt_build as b, build_h10 as h, encode as e
@njit(cache=True)
def trellis(t,tb,bk,bm,lens,w,pen,qlut,width):
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
     y,wr=step(hh,tb[bm[k]],bk[k,z],10);d=qlut[y+512]-t[p+z];low=.65*d+.35*old;err+=w[p+z]*(.65*d*d+.35*low*low)+250000.*wr;old=d
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
@njit(cache=True)
def refine_lut(t,tb,bk,bm,lens,idx,start,w,qlut):
 out=bk.copy();loc=np.zeros(len(idx)+1,np.int64);loc[1:]=np.cumsum(lens[idx])
 for k in range(len(lens)):
  hits=np.where(idx==k)[0];ln=lens[k]
  if len(hits)==0:continue
  for j in range(ln):
   old=out[k,j];best=1e30;choice=old
   for d in (0,-4,4,-2,2,-1,1,-8,8):
    v=old+d
    if v < -512 or v>511:continue
    out[k,j]=v;err=0.
    for bb in hits:
     hh=start[bb].copy();p=loc[bb];prev=0. if p==0 else qlut[hh[0]+512]-t[p-1]
     for z in range(ln):
      yy,wr=step(hh,tb[bm[k]],out[k,z],10);q=qlut[yy+512]-t[p+z];low=.65*q+.35*prev;err+=w[p+z]*(.65*q*q+.35*low*low)+250000.*wr;prev=q
    if err<best:best=err;choice=v
   out[k,j]=choice
 return out

def choose_widths(t,y,weights,period,pulses,n):
 mid=period//2;acts=h.fix_actions(h.actions());good=[w for w in range(16,period-15) if b.schedule(acts,period,pulses,w,False) is not None];good=sorted(set(good)&{period-w for w in good});span=mid-min(good);cand=np.array([w-mid for w in good if w>=mid]);print('feasible',min(good),max(good),len(good),'span',span,flush=True)
 # Fine amplitude histogram in physical pulse-width coordinates. Regularization
 # puts 1.5% of mass uniformly over the possible dynamic range.
 x=np.linspace(0,span,2049);pos=np.clip(np.abs(t)*span/128,0,span);q=np.clip(np.abs(y.astype(float))*span/512,0,span)
 hist=np.bincount(np.rint(pos/span*2048).astype(int),weights=weights,minlength=len(x))+np.bincount(np.rint(q/span*2048).astype(int),weights=weights,minlength=len(x));hist=hist/hist.sum()*.985+.015/len(x)
 nc=len(cand);C=np.full((nc,nc),np.inf)
 for i in range(nc-1):
  for j in range(i+1,nc):
   m=(x>=cand[i])&(x<cand[j]);C[i,j]=np.sum(hist[m]*np.minimum((x[m]-cand[i])**2,(x[m]-cand[j])**2))
 k=n//2+1;dp=np.full((k,nc),np.inf);back=np.zeros((k,nc),int);dp[0,0]=0
 for i in range(1,k):
  for j in range(i,nc):
   z=dp[i-1,:j]+C[:j,j];p=z.argmin();dp[i,j]=z[p];back[i,j]=p
 j=nc-1;sel=[j]
 for i in range(k-1,0,-1):j=back[i,j];sel.append(j)
 half=cand[sel[::-1]];ww=np.r_[mid-half[:0:-1],mid+half];assert len(ww)==n
 lut=np.array([min(ww,key=lambda w:(abs(w-(mid+v*span/512)),abs(w-mid))) for v in range(-512,512)],dtype=np.int32);return ww,lut,(lut-mid)*128./span

def render_actual(widths,period,pulses):
 bw=period//4;ww=np.repeat(widths,pulses);z=(np.clip(ww[:,None]-np.arange(4)*bw,0,bw).astype(np.float32)*2/bw-1).ravel();g=math.gcd(48000*bw,20000000);return e.lp(resample_poly(z,48000*bw//g,20000000//g),7000)

def measure(tag,t,y,lut,period,pulses):
 out=ROOT/tag;out.mkdir(exist_ok=True);width=lut[y+512];mid=period//2;span=mid-lut[0];xr=resample_poly(t/127,768,125);ref=e.lp(xr,3500);scale=.98/max(abs(xr));raw=render_actual(width,period,pulses);z=raw/(2*span/period)*128/127;pcm=resample_poly(y.astype(float)/(127*4),768,125);m=e.align_metric(ref,e.lp(z,3500));m['pcm']=e.align_metric(ref,e.lp(pcm,3500));m.update(duty_min=float(width.min()/period),duty_max=float(width.max()/period),raw_peak_dbfs=float(20*np.log10(np.max(np.abs(raw)))),raw_rms_dbfs=float(20*np.log10(np.sqrt(np.mean(raw*raw)))))
 e.wav(out/'pwm.wav',z*scale*min(1,.98/(max(abs(z))*scale)));e.wav(out/'raw_duty.wav',raw);e.wav(out/'pcm.wav',pcm*scale*min(1,.98/(max(abs(pcm))*scale)));(out/'metrics.json').write_text(json.dumps(m,indent=2));print(tag,m,flush=True);return m

def main(n=61,rounds=1):
 d=np.load(ROOT/'h10_compact/training.npz');t,a,tb,bk,bm,lens,y=[d[k] for k in ('target','a','tb','bk','bm','lens','y')];weights=(uniform_filter1d(t*t,size=156)+12.)**(-.12);weights/=weights.mean();period=256;pulses=10;ww,lut,qlut=choose_widths(t,y,weights,period,pulses,n);print('widths',ww,flush=True);lam=20.5;target=len(t)/FS*5000/8
 for it in range(rounds+1):
  best=None
  for j in range(3):
   st=time.time();ix=trellis(t,tb,bk,bm,lens,weights,lam,qlut,2);print(it,j,lam,len(ix),time.time()-st,flush=True)
   if best is None or abs(len(ix)-target)<abs(len(best[0])-target):best=(ix.copy(),lam)
   if abs(len(ix)-target)<target*.012:break
   lam*=(len(ix)/target)**2.5
  ix,lam=best;yy,hh,ov=reconstruct(t,tb,bk,bm,lens,ix,10);assert not ov
  tag=f'nonuniform_{n}_p{it}';m=measure(tag,t,yy,lut,period,pulses);m.update(bytes=len(ix),kbps=len(ix)*8/(len(t)/FS)/1000,levels=len(ww),active=len(set(lut[yy+512])),overflow=ov);out=ROOT/tag;(out/'metrics.json').write_text(json.dumps(m,indent=2));np.savez(out/'training.npz',target=t,a=a,tb=tb,bk=bk,bm=bm,lens=lens,idx=ix,y=yy,bits=10,ww=ww);np.save(out/'widths.npy',ww);print('rate',m,flush=True)
  if it<rounds:bk=refine_lut(t,tb,bk,bm,lens,ix,hh,weights,qlut)
if __name__=='__main__':main(*map(int,sys.argv[1:]))

#!/usr/bin/env python3
"""Four-adjacent-template exact quadratic search (uncompressed diagnostic only).
Local shifts +/- one existing PWM template; exhaustive 3**4 candidates, linear filter halo.
"""
import sys
from pathlib import Path
ROOT48=Path(__file__).resolve().parent;V47=ROOT48.parent/'LP20-v47';sys.path.insert(0,str(V47))
from joint_pwm import *
@njit(cache=True)
def quad(idx,e,K,beta,lag,phase,back):
 n=len(idx);changes=0;L=2*R+1+20
 for ib in range((n-96)//4-1):
  i=48+phase+4*ib if not back else n-52-phase-4*ib
  if i<48 or i+4>=n-48:continue
  a=i*768//125-lag-R
  if a<0 or a+L>len(e):continue
  old=idx[i:i+4].copy();d=np.zeros((12,L));valid=np.ones(12,np.uint8);lin=np.zeros(12);cross=np.zeros((12,12))
  for j in range(4):
   p=(i+j)%125;sh=(i+j)*768//125-i*768//125
   for t in range(3):
    k=old[j]+t-1;u=3*j+t
    if k<0 or k>=K.shape[1]:valid[u]=0;continue
    for m in range(2*R+1):
     dv=(K[p,k,m]-K[p,old[j],m])*beta;d[u,m+sh]=dv;lin[u]+=dv*(2*e[a+m+sh]+dv)
  for j in range(12):
   if not valid[j]:continue
   for k in range((j//3+1)*3,12):
    if not valid[k]:continue
    s=0.
    for m in range(L):s+=d[j,m]*d[k,m]
    cross[j,k]=2*s
  best=0.;aa=1;bb=4;cc=7;dd=10
  for j in range(3):
   if not valid[j]:continue
   for k in range(3,6):
    if not valid[k]:continue
    t0=lin[j]+lin[k]+cross[j,k]
    for l in range(6,9):
     if not valid[l]:continue
     t1=t0+lin[l]+cross[j,l]+cross[k,l]
     for m in range(9,12):
      if not valid[m]:continue
      cost=t1+lin[m]+cross[j,m]+cross[k,m]+cross[l,m]
      if cost<best:best=cost;aa=j;bb=k;cc=l;dd=m
  if best<0:
   for j,k in enumerate((aa,bb,cc,dd)):
    z=old[j]+k%3-1;changes+=int(z!=old[j]);idx[i+j]=z
   for m in range(L):e[a+m]+=d[aa,m]+d[bb,m]+d[cc,m]+d[dd,m]
 return changes

def run(c):
 _,d,meta,ref,lv,x=data(c);out=ROOT48/c;raw,rep,uniq,K,H,rel=model(d,meta);z=np.load(V47/c/'direct-snr.npy');idx=ids(z,raw,uniq);r=filt(ref.astype(float)/32768);r-=r.mean();rows=[dict(passno=0,**evaluate(ref,render(z,d,meta)))];print(c,0,rows[-1]['snr_db'],flush=True)
 for i in range(2):
  ya,lag,beta=align(r,filt_raw(uniq[idx].ravel()));e=ya-r;ch=quad(idx,e,K,beta,lag,i*2,i%2==1);z=rep[idx];wav=render(z,d,meta);rows.append(dict(passno=i+1,changes=ch,**evaluate(ref,wav)));print(c,i+1,ch,rows[-1]['snr_db'],rows[-1]['peak_error_pct'],flush=True)
 np.save(out/'direct-quad.npy',z);(out/'direct-quad.json').write_text(json.dumps(rows,indent=2));wavfile.write(out/'direct-quad.wav',48000,wav)
if __name__=='__main__':run(sys.argv[1])

#!/usr/bin/env python3
"""Finite-memory Viterbi over existing PWM templates (encoder only).
State: last M choices (lower / unchanged / higher), 3**M states.
Exact DP for quadratic costs with pair interactions up to M samples;
accept only if full window cost, including longer interactions, decreases.
"""
import sys,time
from pathlib import Path
ROOT49=Path(__file__).resolve().parent;V48=ROOT49.parent/'LP20-v48';V47=ROOT49.parent/'LP20-v47';sys.path.insert(0,str(V47))
from joint_pwm import *
@njit(cache=True)
def trellis(idx,e,eh,K,H,beta,lag,w,hw,threshold,pk,M,B,phase,back):
 n=len(idx);S=3**M;P=S//3;neutral=(S-1)//2;changes=0;accepted=0;total=0;maxlen=B*7+2*R+1
 digits=np.empty((S,M),np.int8)
 for s in range(S):
  x=s
  for k in range(M):digits[s,k]=x%3;x//=3
 d=np.zeros((B,3,2*R+1));dh=np.zeros_like(d);sh=np.zeros(B,np.int32);valid=np.zeros((B,3),np.uint8)
 unary=np.empty((B,3));pair=np.zeros((B,M,3,3));parents=np.empty((B,S),np.int16);delta=np.empty(maxlen);deltah=np.empty(maxlen);path=np.empty(B,np.int8)
 for bi in range((n-96)//B+1):
  i=48+phase+bi*B if not back else n-48-phase-(bi+1)*B
  if i<48 or i+B>n-48:continue
  a=i*768//125-lag-R;L=(i+B-1)*768//125-i*768//125+2*R+1
  if a<0 or a+L>len(e):continue
  total+=1
  for j in range(B):
   t=i+j;ph=t%125;sh[j]=t*768//125-i*768//125;old=idx[t]
   for c in range(3):
    k=old+c-1;valid[j,c]=int(0<=k<K.shape[1]);unary[j,c]=0.
    if not valid[j,c]:unary[j,c]=1e30;continue
    for m in range(2*R+1):
     v=(K[ph,k,m]-K[ph,old,m])*beta;h=(H[ph,k,m]-H[ph,old,m])*beta;d[j,c,m]=v;dh[j,c,m]=h;t0=a+sh[j]+m;err=e[t0];errh=eh[t0]
     u=max(abs(err)-threshold,0.);v0=max(abs(err+v)-threshold,0.)
     unary[j,c]+=w[t0]*v*(2*err+v)+hw[t0]*h*(2*errh+h)+pk*(v0*v0-u*u)
   for dist in range(1,min(j,M)+1):
    off=sh[j]-sh[j-dist]
    for c in range(3):
     for pc in range(3):
      v=0.
      if c!=1 and pc!=1 and valid[j,c] and valid[j-dist,pc]:
       for m in range(2*R+1-off):
        t0=a+sh[j]+m;v+=2*(w[t0]*d[j,c,m]*d[j-dist,pc,m+off]+hw[t0]*dh[j,c,m]*dh[j-dist,pc,m+off])
      pair[j,dist-1,c,pc]=v
  cost=np.full(S,1e30);cost[neutral]=0.;new=np.empty(S)
  for j in range(B):
   for s in range(S):
    c=s%3
    if not valid[j,c]:new[s]=1e30;parents[j,s]=-1;continue
    p=s//3;v=unary[j,c]
    for k in range(min(j,M-1)):v+=pair[j,k,c,digits[p,k]]
    best=1e30;bst=-1
    for t in range(3):
     old=p+t*P;v0=cost[old]
     if j>=M:v0+=pair[j,M-1,c,t]
     if v0<best:best=v0;bst=old
    new[s]=best+v;parents[j,s]=bst
   cost,new=new,cost
  s=np.argmin(cost)
  for j in range(B-1,-1,-1):path[j]=s%3;s=parents[j,s]
  delta[:L]=0.;deltah[:L]=0.
  for j in range(B):
   c=path[j]
   if c!=1:
    for m in range(2*R+1):delta[sh[j]+m]+=d[j,c,m];deltah[sh[j]+m]+=dh[j,c,m]
  full=0.
  for m in range(L):
   t=a+m;v=delta[m];h=deltah[m];ee=e[t];u=max(abs(ee)-threshold,0.);u1=max(abs(ee+v)-threshold,0.)
   full+=w[t]*v*(2*ee+v)+hw[t]*h*(2*eh[t]+h)+pk*(u1*u1-u*u)
  if full < -1e-15:
   accepted+=1
   for j in range(B):
    c=path[j];idx[i+j]+=c-1;changes+=int(c!=1)
   for m in range(L):e[a+m]+=delta[m];eh[a+m]+=deltah[m]
 return changes,accepted,total

def optimize(z,d,meta,ref,md,mode='snr',configs=((4,96,0,False),(5,96,48,True))):
 raw,rep,uniq,K,H,_=md;r=filt(ref.astype(float)/32768);r-=r.mean();idx=ids(z,raw,uniq);w,hw=weights(r,mode!='snr');pk=18. if mode=='peak' else 0.;rows=[]
 for M,B,phase,back in configs:
  t=time.time();ya,lag,beta=align(r,filt_raw(uniq[idx].ravel()));e=ya-r;eh=sosfiltfilt(HH,e);ch,ok,tot=trellis(idx,e,eh,K,H,beta,lag,w,hw,.065*np.max(abs(r)),pk,M,B,phase,back);zz=rep[idx];wav=render(zz,d,meta);m=evaluate(ref,wav);row=dict(memory=M,states=3**M,window=B,changes=int(ch),accepted=int(ok),windows=int(tot),seconds=time.time()-t,**m);rows.append(row);print('VITERBI',mode,row,flush=True)
 return rep[idx],rows

def run(c):
 _,d,meta,ref,lv,x=data(c);out=ROOT49/c;md=model(d,meta);z=np.load(V48/c/'direct-quad.npy');m0=evaluate(ref,render(z,d,meta));print(c,'v48',m0,flush=True);zz,rows=optimize(z,d,meta,ref,md);np.save(out/'direct-viterbi.npy',zz);wavfile.write(out/'direct-viterbi.wav',48000,render(zz,d,meta));(out/'direct.json').write_text(json.dumps(dict(baseline=m0,passes=rows,kernel_error=md[-1]),indent=2))
if __name__=='__main__':run(sys.argv[1])

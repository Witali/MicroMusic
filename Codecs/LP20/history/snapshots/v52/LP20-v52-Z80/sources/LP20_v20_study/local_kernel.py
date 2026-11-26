import numpy as np
from numba import njit
from study_pitch import step
@njit(cache=True)
def local_search(t,tb,bk,bm,lens,alt,ab,active,th,q,w,wd,wl,pen,extra,qid,width,ctx,ll,initial,initial_ctx):
 n=len(t);best=np.full((n+1,width),1e30);hist=np.zeros((n+1,width,6),np.int16);ids=np.full((n+1,width),-1,np.int16);prev=np.zeros((n+1,width),np.uint8);best[0,0]=0;hist[0,0]=initial;h=np.empty(6,np.int16)
 for p in range(n):
  for j in range(width):
   if best[p,j]>1e29:break
   old=q[hist[p,j,0]+512]-t[p-1] if p else 0.
   c=ctx[ids[p,j]] if p else initial_ctx
   cont=hist[p,j,0]>=th or hist[p,j,0]<-th
   for k in range(len(lens)):
    ln=lens[k];end=p+ln
    if end>n:continue
    err=best[p,j]+pen*ll[c,k]
    if err>=best[end,width-1]:continue
    h[:]=hist[p,j];pe=old;ok=True;use=cont and active[k];bank=ab[k] if use else bm[k];vec=alt[k] if use else bk[k]
    for z in range(ln):
     v,ov=step(h,tb[bank],vec[z],10)
     if ov:ok=False;break
     e=q[v+512]-t[p+z];lo=.65*e+.35*pe;hi=e-pe
     err+=w[p+z]*e*e+wd[p+z]*hi*hi+wl[p+z]*lo*lo+extra[p+z,qid[v+512]];pe=e
     if err>=best[end,width-1]:ok=False;break
    if not ok:continue
    dup=-1
    for k2 in range(width):
     if best[end,k2]>1e29:break
     if ctx[k]!=ctx[ids[end,k2]]:continue
     same=True
     for a in range(6):
      if h[a]!=hist[end,k2,a]:same=False;break
     if same:dup=k2;break
    if dup>=0:
     if err>=best[end,dup]:continue
     at=dup
    else:at=width-1
    while at>0 and err<best[end,at-1]:
     best[end,at]=best[end,at-1];hist[end,at]=hist[end,at-1];ids[end,at]=ids[end,at-1];prev[end,at]=prev[end,at-1];at-=1
    best[end,at]=err;hist[end,at]=h;ids[end,at]=k;prev[end,at]=j
 out=np.empty(n,np.int16);p=n;j=0;cnt=0
 while p>0:
  k=ids[p,j]
  if k<0:raise ValueError('no path')
  out[cnt]=k;cnt+=1;j=prev[p,j];p-=lens[k]
 return out[:cnt][::-1].copy()

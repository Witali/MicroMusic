from repack import *
from collections import defaultdict
@njit(cache=True)
def alternatives(recs,lens,tb,ctx,loc,ix,y,th):
 n=len(ix);alt=np.full(n,-1,np.int16);h=np.zeros(6,np.int16);hh=h.copy()
 for i in range(n):
  p=loc[i];ln=loc[i+1]-p;k=ix[i];c=255*ctx[p]
  for z in range(6):h[z]=y[p-z-1] if p>z else 0
  for j in range(255):
   if j==k or lens[j+c]!=ln:continue
   hh[:]=h;good=True
   for z in range(ln):
    b,r=recs[j+c,z];v,o=step(hh,tb[b],r,10)
    if o or v!=y[p+z]:good=False;break
   if good:alt[i]=j;break
 return alt
for n in ['first','second']:
 d=dict(np.load(HERE/n/'exact'/'model.npz'));raw,loc=actual(d,records(d));y=d['y'];th=int(d['threshold']);ctx=np.r_[0,(y[:-1]>=th)|(y[:-1]<-th)].astype(np.int32);ix=d['idx'];a=alternatives(d['records'],d['lengths'],d['tb'],ctx,loc,ix,y,th);cnt=np.bincount(ix+255*ctx[loc[:-1]],minlength=510);bad=np.bincount((ix+255*ctx[loc[:-1]])[a<0],minlength=510);print(n,'alternative exact',sum(a>=0),'free',[(int(k),int(cnt[k])) for k in np.flatnonzero((cnt>0)&(bad==0))],flush=True);print('low rare',[(int(k),int(cnt[k]),int(bad[k])) for k in np.argsort(cnt[:255])[:15]],flush=True)

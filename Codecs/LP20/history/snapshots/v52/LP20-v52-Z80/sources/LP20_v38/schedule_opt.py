"""Optimize common phase boundaries while retaining the exact PWM patterns."""
from functools import lru_cache
import numpy as np
import opt_build as b
import period_share as ps

def choose(acts,period,pulses,grid,emit):
    original=ps.choose(acts,period,pulses,grid)
    if original is None:return None
    _,ranges=original
    costs=[]
    for o in acts:
        im=b.Image();emit(im,o);costs.append(im.pc)
    cb=np.r_[0,np.cumsum(costs)].tolist();ts=np.r_[0,np.cumsum([x[0] for x in acts])].tolist();N=len(acts)
    @lru_cache(None)
    def padding(t):
        p=b.pad(t,False)
        return (None,0) if p is None else (tuple(('pad',v) for v in p),sum(b.pad_bytes(v) for v in p))
    def work(i,j):return tuple(('act',n) for n in range(i,j))
    @lru_cache(None)
    def phase(i,j,last):
        if i>j or (last and j!=N) or (not last and j>=N):return None
        ec=0 if last else 1
        if ts[j]-ts[i]>period-24-(0 if last else 10):return None
        opts={}
        for w in grid:
            a=[]
            for k in range(i,min(j,N-1)+1):
                p,pc=padding(w-12-(ts[k]-ts[i]));rem=period-w-12-(0 if last else 10)-(ts[j]-ts[k]);q,qc=padding(rem);qr,qrc=padding(rem-10)
                if p is None:continue
                hc=4+cb[k]-cb[i]+pc
                if q is not None:a.append((hc+qc+cb[j]-cb[k]+ec,k,False,p,q))
                if qr is not None:a.append((hc+qrc+3,k,True,p,qr))
            if not a:return None
            opts[w]=a
        best=None
        for first in [None,*range(i,min(j,N-1)+1)]:
            sel={w:min((x for x in opts[w] if not x[2] or (first is not None and x[1]>=first)),key=lambda x:x[0],default=None) for w in grid}
            if any(x is None for x in sel.values()):continue
            used=[x[1] for x in sel.values() if x[2]]
            cost=sum(x[0] for x in sel.values())+(cb[j]-cb[min(used)]+ec if used else 0)
            if best is None or cost<best[0]:best=(cost,sel,used)
        return best
    bd=[ranges[0][0]]+[j for i,j in ranges]
    def score(bd):return sum(phase(i,j,k==pulses-1)[0] for k,(i,j) in enumerate(zip(bd,bd[1:])))
    print('schedule baseline estimated code',score(bd),bd,flush=True)
    # Coordinate descent across all feasible adjacent phase boundaries.
    for sweep in range(8):
        prev=score(bd)
        for k in (range(1,pulses) if sweep%2==0 else range(pulses-1,0,-1)):
            best=(phase(bd[k-1],bd[k],False)[0]+phase(bd[k],bd[k+1],k==pulses-1)[0],bd[k])
            for j in range(bd[k-1],min(bd[k+1],N-1)+1):
                if ts[j]-ts[bd[k-1]]>period-34:break
                if ts[bd[k+1]]-ts[j]>period-34+10*int(k==pulses-1):continue
                a=phase(bd[k-1],j,False);z=phase(j,bd[k+1],k==pulses-1)
                if a is not None and z is not None and a[0]+z[0]<best[0]:best=(a[0]+z[0],j)
            bd[k]=best[1]
        print('schedule sweep',sweep,score(bd),bd,flush=True)
        if score(bd)==prev:break
    plans={};tails={};ranges=tuple(zip(bd,bd[1:]))
    for k,(i,j) in enumerate(ranges):
        last=k==pulses-1;_,sel,used=phase(i,j,last);end=() if last else (('ret',),)
        for w,(_,cut,shared,p,q) in sel.items():
            front=(('edge',0),)+work(i,cut)+p+(('edge',1),)
            plans[k,w]=front+q+((('tail',k,cut),) if shared else work(cut,j)+end)
        if used:tails[k]=(min(used),j,set(used),last)
    return plans,ranges,tails

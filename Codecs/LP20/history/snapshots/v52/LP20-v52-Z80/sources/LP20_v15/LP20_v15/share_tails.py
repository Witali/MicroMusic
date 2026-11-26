"""Share identical low-phase tails by a fixed 10-T JP, paid out of padding.
All code generation is offline; no RAM or changes in PCM arithmetic.
"""
import numpy as np
import period_share as ps
import opt_build as b

def choose(acts,period,pulses,grid,emit):
 result=ps.choose(acts,period,pulses,grid)
 if result is None:return None
 original,ranges=result
 costs=[]
 for o in acts:
  im=b.Image();emit(im,o);costs.append(im.pc)
 cb=np.r_[0,np.cumsum(costs)].tolist();ts=np.r_[0,np.cumsum([x[0] for x in acts])].tolist()
 def work(i,j):return tuple(('act',n) for n in range(i,j))
 def pad(p):return tuple(('pad',v) for v in p)
 def pcost(p):return sum(b.pad_bytes(v) for v in p)
 plans={};tails={};N=len(acts)
 for phase,(i,j) in enumerate(ranges):
  last=phase==pulses-1;end=() if last else (('ret',),);ec=len(end)
  opts={}
  for w in grid:
   a=[]
   for k in range(i,min(j,N-1)+1):
    p=b.pad(w-12-(ts[k]-ts[i]),False)
    rem=period-w-12-(0 if last else 10)-(ts[j]-ts[k])
    q=b.pad(rem,False);qr=b.pad(rem-10,False)
    if p is None:continue
    front=(('edge',0),)+work(i,k)+pad(p)+(('edge',1),)
    hc=4+cb[k]-cb[i]+pcost(p)
    if q is not None:
     a.append((hc+pcost(q)+cb[j]-cb[k]+ec,k,False,front+pad(q)+work(k,j)+end))
    if qr is not None:
     a.append((hc+pcost(qr)+3,k,True,front+pad(qr)+(('tail',phase,k),)))
   assert a;opts[w]=a
  # Enumerate earliest shared entry. Include inline-only case.
  best=None
  for first in [None,*range(i,min(j,N-1)+1)]:
   sel={w:min((x for x in opts[w] if not x[2] or (first is not None and x[1]>=first)),key=lambda x:x[0]) for w in grid}
   used=[x[1] for x in sel.values() if x[2]];earliest=min(used) if used else None
   cost=sum(x[0] for x in sel.values())+(cb[j]-cb[earliest]+ec if used else 0)
   if best is None or cost<best[0]:best=(cost,sel,used)
  _,sel,used=best
  for w,x in sel.items():plans[phase,w]=x[3]
  if used:tails[phase]=(min(used),j,set(used),last)
 return plans,ranges,tails

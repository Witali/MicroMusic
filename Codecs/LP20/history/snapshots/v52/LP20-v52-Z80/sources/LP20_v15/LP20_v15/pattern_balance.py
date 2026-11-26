"""Offline PWM pattern selection with bounded within-sample width spread."""
from itertools import combinations_with_replacement
from functools import lru_cache
import numpy as np
import period_share as ps
@lru_cache(None)
def candidates(period,pulses,grid,span):
 rows=[r for r in combinations_with_replacement(grid,pulses) if r[-1]-r[0]<=span]
 x=np.asarray(rows,dtype=np.int32);s=x.sum(1);var=np.sum((x-s[:,None]/pulses)**2,axis=1)
 return x,s,var

def order_balanced(x):
 r=list(map(int,x));total=sum(r);n=len(r);s=0;p=[]
 for k in range(1,n+1):
  j=min(range(len(r)),key=lambda j:(abs(n*(s+r[j])-k*total),r[j]))
  v=r.pop(j);p.append(v);s+=v
 return tuple(p)

def patterns(w,period,pulses,grid,alpha=.03,span=None):
 grid=tuple(grid)
 if alpha is None:return ps.patterns(w,period,pulses,grid)
 if span is None:span=max(np.diff(grid))
 if w<1280:return tuple(period-v for v in patterns(2560-w,period,pulses,grid,alpha,span))
 if w==1280:return (period//2,)*pulses
 x,s,var=candidates(period,pulses,grid,int(span));cost=(s-w)**2+alpha*var
 return order_balanced(x[cost.argmin()])

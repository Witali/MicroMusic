'''Period-wise shared code for a fixed grid of instantaneous PWM widths.
At every PWM period boundary the LPC action index is identical regardless
of duty. A ROM thread selects the phase/width routine; no runtime writes.
'''
from functools import lru_cache
import numpy as np
import opt_build as b

def patterns(w,period,pulses,grid):
 # w is total high time over 2560 T. Map to two adjacent grid widths.
 mean=w/pulses;j=int(np.searchsorted(grid,mean,side='left'))
 if j==len(grid):return (grid[-1],)*pulses
 if grid[j]==mean or j==0:return (grid[j],)*pulses
 lo,hi=grid[j-1:j+1];n=int(np.floor((w-pulses*lo)/(hi-lo)+.5));return tuple(lo+(hi-lo)*(((i+1)*n+pulses//2)//pulses-(i*n+pulses//2)//pulses) for i in range(pulses))

def choose(acts,period,pulses,grid):
 ts=np.r_[0,np.cumsum([o[0] for o in acts])];N=len(acts);total=int(ts[-1]);ts=ts.tolist()
 # For each period, enforce the same action range for every grid width. The
 # last period ends with JP(HL), others return via ROM-thread SP.
 @lru_cache(None)
 def one(i,j,w,last):
  high=w-12;low=period-w-12-(0 if last else 10)
  if low<0 or high<0:return None
  if ts[j]-ts[i]>high+low:return None
  cand=[]
  for k in range(i,j+1):
   if k>=N or (not last and k>=N-1):break
   a=high-(ts[k]-ts[i]);bb=low-(ts[j]-ts[k]);p=b.pad(a,False);q=b.pad(bb,False)
   if p is None or q is None:continue
   # prefer balanced work and short padding; no branch/RET after prep except JP.
   cost=sum(b.pad_bytes(x) for x in p+q)
   cand.append((cost,k,p,q))
  return min(cand) if cand else None
 @lru_cache(None)
 def rec(k,i):
  if k==pulses:return () if i==N else None
  last=k==pulses-1;cap=period-24-(0 if last else 10)
  if total-ts[i]>(pulses-k)*cap+10:return None
  if last:js=[N]
  else:
   # Prefer near-equal work per period. Need room for the terminal dispatch.
   target=(total-ts[i])/(pulses-k);js=sorted(range(i,N-1),key=lambda j:abs(ts[j]-ts[i]-target))
  for j in js:
   if ts[j]-ts[i]>cap:continue
   if any(one(i,j,w,last) is None for w in grid):continue
   rest=rec(k+1,j)
   if rest is not None:return ((i,j),)+rest
  return None
 ranges=rec(0,0)
 if ranges is None:return None
 d={}
 for phase,(i,j) in enumerate(ranges):
  last=phase==pulses-1
  for w in grid:
   _,k,p,q=one(i,j,w,last);a=[('edge',0)]+[('act',z) for z in range(i,k)]+[('pad',v) for v in p]+[('edge',1)]
   if last:a += [('act',z) for z in range(k,j-1)]+[('pad',v) for v in q]+[('act',j-1)]
   else:a += [('act',z) for z in range(k,j)]+[('pad',v) for v in q]+[('ret',)]
   d[phase,w]=tuple(a)
 return d,ranges

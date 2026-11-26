'''Shared-chunk timing scheduler for read-only RET-threaded Z80 code.'''
from functools import lru_cache
import numpy as np
import opt_build as b

def pat(w,period,pulses):
 assert period*pulses==2560
 if w<1280:return tuple(period-v for v in pat(2560-w,period,pulses))
 a,r=divmod(int(w),pulses);return tuple(a+((j+1)*r+pulses//2)//pulses-(j*r+pulses//2)//pulses for j in range(pulses))

def chunks(acts,limit):
 out=[0];t=0
 for i,o in enumerate(acts[:-2]):
  if t+o[0]>limit and i>out[-1]:out.append(i);t=0
  t+=o[0]
 if out[-1]!=len(acts)-2:out.append(len(acts)-2)
 out.append(len(acts));return out

def common_schedule(acts,widths,period,cut,known):
 ts=np.r_[0,np.cumsum([o[0] for o in acts])].tolist();N=len(cut)-1;M=len(widths)*2;slots=[x-12 for w in widths for x in (w,period-w)];act=lambda i,j:tuple(('act',n) for n in range(cut[i],cut[j]));t=lambda i,j:ts[cut[j]]-ts[cut[i]]
 def pad(x):
  v=b.pad(x,False);return None if v is None else tuple(('pad',p) for p in v)
 def cost(f):
  if f in known:return 2
  return 2+sum(b.pad_bytes(x[1]) if x[0]=='pad' else 2 if x[0]=='edge' else 1 if x[0]=='ret' else asize[x[1]] for x in f)
 @lru_cache(None)
 def f(k,i):
  if k==M:return (0,()) if i==N else (1e20,())
  if ts[-1]-ts[cut[i]]>sum(slots[k:]):return (1e20,())
  rem=slots[k];edge=(('edge',k%2),);best=(1e20,());R=(('ret',),)
  for j in ([N] if k==M-1 else range(i,N)):
   if k!=M-1 and j==N:continue
   if k==M-1 and i==N:continue
   fin=j==N;ln=j-i;costwork=t(i,j);available=rem-costwork
   if available<0:break
   # Standalone edge+pad followed by reusable chunks. Last chunk ends in JP.
   def work(start):return tuple(act(q,q+1)+(R if q+1<N else ()) for q in range(start,j))
   opts=[]
   if ln==0:
    p=pad(available-10)
    if p is not None:opts.append((edge+p+R,))
   else:
    p=pad(available-10-10*(ln-int(fin)))
    if p is not None:opts.append((edge+p+R,)+work(i))
    # Fuse first work chunk with edge. The rest can be fully shared.
    p=pad(available-10*(ln-int(fin)))
    if p is not None:opts.append((edge+p+act(i,i+1)+(R if i+1<N else ()),)+work(i+1))
    # Fuse all work (fallback); preserves exact time and permits variable pad.
    p=pad(available-(0 if fin else 10))
    if p is not None:opts.append((edge+p+act(i,j)+(R if not fin else ()),))
    # Edge+first shared work and a separate universal padding fragment.
    if not fin:
     p=pad(available-10*ln-10)
     if p is not None:opts.append((edge+act(i,i+1)+R,)+work(i+1)+(p+R,))
   if not opts:continue
   v,tail=f(k+1,j)
   if v>=1e19:continue
   for fr in opts:
    c=v+sum(cost(z) for z in fr)
    if c<best[0]:best=(c,fr+tail)
  return best
 # Approximate actual byte size of each op, branch groups penalized.
 asize=[len(x[2]) if x[2] else max(3,x[0]//5) for x in acts]
 score,out=f(0,0)
 return out if score<1e19 else None

def choose(acts,width_list,period,pulses):
 # Try several common partition lengths. Optimize total new fragments across
 # all levels (not individual amplitude code lengths).
 best=None
 for lim in (80,92,104,116,128,140,152,164,176,192,208,224,240):
  cut=chunks(acts,lim);known=set();plans={};miss=[]
  for w in sorted(width_list,key=lambda w:abs(w-1280)):
   f=common_schedule(acts,pat(w,period,pulses),period,cut,known)
   if f is None:miss.append(w);continue
   plans[w]=f;known.update(f)
  def approx(z):return sum(b.pad_bytes(x[1]) if x[0]=='pad' else 2 if x[0]=='edge' else 1 if x[0]=='ret' else len(acts[x[1]][2]) or max(3,acts[x[1]][0]//5) for x in z)
  sz=sum(approx(z) for z in known)+2*sum(len(x) for x in plans.values());score=sz+len(miss)*10000
  print('shared',period,lim,'chunks',len(cut)-1,'missing',len(miss),'estimated bytes',sz,flush=True)
  if best is None or score<best[0]:best=(score,plans,miss,lim)
 return best[1:]

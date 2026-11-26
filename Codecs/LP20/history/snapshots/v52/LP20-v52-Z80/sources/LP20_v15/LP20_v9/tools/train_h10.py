import sys,json,numpy as np
from precision_study import *
from build_h10 import compact_tables
p=ROOT/'lpc6_8banks_10bit_p1'/'training.npz';d=np.load(p);t,a,bk,bm,lens,idx=[d[k] for k in ('target','a','bk','bm','lens','idx')];tb=compact_tables(a);w=(uniform_filter1d(t*t,size=156)+12.)**(-.12);w/=w.mean();lam=20.46
for j in range(3):
 ix=search(t,tb,bk,bm,lens,w,lam,10,48,1,2);print(j,len(ix),flush=True)
 if abs(len(ix)-18720)<180:break
 lam*=(len(ix)/18720)**2.5
save('h10_compact',t,a,tb,bk,bm,lens,ix,10,lam)

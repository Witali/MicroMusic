"""Verify Viterbi against exhaustive enumeration when memory covers whole window."""
from viterbi49 import *
from itertools import product
rng=np.random.default_rng(49)
for trial in range(12):
 B=5;n=96+B;M=B-1;K=rng.normal(size=(125,3,2*R+1))*.03;H=rng.normal(size=K.shape)*.03
 idx=rng.integers(0,3,n,dtype=np.int32);old=idx.copy();e=rng.normal(size=640)*.03;eh=rng.normal(size=640)*.03;w=rng.uniform(.8,1.3,len(e));hw=rng.uniform(0.,.2,len(e));eo=e.copy();eho=eh.copy();beta=0.8;lag=0;i=48
 def cost(p):
  x=eo.copy();y=eho.copy()
  for j,c in enumerate(p):
   t=i+j;ph=t%125;a=t*768//125-R;x[a:a+2*R+1]+=beta*(K[ph,c]-K[ph,old[t]]);y[a:a+2*R+1]+=beta*(H[ph,c]-H[ph,old[t]])
  return np.dot(w,x*x)+np.dot(hw,y*y)
 valid=[range(max(0,k-1),min(3,k+2)) for k in old[i:i+B]];best=min(cost(p) for p in product(*valid));ch,ok,tot=trellis(idx,e,eh,K,H,beta,lag,w,hw,0.,0.,M,B,0,False);assert tot==1;got=cost(idx[i:i+B]);assert abs(got-best)<1e-10,(trial,got,best);assert abs(np.dot(w,e*e)+np.dot(hw,eh*eh)-got)<1e-10
print('PASS: 12 exhaustive small-window tests, including boundary template indices')

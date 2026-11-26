from repack import *
from collections import defaultdict
for name in ['first','second']:
 d=model(HERE.parent/'LP20_v21_rollout'/name/'training.npz');recs=records(d);raw,loc=actual(d,recs);syms=sorted(set(raw)-{(4,0),(4,1)});tb=d['tb'];sets=[defaultdict(list),defaultdict(list)];cases=[[],[]];y=np.r_[np.zeros(6,np.int16),d['y']]
 for i,k in enumerate(d['idx']):
  p=loc[i];c=int(y[p+5]>=d['threshold'] or y[p+5]<-d['threshold']);r=recs[c*255+k]
  if not any(b==4 for b,x in r):continue
  ca=[]
  for s in range(2):
   h=y[p+s:p+s+6][::-1];t=y[p+s+6];valid=[]
   for b,res in syms:
    z=(sum(int(tb[b,j,h[j]+512]) for j in range(6))+64*res+32)>>6
    if z==t:valid.append((b,res))
   ca.append(valid)
  i0=len(cases[c]);cand={ (p1,p2) for p1 in ca[0] for p2 in ca[1]};cases[c].append(cand)
  for r in cand:sets[c][r].append(i0)
 print(name)
 for c in range(2):
  cc=cases[c];ss=sets[c];exist=set(recs[c*255:(c+1)*255]);covered={i for i,a in enumerate(cc) if a&exist};rem=set(range(len(cc)))-covered;print(c,'cases',len(cc),'exact any',sum(bool(a) for a in cc),'existing exact',len(covered));chosen=[]
  while rem:
   if not ss:break
   r,a=max(ss.items(),key=lambda z:len(rem&set(z[1])));n=len(rem&set(a));
   if not n:break
   chosen.append((r,n));rem-=set(a)
  print('needed',len(chosen),'uncovered',len(rem),'top',chosen[:10])

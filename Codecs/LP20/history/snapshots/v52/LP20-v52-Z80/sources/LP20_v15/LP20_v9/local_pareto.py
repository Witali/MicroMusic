"""Rate-preserving token substitution, with full forward history verification.
No decoder changes. Final measured PWM STOI AND SNR must improve.
"""
import study as s
import numpy as np, sys, json, time
from numba import njit
from precision_study import step,reconstruct,FS
from pathlib import Path
@njit(cache=True)
def sweep(t,tb,bk,bm,lens,idx,y,qlut,qid,proj,max_tail,mode):
 n=len(t);m=len(idx);order=tb.shape[1];y=y.copy();idx=idx.copy();res=np.empty(n,np.int16);banks=np.empty(n,np.int16);p=0
 for k in idx:
  for j in range(lens[k]):res[p+j]=bk[k,j];banks[p+j]=bm[k]
  p+=lens[k]
 hist=np.empty(order,np.int16);buf=np.empty(max_tail+128,np.int16);bestbuf=np.empty(max_tail+128,np.int16);p=0;changes=0;rejected=0
 for z in range(m):
  k=idx[z];ln=lens[k];limit=min(n,p+ln+max_tail);bestscore=0.;choice=k;bl=0
  for cand in range(len(lens)):
   if cand==k or lens[cand]!=ln:continue
   for i in range(order):hist[i]=y[p-i-1] if p-i-1>=0 else 0
   dg=0.;de=0.;match=0;ok=True;oldprev=qlut[y[p-1]+512]-t[p-1] if p>0 else 0.;newprev=oldprev
   for j in range(p,limit):
    a=j-p;r=bk[cand,a] if a<ln else res[j];b=bm[cand] if a<ln else banks[j];v,ov=step(hist,tb[b],r,10)
    if ov:ok=False;break
    buf[a]=v;old=qlut[y[j]+512]-t[j];new=qlut[v+512]-t[j];oldsm=.75*old+.25*oldprev;newsm=.75*new+.25*newprev
    de+=.65*(new*new-old*old)+.35*(newsm*newsm-oldsm*oldsm);oldprev=old;newprev=new
    dg+=proj[j,qid[v+512]]-proj[j,qid[y[j]+512]]
    if v==y[j]:match+=1
    else:match=0
    if j>=p+ln-1 and (match>=order or j==n-1):break
   if not ok or (match<order and j!=n-1):continue
   # de is an approximate physical squared-error change, dg is gradient of
   # actual after-PWM STOI. Retain only predicted nondominated substitutions.
   if de>=-1e-4 or dg<=1e-4:continue
   score=dg-.12*de if mode==0 else dg-.5*de
   if score>bestscore:
    bestscore=score;choice=cand;bl=j-p+1;bestbuf[:bl]=buf[:bl]
  if choice!=k:
   idx[z]=choice;y[p:p+bl]=bestbuf[:bl];res[p:p+ln]=bk[choice,:ln];banks[p:p+ln]=bm[choice];changes+=1
  p+=ln
 return idx,y,changes

def run(src,tag,rounds=2):
 d=dict(np.load(src));t=d['target'];y=d['y'];idx=d['idx'];qid,lut,qlut=s.lut_for(d['ww']);m=s.measure(t,y,d['ww']);m.update(bytes=len(idx),kbps=len(idx)*8/(len(t)/FS)/1000);print('START',tag,m,flush=True)
 for i in range(rounds):
  proj=s.get_proj(d,y);st=time.time();ii,yy,n=sweep(t,d['tb'],d['bk'],d['bm'],d['lens'],idx,y,qlut,qid,proj,64,i%2);check,_,ov=reconstruct(t,d['tb'],d['bk'],d['bm'],d['lens'],ii,10);assert not ov and np.array_equal(check,yy);q=s.measure(t,yy,d['ww']);q.update(bytes=len(ii),kbps=len(ii)*8/(len(t)/FS)/1000,changes=int(n),round=i+1,tag=tag,overflow=0);print('CANDIDATE',q,'seconds',time.time()-st,flush=True)
  accepted=q['snr']>=m['snr'] and q['stoi']>m['stoi'];print('ACCEPTED',accepted,flush=True)
  if not accepted:break
  idx,y,m=ii,yy,q;s.save(tag,d,idx,y,m)
 print('FINAL',tag,json.dumps(m),flush=True)
if __name__=='__main__':run(sys.argv[1],sys.argv[2],int(sys.argv[3]) if len(sys.argv)>3 else 2)

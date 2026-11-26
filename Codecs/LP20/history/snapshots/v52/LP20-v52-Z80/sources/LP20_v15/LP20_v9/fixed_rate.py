"""Same-rate Pareto refinement of VBR token paths. All edits use a fixed
number of tokens and unchanged lengths. Verify the entire integer recurrence,
then accept only exact after-PWM STOI and SNR improvement. No decoder changes."""
import study as s
from local_pareto import sweep
import numpy as np, time,json,sys
from precision_study import reconstruct,FS
from pathlib import Path

# Local substitutions are first proposed with a gradient, then verified in
# smaller batches. The earlier v8 algorithm rejected the entire batch if one
# metric fell. Partitioning finds useful subsets without increasing bit rate.
def run(src,tag,rounds=2):
 d=dict(np.load(src));t=d['target'];idx=d['idx'];y=d['y'];ww=d['ww'];ln=d['lens'];qid,lut,qlut=s.lut_for(ww)
 start=s.measure(t,y,ww);m=start.copy();log=[];print('BASE',start,'bytes',len(idx),flush=True)
 loc=np.r_[0,np.cumsum(ln[idx])];
 for it in range(rounds):
  proj=s.get_proj(d,y);ii,yy,n=sweep(t,d['tb'],d['bk'],d['bm'],ln,idx,y,qlut,qid,proj,96,it%2);assert len(ii)==len(idx) and np.array_equal(ln[ii],ln[idx]);check,_,ov=reconstruct(t,d['tb'],d['bk'],d['bm'],ln,ii,10);assert not ov and np.array_equal(check,yy)
  p=np.flatnonzero(ii!=idx);print('PROPOSED',it,len(p),flush=True)
  if not len(p):break
  # Choose sparse windows and evaluate disjoint clusters, sorted by a
  # first-order metric gain. Avoid selecting on a local-only metric.
  block=round(FS*1.5);nseg=(len(y)+block-1)//block;proposals=[]
  for i in range(nseg):
   a,b=np.searchsorted(loc,[i*block,min(len(y),(i+1)*block)])
   q=p[(p>=a)&(p<b)]
   if not len(q):continue
   l,r=loc[a],min(len(y),loc[b]+96);ix0=qid[y[l:r]+512];ix1=qid[yy[l:r]+512];g=float(np.sum(proj[np.arange(l,r),ix1]-proj[np.arange(l,r),ix0]));e0=qlut[y[l:r]+512]-t[l:r];e1=qlut[yy[l:r]+512]-t[l:r];de=float(np.sum(e0*e0-e1*e1));proposals.append((g+.05*de,q))
  proposals.sort(key=lambda x:x[0],reverse=True);okcount=0
  for rank,(_,q) in enumerate(proposals):
   ix=idx.copy();ix[q]=ii[q];z,_,ov=reconstruct(t,d['tb'],d['bk'],d['bm'],ln,ix,10)
   if ov:continue
   mm=s.measure(t,z,ww);accept=mm['snr']>=m['snr'] and mm['stoi']>m['stoi'];log.append(dict(round=it,rank=rank,changes=len(q),accepted=bool(accept),**mm));print('TRIAL',rank,len(q),mm,'accepted',accept,flush=True)
   if accept:
    idx,y,m=ix,z,mm;okcount+=1
    s.save(tag,d,idx,y,dict(**m,bytes=len(idx),kbps=len(idx)*8/(len(t)/FS)/1000,overflow=0))
  print('ROUND',it,okcount,m,flush=True)
  if not okcount:break
 # Always emit exact baseline if none accepted.
 m.update(bytes=len(idx),kbps=len(idx)*8/(len(t)/FS)/1000,overflow=0);s.save(tag,d,idx,y,m);(s.ROOT/'logs'/(tag+'.json')).write_text(json.dumps(dict(baseline=start,final=m,log=log),indent=2));print('FINAL',m,flush=True)
if __name__=='__main__':run(sys.argv[1],sys.argv[2],int(sys.argv[3]) if len(sys.argv)>3 else 2)

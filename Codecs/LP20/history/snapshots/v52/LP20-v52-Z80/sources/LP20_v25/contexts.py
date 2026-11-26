#!/usr/bin/env python3
"""Test alternative causal amplitude contexts, including global record reuse."""
from study import *

def opt(seq,ctx,pool,nsyms,nc,shortmax=239):
 # Each context gets the same candidate pool; optimize assignment to 239 native short codes.
 n=len(pool);nodes=[{} for _ in range(nc)];ends=[-1]*nc;ln=np.tile(np.array(list(map(len,pool)),np.int32),nc);bk=pool*nc;cx=np.repeat(np.arange(nc),n)
 for c in range(nc):
  for k,r in enumerate(pool):
   node=c
   for a in r:
    if a not in nodes[node]:nodes[node][a]=len(nodes);nodes.append({});ends.append(-1)
    node=nodes[node][a]
   ends[node]=c*n+k
 tr=np.full((len(nodes),nsyms),-1,np.int32);en=np.array(ends,np.int32)
 for i,node in enumerate(nodes):
  for a,j in node.items():tr[i,a]=j
 cost=np.ones(len(bk),np.int32);best=None
 for it in range(12):
  ix,ll=weighted_parse(seq,ctx,tr,en,ln,cost,int(ln.max()));assert len(ix) and ll[-1]==len(seq)
  counts=np.bincount(ix,minlength=len(bk));used=np.flatnonzero(counts)
  if it or n<=shortmax:
   stream=int(cost[ix].sum());bs=size([bk[k] for k in used]);score=stream+bs
   if best is None or score<best[0]:best=(score,stream,bs,ix.copy(),ll.copy(),cost.copy())
  new=np.full(len(bk),2,np.int32)
  for c in range(nc):
   kk=sorted(range(c*n,(c+1)*n),key=lambda k:(-counts[k],-len(bk[k]),k));new[kk[:shortmax]]=1
  if np.array_equal(new,cost):break
  cost=new
 score,stream,bs,ix,ll,cost=best
 assert np.array_equal(np.concatenate([np.asarray(bk[k],np.int16) for k in ix]),seq)
 return dict(score=score,stream=stream,book=bs,ix=ix,ll=ll,cost=cost,bk=bk,cx=cx)

def main(clip,profile):
 src=V23/clip/profile;d=dict(np.load(src/'model.npz'));r=records(d);raw,loc=actual(d,r);syms=sorted({p for rr in r for p in rr});mp={p:i for i,p in enumerate(syms)};seq=np.array([mp[p] for p in raw],np.int16);y=d['y'];prev=np.r_[0,y[:-1]].astype(np.int32);pool=list(dict.fromkeys(tuple(mp[p] for p in rr) for rr in r));basepath=V24/'extended239'/clip/profile/'96'
 if (basepath/'model.npz').exists():
  old=dict(np.load(basepath/'model.npz'));rr=[tuple(mp[tuple(p)] for p in rec[:n]) for rec,n in zip(np.concatenate([old['records'],old['ext_records']]),np.r_[old['lengths'],old['ext_lengths']])];pool=list(dict.fromkeys(pool+rr))
 out=R/clip/profile;out.mkdir(parents=True,exist_ok=True);res=[];sols=[]
 def trial(name,ctx,nc,th=None):
  ctx=ctx.astype(np.uint8);sol=opt(seq,ctx,pool,len(syms),nc);rec=dict(name=name,nctx=nc,stream=sol['stream'],estimated_book=sol['book'],extra_pointer_bytes=max(0,nc-2)*512,estimated_total=sol['score']+max(0,nc-2)*512,threshold=th);res.append(rec);sols.append((sol,ctx));print(clip,profile,rec,flush=True)
 for th in (4,8,12,16,20,24,28,32,48,64,80,96,112,128,160,192,256):trial('amp'+str(th),(prev>=th)|(prev< -th),2,th)
 trial('sign',prev<0,2)
 for th in (64,96,128,192):
  trial('3amp'+str(th),np.where(prev< -th,1,np.where(prev>=th,2,0)),3)
  trial('4amp'+str(th),((prev>=th)|(prev< -th)).astype(np.uint8)*2+(prev<0),4)
 for i in sorted((i for i,x in enumerate(res) if x['threshold'] is not None),key=lambda i:res[i]['estimated_total'])[:3]:
  sol,ctx=sols[i];th=res[i]['threshold'];res[i]['ext_records']=model_out(dict(d,threshold=np.array(th,dtype=d['threshold'].dtype)),sol,syms,ctx,out/res[i]['name']/'model.npz')
 (out/'contexts.json').write_text(json.dumps(res,indent=2))
if __name__=='__main__':main(*sys.argv[1:])

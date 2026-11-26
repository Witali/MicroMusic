#!/usr/bin/env python3
"""Exact composite candidate selection and unrestricted substring mining. Expanded native v24 records."""
import os,sys,json,itertools
from pathlib import Path
os.environ.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',LP20_ALIAS8='1',LP20_SHORT='239')
R=Path(__file__).resolve().parent;V24=R.parent/'LP20_v24';V23=R.parent/'LP20_v23';B=R.parent/'base';os.environ['LP20_V15']=str(B/'LP20_v15');sys.path[:0]=[str(V24),str(B/'LP20_v22')]
from extended import weighted_parse
from repack import *
from collections import Counter

def factor(phrases,contexts,shape):
 out=[];parts=[]
 for c in (0,1):
  k=len(shape);cnt=Counter(tuple(phrases[i:i+k]) for i in range(len(phrases)-k+1) if contexts[i]==c and sum(map(len,phrases[i:i+k]))<=128)
  sets=[]
  for j,n in enumerate(shape):
   m=Counter()
   for r,v in cnt.items():m[r[j]]+=v
   sets.append(set(x for x,_ in m.most_common(n)))
  for it in range(6):
   old=[s.copy() for s in sets]
   for j,n in enumerate(shape):
    m=Counter()
    for r,v in cnt.items():
     if all(r[i] in sets[i] for i in range(k) if i!=j):m[r[j]]+=v
    for x in sorted(old[j]):m.setdefault(x,0)
    sets[j]=set(x for x,_ in m.most_common(n))
   if old==sets:break
  ordered=[sorted(s) for s in sets];parts.append(ordered)
  out.append([sum(t,()) for i,t in enumerate(itertools.product(*ordered)) if i<255 and cnt[t]])
 return out,parts

def optimize(seq,ctx,base,adds,nsyms,pure=False):
 bk=[];cx=[];cs=[];nodes=[{},{}];ends=[-1,-1]
 for c in (0,1):
  m={r:2 for r in base[c]};m.update({r:1 for r in adds[c]})
  for r,v in m.items():
   i=len(bk);bk.append(r);cx.append(c);cs.append(v);node=c
   for a in r:
    if a not in nodes[node]:nodes[node][a]=len(nodes);nodes.append({});ends.append(-1)
    node=nodes[node][a]
   ends[node]=i
 cx=np.array(cx);tr=np.full((len(nodes),nsyms),-1,np.int32);en=np.array(ends,np.int32);ln=np.array(list(map(len,bk)),np.int32)
 for i,node in enumerate(nodes):
  for a,j in node.items():tr[i,a]=j
 cost=np.array(cs,np.int32) if pure else np.ones(len(bk),np.int32);best=None
 for it in range(1 if pure else 8):
  ix,ll=weighted_parse(seq,ctx,tr,en,ln,cost,int(ln.max()));assert len(ix) and ll[-1]==len(seq)
  counts=np.bincount(ix,minlength=len(bk));used=np.flatnonzero(counts)
  if it or pure or max(np.sum(cx==0),np.sum(cx==1))<=239:
   stream=int(cost[ix].sum());bs=size([bk[k] for k in used]);score=stream+bs
   if best is None or score<best[0]:best=(score,stream,bs,ix.copy(),ll.copy(),cost.copy())
  if pure:break
  new=np.full(len(bk),2,np.int32)
  for c in (0,1):
   kk=sorted(np.flatnonzero(cx==c),key=lambda k:(-counts[k],-len(bk[k]),k));new[kk[:239]]=1
  if np.array_equal(new,cost):break
  cost=new
 score,stream,bs,ix,ll,cost=best
 assert np.array_equal(np.concatenate([np.asarray(bk[k],np.int16) for k in ix]),seq)
 return dict(score=score,stream=stream,book=bs,ix=ix,ll=ll,cost=cost,bk=bk,cx=cx)

def model_out(d,sol,syms,ctx,path,shortmax=239):
 bk,cx,ix,cost,ll=[sol[k] for k in ('bk','cx','ix','cost','ll')];used=set(ix.tolist());common=min((bk[k] for k in used),key=len);short=[common]*510;ext=[];mapping={}
 for c in (0,1):
  ks=[k for k in sorted(used) if cx[k]==c and cost[k]==1];assert len(ks)<=shortmax
  for i,k in enumerate(ks):short[c*255+i]=bk[k];mapping[k]=c*255+i
 for k in sorted(used):
  if cost[k]==2:
   if bk[k] not in ext:ext.append(bk[k])
   mapping[k]=510+ext.index(bk[k])
 plan=np.array([mapping[k] for k in ix],np.int32);assert np.array_equal(cx[ix],ctx[ll[:-1]])
 rr=[tuple(syms[p] for p in r) for r in short+ext];lens=np.array(list(map(len,rr)),np.int32);mat=np.zeros((len(rr),max(lens),2),np.int16)
 for i,r in enumerate(rr):mat[i,:len(r)]=r
 path.parent.mkdir(exist_ok=True,parents=True);np.savez(path,**dict(d,records=mat[:510],lengths=lens[:510],ext_records=mat[510:],ext_lengths=lens[510:],plan=plan,shortmax=np.int16(shortmax)))
 return len(ext)

def main(clip,profile):
 src=V23/clip/profile;d=dict(np.load(src/'model.npz'));r=records(d);raw,loc=actual(d,r);syms=sorted({p for rr in r for p in rr});mp={p:i for i,p in enumerate(syms)};seq=np.array([mp[p] for p in raw],np.int16);y=d['y'];ctx=np.r_[False,(y[:-1]>=d['threshold'])|(y[:-1]<-d['threshold'])].astype(np.uint8)
 original=[tuple(mp[p] for p in rr) for rr in r];base=[list(dict.fromkeys(original[:255])),list(dict.fromkeys(original[255:]))];shortbase=[x.copy() for x in base];basepath=V24/'extended239'/clip/profile/'96';phrases=[tuple(seq[p:e].tolist()) for p,e in zip(loc[:-1],loc[1:])]
 if (basepath/'model.npz').exists():
  old=dict(np.load(basepath/'model.npz'));rr=[tuple(mp[tuple(p)] for p in rec[:n]) for rec,n in zip(np.concatenate([old['records'],old['ext_records']]),np.r_[old['lengths'],old['ext_lengths']])];phrases=[rr[k] for k in old['plan']];loc=np.r_[0,np.cumsum(list(map(len,phrases)))];assert np.array_equal(np.concatenate([np.array(p,np.int16) for p in phrases]),seq)
  for c in (0,1):base[c]=list(dict.fromkeys(base[c]+rr[c*255:(c+1)*255]+rr[510:]))
 pc=ctx[loc[:-1]];out=R/clip/profile;out.mkdir(parents=True,exist_ok=True);results=[];sols=[]
 def test(name,adds,extras=None):
  sol=optimize(seq,ctx,base,adds,len(syms));rec=dict(name=name,stream=sol['stream'],estimated_book=sol['book'],stream_plus_book=sol['score'],candidates=sum(map(len,adds)),**(extras or {}));print(clip,profile,rec,flush=True);results.append(rec);sols.append(sol)
 test('base_reparse',[[],[]]);alladds=[set(),set()]
 for name,shape in [('4+4',(16,16)),('3+5',(8,32)),('5+3',(32,8)),('2+3+3',(4,8,8))]:
  adds,parts=factor(phrases,pc,shape);pure=optimize(seq,ctx,shortbase,adds,len(syms),True);table=6+sum(1+len(r) for p in parts for s in p for r in s);test(name,adds,dict(pure_product_bytes=pure['stream'],component_table_bytes=table,pure_total=pure['stream']+table))
  for c in (0,1):alladds[c].update(adds[c])
 counts=[Counter(),Counter()];s=seq.tolist()
 for p in range(len(s)-1):
  c=ctx[p]
  for n in (2,3,4,5,6,8,10,12,16):
   if p+n<=len(s):counts[c][tuple(s[p:p+n])]+=1
 for limit in (96,192,320):
  adds=[]
  for c in (0,1):
   seen=set(base[c]);cand=[(v*(min(len(r),8)-1)/(len(r)+1)**.5,r) for r,v in counts[c].items() if v>=3 and r not in seen];cand.sort(reverse=True);adds.append([r for _,r in cand[:limit]])
  test('ngram'+str(limit),adds)
  if limit==192:test('hybrid192',[sorted(alladds[c]|set(adds[c])) for c in (0,1)])
 rank=sorted(range(len(results)),key=lambda i:results[i]['stream_plus_book'])[:3]
 for i in rank:results[i]['ext_records']=model_out(d,sols[i],syms,ctx,out/results[i]['name']/'model.npz')
 (out/'results.json').write_text(json.dumps(results,indent=2));print('DONE',clip,profile,[results[i] for i in rank],flush=True)
if __name__=='__main__':main(*sys.argv[1:])

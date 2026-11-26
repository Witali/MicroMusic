#!/usr/bin/env python3
"""Exact context-dependent macrocode dictionary. Every record stores bank/residual pairs."""
import os,sys,json,subprocess
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'LP20_v20_study'))
from harmonic import model,decode,f,inspect,FS,np
from study_pitch import step,qtables
from numba import njit
from collections import Counter

@njit(cache=True)
def raw_decode(tb,recs,lens,idx,th):
 h=np.zeros(6,np.int16);out=np.empty(len(idx)*int(lens.max()),np.int16);p=0;ov=0
 for k in idx:
  k=k+255*int(h[0]>=th or h[0]<-th)
  for b,r in recs[k,:lens[k]]:
   v,o=step(h,tb[b],r,10);out[p]=v;p+=1;ov+=o
 return out[:p],ov

def decode_records(d):return raw_decode(f.compact_tables(d['a']),d['records'],d['lengths'],d['idx'],int(d['threshold']))

def records(d):
 if 'records' in d:return [tuple(map(tuple,rec[:n].tolist())) for rec,n in zip(d['records'],d['lengths'])]
 a=[]
 for c in range(2):
  for k,n in enumerate(d['lens']):
   u=c and d['active'][k];b=d['ab'][k] if u else d['bm'][k];v=d['alt'][k] if u else d['bk'][k];a.append(tuple((int(b),int(r)) for r in v[:n]))
 return a

def actual(d,recs):
 p=0;arr=[];y=d['y'];th=int(d['threshold']);idx=d['idx'];loc=[0]
 for k in idx:
  c=int(p>0 and (y[p-1]>=th or y[p-1]<-th));r=recs[k+c*255];arr.extend(r);p+=len(r);loc.append(p)
 assert p==len(y)
 return arr,np.array(loc)

@njit(cache=True)
def parse(seq,ctx,trie,ends,maxlen):
 n=len(seq);cost=np.full(n+1,100000000,np.int32);choice=np.full(n,-1,np.int16);length=np.zeros(n,np.int16);cost[n]=0
 for p in range(n-1,-1,-1):
  node=int(ctx[p]);end=min(n,p+maxlen)
  for j in range(p,end):
   node=trie[node,seq[j]]
   if node<0:break
   k=ends[node]
   if k>=0 and cost[j+1]+1<=cost[p]:
    cost[p]=cost[j+1]+1;choice[p]=k;length[p]=j-p+1
 if choice[0]<0:return np.empty(0,np.int16),np.empty(0,np.int32)
 idx=np.empty(cost[0],np.int16);loc=np.empty(cost[0]+1,np.int32);p=0
 for i in range(cost[0]):
  loc[i]=p;idx[i]=choice[p];p+=length[p]
 loc[-1]=p
 return idx,loc

def triebuild(book,nsyms):
 nodes=[{},{}];ends=[-1,-1];maxlen=max(map(len,book))
 for k,r in enumerate(book):
  if not r:continue
  i=k//255
  for a in r:
   if a not in nodes[i]:nodes[i][a]=len(nodes);nodes.append({});ends.append(-1)
   i=nodes[i][a]
  if ends[i]<0:ends[i]=k%255
 trie=np.full((len(nodes),nsyms),-1,np.int32)
 for i,n in enumerate(nodes):
  for a,j in n.items():trie[i,a]=j
 return trie,np.array(ends,np.int16),maxlen

def size(b):
 keep=set(b);suffix=set()
 for r in keep:
  for j in range(1,len(r)):suffix.add(r[j:])
 return sum(len(r)+1 for r in keep-suffix if r)

def optimize(d,limit=48):
 orig=records(d);raw,loc=actual(d,orig);syms=sorted(set(raw)|{p for r in orig for p in r});mp={p:i for i,p in enumerate(syms)};seq=np.array([mp[p] for p in raw],np.int16);book=[tuple(mp[p] for p in r) for r in orig];ctx=np.r_[False,(d['y'][:-1]>=d['threshold'])|(d['y'][:-1]<-d['threshold'])].astype(np.uint8);nsyms=len(syms)
 def opt(b):return parse(seq,ctx,*triebuild(b,nsyms))
 ix,loc=opt(book);assert len(ix) and loc[-1]==len(seq);start=len(d['idx']);log=[dict(stage='exact_reparse',tokens=len(ix))];print('REPARSE',start,len(ix),flush=True)
 for it in range(limit):
  count=np.bincount(ix+255*ctx[loc[:-1]].astype(np.int32),minlength=510);candidates=[]
  for c in range(2):
   cnt=Counter()
   for i,p in enumerate(loc[:-1]):
    if ctx[p]!=c:continue
    for n in (2,3,4):
     if i+n>=len(loc):break
     e=loc[i+n];ln=e-p
     if ln>256:continue
     cnt[tuple(seq[p:e].tolist())]+=1
   existing=set(book[c*255:(c+1)*255]);best=[]
   for r,h in cnt.most_common(250):
    if h<2 or r in existing:continue
    cost=0 if any(len(z)>=len(r) and z[-len(r):]==r for z in book if z) else len(r)+1
    best.append((h-cost*.8,h,r))
   best.sort(reverse=True);victims=np.argsort(count[c*255:(c+1)*255])[:8]+c*255
   for gain,h,r in best[:8]:
    for v in victims[:5]:
     if gain-count[v]<=0:continue
     candidates.append((gain-int(count[v]),c,int(v),r,h))
  candidates.sort(reverse=True);accepted=False;oldsize=size(book)
  for _,c,v,r,h in candidates[:25]:
   new=book.copy();new[v]=r;ii,ll=opt(new)
   if not len(ii):continue
   ds=size(new)-oldsize;saving=len(ix)-len(ii)
   if saving<=0 or saving<=ds:continue
   log.append(dict(stage='macro',iteration=it,context=c,slot=v%255,length=len(r),hits=h,removed_use=int(count[v]),stream_saved=saving,estimated_book_delta=ds,tokens=len(ii)));book=new;ix=ii;loc=ll;accepted=True;print('MACRO',log[-1],flush=True);break
  if not accepted:break
 cnt=np.bincount(ix+255*ctx[loc[:-1]].astype(np.int32),minlength=510);common=min((r for r in book if r),key=len);book=[r if cnt[i] else common for i,r in enumerate(book)]
 rr=[tuple(syms[p] for p in r) for r in book];lengths=np.array(list(map(len,rr)),np.int32);mat=np.zeros((510,max(lengths),2),np.int16)
 for i,r in enumerate(rr):mat[i,:len(r)]=r
 z=dict(d,records=mat,lengths=lengths,idx=ix);yy,ov=decode_records(z);assert not ov and np.array_equal(yy,d['y']);print('FINAL',start,len(ix),'maxlen',lengths.max(),'unused',sum(cnt==0),flush=True)
 return z,log

def buildcheck(d,out,m):
 import build_v22
 out.mkdir(parents=True,exist_ok=True);src=out/'model.npz';np.savez(src,**d);p=out/'decoder';mm=build_v22.build(src,p,period=320,grid=m['grid'],alpha=.001)
 cpu=HERE.parent/'LP20_v17_gain'/'test_fast'
 if not cpu.exists():subprocess.run(['g++','-O3','-std=c++17',str(cpu.with_suffix('.cpp')),'-o',str(cpu)],check=True)
 test=json.loads(subprocess.check_output([str(cpu),str(p.with_suffix('.bin')),str(p.with_suffix('.map')),str(p.with_suffix('.expected')),'320','8','0','16',str(p.with_suffix('.threads'))],text=True));test.update(core_bytes=mm['used']-mm['stream_bytes'],occupied_rom=mm['used'],stream_bytes=mm['stream_bytes']);(out/'test.json').write_text(json.dumps(test,indent=2));print('ROM',test,flush=True);return test

def main():
 import argparse
 p=argparse.ArgumentParser();p.add_argument('clip');p.add_argument('--source');p.add_argument('--tag',default='exact');p.add_argument('--limit',type=int,default=48);a=p.parse_args();src=Path(a.source) if a.source else HERE.parent/'LP20_v21_rollout'/a.clip/'training.npz';d=model(src);m=json.loads((HERE.parent/'LP20_v21_rollout'/a.clip/'decoder.json').read_text());assert np.array_equal(decode(d,d['idx'])[0],d['y']);z,log=optimize(d,a.limit);out=HERE/a.clip/a.tag;out.mkdir(parents=True,exist_ok=True);(out/'macro.json').write_text(json.dumps(log,indent=2));buildcheck(z,out,m)
if __name__=='__main__':main()

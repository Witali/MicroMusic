#!/usr/bin/env python3
"""Viterbi beam search: allow different PCM only if every PWM width index is identical.
Preserve original trajectory as a dedicated state at original token boundaries.
"""
from study import *
import layout_builder as builder
from fractional import lut10
import subprocess,time

@njit(cache=True)
def search(tb,rr,ll,words,costs,th,reference,lut,refplan,beam):
 n=len(reference);targets=lut[reference+512];orig=np.zeros((n+1,6),np.int16)
 for p in range(1,n+1):
  orig[p,0]=reference[p-1];orig[p,1:]=orig[p-1,:5]
 anchors=np.zeros(n+1,np.uint8);anchors[0]=1;p=0
 for k in refplan:p+=ll[k];anchors[p]=1
 inf=100000000;hist=np.zeros((n+1,beam+1,6),np.int16);score=np.full((n+1,beam+1),inf,np.int32);rank=np.full((n+1,beam+1),inf,np.int32);prev=np.full((n+1,beam+1),-1,np.int8);token=np.full((n+1,beam+1),-1,np.int32);score[0,beam]=0;rank[0,beam]=0
 hh=np.empty(6,np.int16)
 for p in range(n):
  for s in range(beam+1):
   base=score[p,s]
   if base>=inf:continue
   c=int(hist[p,s,0]>=th or hist[p,s,0]<-th)
   for a in range(words.shape[1]):
    k=words[c,a]
    if k<0:break
    ln=ll[k];e=p+ln
    if e>n:continue
    newcost=base+costs[k];hh[:]=hist[p,s];good=True
    for j in range(ln):
     b,r=rr[k,j];v,ov=step(hh,tb[b],r,10)
     if ov or lut[v+512]!=targets[p+j]:good=False;break
    if not good:continue
    dist=0
    for j in range(6):dist+=abs(int(hh[j])-int(orig[e,j]))
    newrank=newcost*4096+dist # exact cost dominates the tie-breaker
    if anchors[e] and dist==0:
     t=beam
     if newcost>=score[e,t]:continue
    else:
     t=-1;worst=0;duplicate=False
     for j in range(beam):
      same=True
      for a1 in range(6):
       if hh[a1]!=hist[e,j,a1]:same=False;break
      if same and score[e,j]<inf:
       duplicate=True
       if newrank<rank[e,j]:t=j
       break
      if rank[e,j]>rank[e,worst]:worst=j
     if duplicate and t<0:continue
     if not duplicate:
      t=worst
      if newrank>=rank[e,t]:continue
    hist[e,t]=hh;score[e,t]=newcost;rank[e,t]=newrank;prev[e,t]=s;token[e,t]=k
 # Conservative: return only a path that reaches the exact original end state.
 assert score[n,beam]<inf
 klist=np.empty(n,np.int32);p=n;s=beam;i=0
 while p>0:
  k=token[p,s];assert k>=0;klist[i]=k;i+=1;s=prev[p,s];p-=ll[k]
 return klist[:i][::-1].copy(),score[n,beam]

@njit(cache=True)
def decode_plan(tb,rr,ll,plan,th):
 n=0
 for k in plan:n+=ll[k]
 y=np.empty(n,np.int16);hist=np.zeros(6,np.int16);p=0;ov=0
 for k in plan:
  if k<510:assert k//255==int(hist[0]>=th or hist[0]<-th)
  for j in range(ll[k]):
   b,r=rr[k,j];v,o=step(hist,tb[b],r,10);y[p]=v;p+=1;ov+=o
 return y,ov

def main(clip,profile,beam=2):
 root=R/clip/profile/'range';a=[]
 for p in root.glob('*/*/test.json'):
  d=json.loads(p.read_text());a.append((d['occupied_rom'],p.parent))
 if not a:raise RuntimeError('No tested input')
 _,src=min(a);model=dict(np.load(src/'model.npz'));orig=model['y'].copy();rr=np.concatenate([model['records'],model['ext_records']]);ll=np.r_[model['lengths'],model['ext_lengths']];th=int(model['threshold']);short=int(model['shortmax']);tb=f.compact_tables(model['a']);lut=lut10(model['ww10']);costs=np.where(np.arange(len(ll))<510,1,2).astype(np.int32);words=[]
 for c in (0,1):
  ids=list(range(255*c,255*c+short))+list(range(510,len(ll)));seen=set();keep=[]
  for k in ids:
   a=rr[k,:ll[k]].tobytes()
   if a not in seen:keep.append(k);seen.add(a)
  words.append(keep)
 ww=np.full((2,max(map(len,words))),-1,np.int32)
 for i,w in enumerate(words):ww[i,:len(w)]=w
 baseline=int(costs[model['plan']].sum());start=time.time();plan,cost=search(tb,rr,ll,ww,costs,th,orig,lut,model['plan'],beam);y,ov=decode_plan(tb,rr,ll,plan,th);assert not ov and len(y)==len(orig) and np.array_equal(lut[y+512],lut[orig+512]);assert cost==costs[plan].sum() and cost<=baseline;print('SEARCH',clip,baseline,cost,'PCM changes',np.count_nonzero(y!=orig),'seconds',time.time()-start,flush=True)
 out=R/clip/profile/f'pwm_beam{beam}';out.mkdir(exist_ok=True);met=dict(baseline_stream=baseline,stream_bytes=int(cost),pcm_changed=int(np.count_nonzero(y!=orig)),max_pcm_delta=int(np.max(abs(y.astype(np.int32)-orig))),pwm_widths_exact=True,beam=beam);(out/'search.json').write_text(json.dumps(met,indent=2));# Remove records no longer referenced; preserve indices for short slots.
 used=set(map(int,plan));common=min(used,key=lambda k:ll[k]);unused=[k for k in range(510) if k not in used];rshort=model['records'].copy();lshort=model['lengths'].copy()
 for k in unused:
  rshort[k]=rr[common];lshort[k]=ll[common]
 extids=sorted(k for k in used if k>=510);remap={k:510+i for i,k in enumerate(extids)};newplan=np.array([remap.get(int(k),int(k)) for k in plan],np.int32)
 model.update(y=y,plan=newplan,records=rshort,lengths=lshort,ext_records=rr[np.array(extids,np.int32)],ext_lengths=ll[np.array(extids,np.int32)]);np.savez(out/'model.npz',**model)
 p=out/'decoder';md=json.loads((src/'decoder.json').read_text());mm=builder.build(out/'model.npz',p,period=320,grid=md['grid'],alpha=.001);test=json.loads(subprocess.check_output([str(V24/'test_extended'),str(p.with_suffix('.bin')),str(p.with_suffix('.map')),str(p.with_suffix('.expected')),'320','8','0','16',str(p.with_suffix('.threads'))],text=True));assert np.array_equal(np.load(p.with_suffix('.widths10.npy')),np.load(src/'decoder.widths10.npy'));assert mm['patterns']==md['patterns'];base=json.loads((src/'test.json').read_text());test.update(met,core_bytes=mm['used']-mm['stream_bytes'],occupied_rom=mm['used'],stream_bytes=mm['stream_bytes'],kbps=mm['stream_bytes']*8*7812.5/len(y)/1000,snr=base['snr'],stoi=base['stoi'],baseline_rom=base['occupied_rom']);(out/'test.json').write_text(json.dumps(test,indent=2));print('PASS',test,flush=True)
if __name__=='__main__':main(sys.argv[1],sys.argv[2],int(sys.argv[3]) if len(sys.argv)>3 else 2)

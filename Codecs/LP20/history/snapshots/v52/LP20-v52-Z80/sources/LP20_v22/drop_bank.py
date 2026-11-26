#!/usr/bin/env python3
"""Remove sparse LPC bank using history-aware local replacement and exact rollout."""
from repack import *
from noise_study import Mask
from scipy.ndimage import uniform_filter1d

@njit(cache=True,inline='always')
def block(h,k,tb,bk,bm,lens,alt,ab,active,th,out,p):
 use=active[k] and (h[0]>=th or h[0]<-th);b=ab[k] if use else bm[k];vec=alt[k] if use else bk[k];ov=0
 for j in range(lens[k]):
  v,o=step(h,tb[b],vec[j],10);out[p+j]=v;ov+=o
 return ov

@njit(cache=True)
def repair(d_ix,tb,bk,bm,lens,alt,ab,active,th,drop,q,t,old,trust,tail):
 ix=d_ix.copy();loc=np.zeros(len(ix)+1,np.int32)
 for i in range(len(ix)):loc[i+1]=loc[i]+lens[ix[i]]
 h=np.zeros(6,np.int16);hh=h.copy();out=np.zeros(len(old),np.int16);scratch=np.zeros(len(old),np.int16);changed=0
 for i,k in enumerate(ix):
  p=loc[i];ln=lens[k];bad=(ab[k] if active[k] and (h[0]>=th or h[0]<-th) else bm[k])==drop
  hh[:]=h;ov=block(hh,k,tb,bk,bm,lens,alt,ab,active,th,out,p)
  if bad or ov:
   best=1e30;bestk=-1
   for j in range(len(lens)):
    if lens[j]!=ln or bm[j]==drop or (active[j] and ab[j]==drop):continue
    hh[:]=h;ov2=block(hh,j,tb,bk,bm,lens,alt,ab,active,th,scratch,p)
    if ov2:continue
    end=loc[i+1];z=i+1
    while z<len(ix) and end<p+ln+tail:
     # stop at next affected token; it will be replaced independently
     kk=ix[z]
     if bm[kk]==drop or (active[kk] and ab[kk]==drop):break
     ov2+=block(hh,kk,tb,bk,bm,lens,alt,ab,active,th,scratch,end);end=loc[z+1];z+=1
    if ov2:continue
    s=0.
    for a in range(p,end):
     v=q[scratch[a]+512];dx=v-q[old[a]+512];e=v-t[a];s+=trust*dx*dx+e*e
    if s<best:best=s;bestk=j
   if bestk<0:return ix,out,-1
   ix[i]=bestk;changed+=1;hh[:]=h;assert block(hh,bestk,tb,bk,bm,lens,alt,ab,active,th,out,p)==0
  h[:]=hh
 return ix,out,changed

def run(name):
 out=HERE/name/'seven';out.mkdir(exist_ok=True,parents=True);d=model(HERE.parent/'LP20_v21_rollout'/name/'training.npz');m=json.loads((HERE.parent/'LP20_v21_rollout'/name/'decoder.json').read_text());lev,qi,q=qtables(d,m);base,pt,r,z,u,v=inspect(d,d['y'],m);mask=Mask(u);base.update(mask.analyze(v));best=None;log=[];drop=4;print('BASE',base,flush=True)
 for trust in (0.,.5,2.,8.,32.,128.):
  ix,y,n=repair(d['idx'],d['tb'],d['bk'],d['bm'],d['lens'],d['alt'],d['ab'],d['active'],int(d['threshold']),drop,q,d['target'],d['y'],trust,64)
  if n<0:continue
  met,_,rr,zz,uu,vv=inspect(d,y,m,pt);met.update(mask.analyze(vv));met.update(trust=trust,changed=n,pcm_changed=int(np.count_nonzero(y!=d['y'])));log.append(met);print('TRIAL',met,flush=True)
  # Minimize damage to actual measured quality; retain only candidates within explicitly recorded limits.
  score=met['snr']-base['snr']+25*(met['stoi']-base['stoi'])
  if best is None or score>best[0]:best=(score,ix.copy(),y.copy(),met)
 assert best is not None
 _,ix,y,met=best;dd=dict(d,idx=ix,y=y);recs=records(dd);raw,loc=actual(dd,recs);assert all(b!=drop for b,r in raw)
 # Reuse the bank-4 slot: duplicate the existing longest quiet sequence (or twice that sequence)
 # in each context; exact reparse and macro search may use it when it matches.
 for c in range(2):
  victim=c*255+240
  assert all(b==drop for b,r in recs[victim]);r=max((r for i,r in enumerate(recs[c*255:(c+1)*255]) if all(b!=drop for b,x in r)),key=len)
  recs[victim]=r+r
 # Remap all seven remaining LPC banks to contiguous indexes.
 rr=[tuple((b-int(b>drop),r) for b,r in rec) for rec in recs];assert all(b!=drop for rec in recs for b,r in rec)
 lens=np.array(list(map(len,rr)),np.int32);mat=np.zeros((510,max(lens),2),np.int16)
 for i,r in enumerate(rr):mat[i,:len(r)]=r
 dd=dict(dd,a=np.delete(dd['a'],drop,axis=0),records=mat,lengths=lens);dd['tb']=f.compact_tables(dd['a']);yy,ov=decode_records(dd);assert not ov and np.array_equal(yy,dd['y'])
 z,mac=optimize(dd,48);(out/'metrics.json').write_text(json.dumps(dict(base=base,selected=met,trials=log,macros=mac),indent=2));buildcheck(z,out,m);mm,_,rr,zz,*_=inspect(dd,yy,m);f.audio(out/'v22.wav',rr,zz);print('SELECTED',met,flush=True)

if __name__=='__main__':run(sys.argv[1])

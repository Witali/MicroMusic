#!/usr/bin/env python3
"""STOI-gated harmonic selection and joint entropy/DDS experiment."""
from harmonic import *
from study_pitch import grads

def run(name,use_entropy=False):
 out=HERE/name;d=model(out/'entropy_training.npz' if use_entropy else ROOT/name/'training.npz');m=json.loads((V18/'release/compact/decoder.json').read_text());base,pt,r,z,u,v=inspect(d,d['y'],m);budget=len(np.load(ROOT/name/'training.npz')['idx']);ix=d['idx'];mode=min([0,1,2],key=lambda md:len(pack(d,ix,256,[],md)));empty=pack(d,ix,256,[],mode);allow=(budget-len(empty))//EV.size;gr,gt,_=grads(d,d['y'],m);lev,qi,q=qtables(d,m);log=[];best=None
 print('BASE',name,use_entropy,base,'budget',budget,'max events',allow,flush=True)
 for block in [128,256]:
  cand=candidates(d,m,block,base,pt,u,v);ranking=[]
  for val,ev in cand:
   p=ev[0]*block;N=min(block,len(d['y'])-p);y=d['y'][p:p+N];yy=np.clip(y.astype(np.int32)+shape(N,*ev[1:]),-512,511);dq=q[yy+512]-q[y+512];gs=float(gt[p:p+N]@dq);gn=float(-gr[p:p+N]@dq);ranking.append((val,gs,gn,ev))
  for tag,order in [('positive_stoi',sorted([k for k in ranking if k[1]>0],key=lambda k:-k[0])),('joint',sorted(ranking,key=lambda k:-(k[0]+.8*k[1]))),('strong_stoi',sorted([k for k in ranking if k[1]>0],key=lambda k:-(k[0]+2*k[1])))]:
   for n in sorted(set([max(1,allow//2),allow])):
    events=[k[3] for k in order[:n]];b=pack(d,ix,block,events,mode);_,_,yy=unpack(d,b);mm,_,rr,zz,*_=inspect(d,yy,m,pt);rec=dict(tag=tag,block=block,events=len(events),bytes=len(b),kbps=len(b)*8*FS/len(yy)/1000,**mm);log.append(rec);print('TRY',rec,flush=True)
    if len(b)<=budget and mm['snr']>=base['snr'] and mm['stoi']>=base['stoi'] and (best is None or mm['snr']>=best[0]['snr'] and mm['stoi']>=best[0]['stoi']):
     best=rec,b;f.audio(out/'joint.wav',rr,zz);(out/'joint.ph20').write_bytes(b);np.save(out/'joint_state.npy',yy)
 (out/'joint.json').write_text(json.dumps(dict(baseline=base,source='entropy' if use_entropy else 'v19',budget=budget,selected=best[0] if best else None,trials=log),indent=2));print('FINAL',best[0] if best else None,flush=True)
if __name__=='__main__':run(sys.argv[1],len(sys.argv)>2 and sys.argv[2]=='entropy')

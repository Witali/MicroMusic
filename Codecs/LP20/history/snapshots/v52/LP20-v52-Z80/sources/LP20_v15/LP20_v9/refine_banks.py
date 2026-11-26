"""Clip-adaptive book refinement with exact after-PWM Pareto acceptance.
A recurrent adjoint proposes integer updates; evaluate separate bank groups,
not the entire update as one candidate. Stream rate unchanged."""
import study as s
import numpy as np, sys,json,time
from scipy.sparse.linalg import LinearOperator,cg
from refine_joint import forward,backward,physical_grad
from precision_study import reconstruct,FS

def run(src,tag):
 d=dict(np.load(src));t=d['target'];idx=d['idx'];y=d['y'];bk=d['bk'];ln=d['lens'];bm=d['bm'];tb=d['tb'];ww=d['ww'];m0=s.measure(t,y,ww);print('BASE',m0,flush=True);best=m0;bestbk=bk.copy();besty=y.copy();log=[]
 pp=[];bb=[]
 for k in idx:pp.extend(k*bk.shape[1]+np.arange(ln[k]));bb.extend([bm[k]]*ln[k])
 active,mi=np.unique(pp,return_inverse=True);aa=d['a'][np.array(bb)];K=len(active);cnt=np.bincount(mi);diag=.10*cnt+1.;mat=LinearOperator((K,K),matvec=lambda v:backward(forward(v,aa,mi),aa,mi,K)+diag*v);M=LinearOperator((K,K),matvec=lambda v:v/(cnt*.2+1));gs,gt=physical_grad(d,y)
 for alpha in (.12,.5,1.0):
  rhs=backward(gs+alpha*gt,aa,mi,K);v,info=cg(mat,rhs,rtol=.015,maxiter=45,M=M);delta=np.zeros(bk.size);delta[active]=v;delta=delta.reshape(bk.shape);print('PROPOSALS',alpha,info,np.percentile(v,[0,5,50,95,100]),flush=True)
  for bank in range(len(d['a'])):
   # Change only one LPC bank's excitation templates; no new parameters.
   mask=bm==bank
   for scale in (1.,.5):
    b=bestbk.copy();b[mask]=np.clip(np.rint(bk[mask]+delta[mask]*scale),-512,511).astype(np.int16);changed=int(np.sum(b!=bestbk));
    if not changed:continue
    yy,_,ov=reconstruct(t,tb,b,bm,ln,idx,10)
    if ov:continue
    m=s.measure(t,yy,ww);ok=m['snr']>=best['snr'] and m['stoi']>best['stoi'];log.append(dict(alpha=alpha,bank=bank,scale=scale,changed=changed,accepted=bool(ok),**m));print('TRIAL',alpha,bank,scale,changed,m,'ACCEPT',ok,flush=True)
    if ok:
     best,bestbk,besty=m,b,yy;dd=dict(d,bk=b);s.save(tag,dd,idx,yy,dict(**m,bytes=len(idx),kbps=len(idx)*8/(len(t)/FS)/1000,overflow=0));break
  if alpha==.5 and best['stoi']-m0['stoi']>.002:break
 dd=dict(d,bk=bestbk);best.update(bytes=len(idx),kbps=len(idx)*8/(len(t)/FS)/1000,overflow=0);s.save(tag,dd,idx,besty,best);(s.ROOT/'logs'/(tag+'.json')).write_text(json.dumps(dict(baseline=m0,final=best,trials=log),indent=2));print('FINAL',best,flush=True)
if __name__=='__main__':run(*sys.argv[1:])

"""Offline fixed-stream codebook update with recurrent linearized predictor adjoint.
Exact metrics/decoder guard every accepted integer update. Clip-adaptive mode.
"""
import study as s
import numpy as np, sys,time,json
from scipy.signal import resample_poly
from scipy.sparse.linalg import LinearOperator,cg
from scipy.ndimage import uniform_filter1d
from numba import njit
from precision_study import reconstruct,FS
@njit(cache=True)
def forward(v,aa,mi):
 n=len(mi);y=np.zeros(n);o=aa.shape[1]
 for i in range(n):
  z=v[mi[i]]*.25
  for j in range(min(i,o)):z+=aa[i,j]*y[i-j-1]
  y[i]=z
 return y
@njit(cache=True)
def backward(v,aa,mi,K):
 n=len(mi);g=v.copy();r=np.zeros(K);o=aa.shape[1]
 for i in range(n-1,-1,-1):
  x=g[i];r[mi[i]]+=x*.25
  for j in range(min(i,o)):g[i-j-1]+=aa[i,j]*x
 return r

def physical_grad(d,y):
 t=d['target'];qid,lut,_=s.lut_for(d['ww']);ww=d['ww'];lev=(ww-128)*128./112.;wave=np.clip(ww[:,None]-np.arange(4)*64,0,64)/32.-1.
 g4,score=s.fb.grad_pwm(t,y,lut);ref=s.e.lp(resample_poly(t/127,768,125),3500);out=s.e.lp(s.nu.render_actual(lut[y+512],256,10)/.875*128/127,3500);L=min(len(ref),len(out));ref=ref[:L];out=out[:L];ref-=ref.mean();out-=out.mean();m=s.e.align_metric(ref,out);delay=m['delay'];gain=m['gain'];gg=np.zeros(L)
 if delay>=0:gg[delay:]=(ref[:L-delay]-out[delay:]*gain)*gain*127**2*FS/48000
 else:gg[:L+delay]=(ref[-delay:]-out[:L+delay]*gain)*gain*127**2*FS/48000
 gg-=gg.mean();gg=s.e.lp(s.e.lp(gg,3500),7000);gb=resample_poly(gg,625,96)*96/625/.875*128/127;ng=len(t)*40;gb=np.pad(gb,(0,max(0,ng-len(gb))))[:ng];sn=gb.reshape(len(t),10,4).sum(axis=1)
 ids=qid[y+512];l=np.maximum(0,ids-1);r=np.minimum(len(ww)-1,ids+1);slope=(wave[r]-wave[l])/(lev[r]-lev[l])[:,None];a=(sn*slope).sum(1);g=(g4*slope).sum(1)*len(t)
 print('grad rms',np.sqrt(np.mean(a*a)),np.sqrt(np.mean(g*g)),flush=True);return a,g

def run(src,tag):
 d=dict(np.load(src));t=d['target'];idx=d['idx'];y=d['y'];bk=d['bk'];ln=d['lens'];bm=d['bm'];tb=d['tb'];ww=d['ww'];m0=s.measure(t,y,ww);print('START',m0,flush=True)
 # Make one parameter for every active vector element, regardless of frequency.
 pp=[];bb=[]
 for k in idx:pp.extend(k*bk.shape[1]+np.arange(ln[k]));bb.extend([bm[k]]*ln[k])
 active,mi=np.unique(pp,return_inverse=True);aa=d['a'][np.array(bb)];K=len(active);cnt=np.bincount(mi);print('active params',K,flush=True)
 # Use exact post-PWM adjoint gradients; damp the approximate Hessian.
 g_snr,g_stoi=physical_grad(d,y);w=np.ones(len(y));diag=.15*cnt+1.;mat=LinearOperator((K,K),matvec=lambda v:backward(forward(v,aa,mi)*w,aa,mi,K)+diag*v);M=LinearOperator((K,K),matvec=lambda v:v/(cnt*.2+1));best=m0;bestbk=bk.copy();besty=y.copy();results=[]
 for alpha in (.0,.25,.75,1.5):
  rhs=backward(g_snr+alpha*g_stoi,aa,mi,K);v,info=cg(mat,rhs,rtol=.006,maxiter=60,M=M);print('CG',alpha,info,np.percentile(v,[0,1,25,50,75,99,100]),flush=True)
  for scale in (.5,1.,1.75):
   b=bk.copy().ravel();b[active]=np.clip(np.rint(b[active]+v*scale),-512,511);b=b.reshape(bk.shape);yy,_,ov=reconstruct(t,tb,b,bm,ln,idx,10)
   if ov:continue
   m=s.measure(t,yy,ww);m.update(alpha=alpha,scale=scale,changed=int(np.sum(b!=bk)),bytes=len(idx),kbps=len(idx)*8/(len(t)/FS)/1000,overflow=0);print('CANDIDATE',m,flush=True);results.append(m)
   if m['snr']>=best['snr'] and m['stoi']>best['stoi']:
    best=m;bestbk=b;besty=yy;dd=dict(d);dd['bk']=b;s.save(tag,dd,idx,yy,m);print('ACCEPTED',flush=True)
 print('FINAL',best,flush=True);(s.ROOT/(tag+'_trials.json')).write_text(json.dumps(dict(baseline=m0,final=best,trials=results),indent=2))
if __name__=='__main__':run(*sys.argv[1:])

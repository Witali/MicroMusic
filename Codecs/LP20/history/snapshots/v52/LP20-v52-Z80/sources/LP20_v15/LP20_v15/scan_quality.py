import json,signal,math,sys
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly
from build_16k import build,lut10
import pattern_balance,encode as e
ROOT=Path(__file__).resolve().parent.parent
SRC=ROOT/'demo/training.npz';D=np.load(SRC);Y=D['y'];W=D['ww10'];REF=e.lp(resample_poly(D['target']/127,768,125),3500);OUT=ROOT/'trials';OUT.mkdir(exist_ok=True)
V,INV=np.unique(lut10(W)[Y+512],return_inverse=True)
def measure(pats,period):
 widths=np.array([pats[int(k)] for k in V],dtype=np.int16)[INV].ravel();bw=period//4;g=math.gcd(48000*bw,20000000);z=(np.clip(widths[:,None]-np.arange(4)*bw,0,bw).astype(np.float32)*2/bw-1).ravel();z=e.lp(resample_poly(z,48000*bw//g,20000000//g),7000)/.875*128/127
 return e.align_metric(REF,e.lp(z,3500))
def alarm(a,b):raise TimeoutError('schedule timeout')
signal.signal(signal.SIGALRM,alarm)
results=[];candidates=[]
for g in ([35,100,135,150,160],[24,72,110,135,150,160],[35,80,110,135,150,160],[35,90,120,140,152,160],[25,80,120,140,152,160],[25,75,105,130,150,160],[35,85,120,135,150,160],[32,80,112,136,150,160],[28,84,112,132,148,160],[40,100,125,140,150,160],[35,100,125,140,150,160],[35,100,125,140,152,160],[35,80,112,130,144,152,160],[35,85,110,130,144,152,160],[35,100,120,136,148,154,160],[35,75,105,130,146,154,160],[20,70,110,134,150,160]):
 candidates.append(g+[320-x for x in g[-2::-1]])
for i in map(int,sys.argv[1:] or range(len(candidates))):
 grid=candidates[i]
 try:
  signal.alarm(4);p=OUT/f'trial_{i:02d}_adj';m=build(SRC,p,period=320,grid=grid,alpha=None);signal.alarm(0)
  for alpha in (None,.01,.15,1.0):
   if alpha is None:pp={int(k):v for k,v in m['patterns'].items()}
   else:pp={int(w):pattern_balance.patterns(int(w),320,8,grid,alpha) for w in W}
   q=measure(pp,320);rec=dict(grid=grid,alpha=alpha,core_adj=m['used']-m['stream_bytes']-1,**q)
   print('METRIC',rec,flush=True);results.append(rec)
   (OUT/f'results_{i:02d}.json').write_text(json.dumps(results,indent=2))
 except Exception as x:
  signal.alarm(0);print('FAIL',grid,repr(x),flush=True)

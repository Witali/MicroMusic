"""Closed-loop excitation re-quantization for LPC3-AVR L3AV.

Source target is the *decoded LPX3 v1 pre-emphasized signal* at 8 kHz,
not its original copyrighted recording. Future encoder may optimize the
original PCM instead. Only re-encodes the excitation, keeping LPC geometry.
"""
from __future__ import annotations
import numpy as np
from numba import njit

@njit(cache=True)
def decode_pre(q,scales,bits,a):
 n=len(q);hist=np.zeros(10,np.float64);out=np.empty(n,np.float64)
 half=1<<(bits-1)
 for t in range(n):
  co=a[t//160,(t%160)//20]; acc=0.
  for k in range(10):acc+=co[k]*hist[k]
  v=(int(q[t])-half)*scales[t//80]-acc
  if v>2:v=2
  elif v<-2:v=-2
  for k in range(9,0,-1):hist[k]=hist[k-1]
  hist[0]=v;out[t]=v
 return out

@njit(cache=True)
def evaluate_block(target, co, hist0, bits, step):
 n=len(target); hist=hist0.copy(); half=1<<(bits-1)
 out=np.empty(n,np.uint8);loss=0.
 for i in range(n):
  acc=0.
  for k in range(10):acc+=co[i,k]*hist[k]
  needed=(target[i]+acc)/step
  qi=int(np.floor(needed+.5))
  if qi<-half:qi=-half
  elif qi>=half:qi=half-1
  v=qi*step-acc
  if v>2:v=2
  elif v<-2:v=-2
  d=v-target[i];loss+=d*d
  for k in range(9,0,-1):hist[k]=hist[k-1]
  hist[0]=v;out[i]=qi+half
 return loss,out,hist

def scale_to_byte(step):
 import math
 return min(255,max(0,int(round(math.log2(max(step,1e-12)/.001)*16+128))))

def byte_to_scale(b):
 return .001 * 2.0**((int(b)-128)/16.)

def optimize(src,analysis,frames, coeff_bits, tolerance, lsf=False, allow4=False):
 """Return chosen per-block modes, scales, q; fidelity budget is absolute
 per-sample extra RMS at preemphasis stage (tolerance 0-0.04).
 """
 oldbits=src['bits'];n=src['n'];originalq=np.array(src['qs'],np.uint8)
 refco=np.asarray(analysis['coeffExact'],np.float64)
 steps=np.array([byte_to_scale(c) for c in src['scales']],np.float64)
 reference=decode_pre(originalq,steps,oldbits,refco)
 if lsf:
  # LSF conversion is nonlinear; use the original LPC subframe shape during
  # RDO and then verify on the actual fixed-point MCU playback engine.
  approx=refco
 else:
  end=np.array([[x/scale for x in q] for scale,q in frames],np.float64)
  prev=np.concatenate([end[:1],end[:-1]],axis=0)
  approx=prev[:,None,:]+(end-prev)[:,None,:]*((np.arange(8)+.5)/8)[:,None]
 hist=np.zeros(10,np.float64)
 choices=[]
 delta=[-56,-48,-40,-32,-24,-16,-12,-8,-4,0,4,8,12,16,24,32,40,48,56,64]
 for bi in range((n+79)//80):
  st=bi*80;en=min(st+80,n);target=reference[st:en]
  coff=approx[st//160,4*((st%160)//80):4*((st%160)//80)+4]
  expanded=coff[np.arange(en-st)//20]
  levels=[2,3]+([4] if allow4 else [])
  best={}
  for mode in levels:
   score=1e99;save=None
   for code in sorted(set(max(0,min(255,int(src['scales'][bi])+offset)) for offset in delta)):
    loss,q,h=evaluate_block(target,expanded,hist,mode,byte_to_scale(code))
    if loss<score:score=loss;save=(mode,code,q,h)
   best[mode]=(score,save)
  # 3 bits is fidelity baseline; 2 bits is adopted if extra PCM error is small.
  chosen=best[3]
  if best[2][0] <= best[3][0]+(en-st)*(tolerance**2):chosen=best[2]
  if allow4 and best[3][0] > (en-st)*(tolerance**2)*3.0:
   if best[4][0] < best[3][0]*0.5:chosen=best[4]
  loss,(mode,code,q,hist)=chosen
  choices.append({'mode':mode,'scale':code,'qs':q.tolist(),'mse':float(loss/len(q))})
 return choices

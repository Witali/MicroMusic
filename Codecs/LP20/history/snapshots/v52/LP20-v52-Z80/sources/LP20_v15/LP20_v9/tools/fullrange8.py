"""Wider PWM range using unchanged 8-bit codec, exact timing verification."""
import sys,json
from pathlib import Path
import numpy as np
import opt_build as b, build_packed as p, encode as e
from scipy.signal import resample_poly
from precision_study import render

def actions(order):
 a=[(10,'ld hl,0',(0x21,0,0)),(11,'add hl,sp',(0x39,)),(4,'ld a,l',(0x7d,)),(4,'or a',(0xb7,)),(15,'peek',()),(45,'addr_lo',()),(45,'addr_hi',()),(15,'peek',()),(37,'count_lo',()),(43,'count_hi',()),(15,'peek',()),(23,'gate',()),(34,'advance_fast',()),(6,'dec sp',(0x3b,)),(10,'ld hl,0',(0x21,0,0)),(11,'add hl,sp',(0x39,)),(21,'read_packed',())]
 old=b.actions(order,fast=True);return a+old[old.index((4,'ld l,e',(0x6b,))):]

def main(npz,out,period=128,pulses=20,maxlevels=77):
 d=np.load(npz);a=actions(d['tb'].shape[1]);good=[]
 for w in range(12,period-11):
  if b.schedule(a,period,pulses,w,False) is not None:good.append(w)
 mid=period//2;good=sorted(set(good)&{period-x for x in good});print('symmetric widths',good,flush=True)
 # Choose symmetric nearest width from feasible set, allowing nonuniform levels.
 span=mid-min(good);desired=np.linspace(mid-span,mid+span,maxlevels);ww=tuple(sorted(set(min(good,key=lambda w:(abs(w-v),abs(w-mid))) for v in desired)));levels=len(ww);assert levels%2
 lut=[min(range(levels),key=lambda i:abs(ww[i]-(mid+((y if y<128 else y-256)*span/128)))) for y in range(256)]
 b.widths_for=lambda p,l:ww;b.quant=lambda y,l:lut[y&255]
 p.build(npz,out,period,pulses,levels,1)
 # Render measured widths, matching the same LUT used in the ROM.
 w=np.asarray(ww)[np.asarray(lut)[d['y']&255]];wwv=np.repeat(w,pulses);bw=period//4
 z=(np.clip(wwv[:,None]-np.arange(4)*bw,0,bw).astype(np.float32)*2/bw-1).ravel();import math;g=math.gcd(48000*bw,20000000);z=e.lp(resample_poly(z,48000*bw//g,20000000//g),7000);t=d['target'];ref=resample_poly(t/127,768,125);gain=.98/max(abs(ref));sc=z/(2*span/period)*128/127;metric=e.align_metric(e.lp(ref,3500),e.lp(sc,3500));metric.update(min_width=min(ww),max_width=max(ww),span=span,levels=levels,range_vpp=2*span/period,actual_min_width=int(w.min()),actual_max_width=int(w.max()));print(metric,flush=True);e.wav(Path(out).with_suffix('.wav'),sc*gain*min(1,.98/(max(abs(sc))*gain)));e.wav(str(out)+'_raw_duty.wav',z);Path(str(out)+'_metrics.json').write_text(json.dumps(metric,indent=2))
if __name__=='__main__':main(sys.argv[1],sys.argv[2],*map(int,sys.argv[3:]))

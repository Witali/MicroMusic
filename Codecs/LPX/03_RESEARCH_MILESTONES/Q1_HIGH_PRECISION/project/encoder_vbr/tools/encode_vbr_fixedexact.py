#!/usr/bin/env python3
"""Closed-loop VBR for EXACT AVR fixed-point decoder (emulated by Numba).
Targets clipped Q14 PCM and follows C++ truncation, history and coefficients.
Not an on-hardware cycle benchmark. Requires coefficient trace exported by C++.
"""
import argparse,sys,struct,json,math
from pathlib import Path
import numpy as np,soundfile as sf
from numba import njit
from pystoi import stoi
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'tools'))
from pack_lpx3_avr import prepare_frames,coeff_pack,pack_bits_lsb,HEADER

@njit(cache=True)
def _clamp(v,l,h):
 return l if v<l else (h if v>h else v)
@njit(cache=True)
def _clamp_int16(v):
 return _clamp(v,-32767,32767)
@njit(cache=True)
def _csigned_div(a,b):
 return a//b if a>=0 else -((-a)//b)

@njit(cache=True)
def _encode_trial(xq,aq,hinit,prevd,pre,step,bits):
 hist=hinit.copy();prev=prevd;n=len(xq);q=np.empty(n,np.uint8);pcm=np.empty(n,np.uint8);tot=0
 maxq=(1<<(bits-1))-1;minq=-(1<<(bits-1))
 for j in range(n):
  acc=0
  for k in range(10):acc+=(int(aq[j,k])*int(hist[k]))>>12
  # Input target waveform after de-emphasis. Use output target in signed Q14.
  preterm=(pre*prev)>>14
  needed=int(xq[j])-preterm+acc
  # Mathematical nearest quantization of the desired excitation.
  val=(needed+step//2)//step if needed>=0 else -((-needed+step//2)//step)
  val=_clamp(val,minq,maxq)
  pred=_clamp_int16(val*step-acc)
  for k in range(9,0,-1):hist[k]=hist[k-1]
  hist[0]=pred
  prev=_clamp_int16(pred+preterm)
  clipped=_clamp(prev,-16384,16384)
  duty=128+_csigned_div(clipped*127,16384)
  duty=_clamp(duty,0,255)
  pcm[j]=duty
  q[j]=val-minq
  e=int(clipped)-int(xq[j]);tot+=e*e
 return q,pcm,tot,hist,prev


def make(x,analysis,coeff_trace,source,dest,lam,only=None,fast=False,context=None):
 if fast:
  from fast_vbr import make_fast
  return make_fast(x,analysis,coeff_trace,source,dest,lam,only,context=context)
 a=json.loads(Path(analysis).read_text());pre=round(float(a['meta']['pre'])*16384)
 # Require the matching source LPX3 header to avoid using frame data
 # prepared for a different recording.
 original=Path(source).read_bytes()
 if len(original)<24:raise ValueError('source LPX3 truncated')
 magic,ver,bits,rate,count,base,block,bright,nblocks=struct.unpack_from('<4sBBHIIHHI',original)
 if magic!=b'LPX3' or ver!=1 or bits not in (2,3,4) or rate!=8000 or count!=len(x) or block!=80:
  raise ValueError('source LPX3 header does not match input 8kHz WAV')
 x=np.asarray(x,np.float64);xq=np.clip(np.rint(x*16384),-16384,16384).astype(np.int32)
 qcoeff=np.loadtxt(coeff_trace,delimiter=',')
 assert np.array_equal(qcoeff[:,0],np.arange(len(qcoeff))*20)
 co=np.repeat(qcoeff[:,1:].astype(np.int32),20,axis=0)[:len(x)]
 assert len(co)==len(x)
 framecodes=prepare_frames(a['lsfFrame'],bits=10,lsf=True)
 assert len(framecodes)==(len(x)+159)//160
 # Load fixed-point excitation step table, MUST match C++ src/scale_table.inc.
 ss=(R/'src'/'scale_table.inc').read_text().split('\n',1)[1]
 import re
 steps=np.asarray([int(z) for z in re.findall(r'\b\d+\b',ss)],dtype=np.int32);assert len(steps)==256
 hist=np.zeros(10,np.int32);prevd=0
 qpack=[];modes=[];scales=[];blockLoss=[];reference=[]
 for st in range(0,len(x),80):
  en=min(st+80,len(x));target=xq[st:en];coeff=co[st:en];n=len(target)
  # Ideal residual needs from unquantized Q14 pre-emphasized source.
  res=[]
  for j in range(n):
   idx=st+j
   prevsample=int(xq[idx-1]) if idx else 0
   expred=int(xq[idx])-((pre*prevsample)>>14)
   for k in range(10):
    hidx=idx-k-1
    if hidx>=0:
     a0=int(xq[hidx])
     a1=int(xq[hidx-1]) if hidx else 0
     xp=a0-((pre*a1)>>14)
     expred+=((int(co[idx,k])*xp)>>12)
   res.append(expred)
  rms=max(1.0,float(np.sqrt(np.mean(np.square(np.asarray(res,dtype=np.float64))))))
  energy=max((.025*16384)**2,float(np.mean(target.astype(np.float64)**2)))
  options=[]
  for bits in ([only] if only else (3,4,5,6)):
   nominal=rms/max(1,(1<<(bits-1))-.5)
   codes=[]
   for t in (.3,.4,.5,.6,.75,.9,1.,1.12,1.3,1.55,1.85,2.25,2.9,3.7,5.,7.):
    z=nominal*t
    # step = 16384*0.001*2**((code-128)/16)
    cb=int(round(128+16*np.log2(max(1.0,z)/16.384)))
    codes.append(_clamp(cb,0,255))
   for sc in sorted(set(codes)):
    step=int(steps[sc])
    if step<=0:continue
    q,pcm,loss,hh,dd=_encode_trial(target,coeff,hist,prevd,pre,step,bits)
    val=loss/n/energy+lam*(bits-3)
    options.append((val,loss,bits,sc,q,pcm,hh,dd))
  if not options:raise ValueError('No encoding options for block')
  _,loss,bits,scale,q,pcm,hh,dd=min(options,key=lambda o:o[0])
  hist=hh;prevd=dd
  modes.append(bits);scales.append(scale);qpack.append(q);reference.extend(pcm.tolist());blockLoss.append(float(loss/n))
 out=bytearray(HEADER.pack(b'L3AV',1,3,8000,len(x),pre,0,160,80));old=None
 for fi,f in enumerate(framecodes):
  out.extend(coeff_pack(f,old,10,lsf=True));old=f
  for sub in range(2):
   i=fi*2+sub
   if i>=len(qpack):continue
   out.extend((modes[i],scales[i]));out.extend(pack_bits_lsb(qpack[i],modes[i]))
 dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(out)
 np.asarray(reference,dtype='u1').tofile(str(dest)+'.exact.pcm8')
 np.concatenate([np.asarray(q,dtype='i2')-(1<<(b-1)) for q,b in zip(qpack,modes)]).astype('<i2').tofile(str(dest)+'.q_signed.i16')
 result={'bytes':len(out),'samples':len(x),'average_bits':float(np.mean(modes)),'mode_counts':{b:modes.count(b) for b in [3,4,5,6]},'lambda':lam,'only_mode':only,'step_table':'Q14 exact','note':'machine C++ decoder and integer model must produce exactly the same pcm8'}
 return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source_wav');p.add_argument('lsf_co_json');p.add_argument('coeff_trace_csv');p.add_argument('original_lpx3');p.add_argument('output');p.add_argument('--lambda',type=float,default=.00025);p.add_argument('--fixed-bits',type=int,choices=[3,4,5,6]);args=p.parse_args()
 x,rate=sf.read(args.source_wav);assert rate==8000 and x.ndim==1
 result=make(x,args.lsf_co_json,args.coeff_trace_csv,args.original_lpx3,args.output,args.__dict__['lambda'],args.fixed_bits)
 print(json.dumps(result,ensure_ascii=False,indent=2))

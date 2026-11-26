#!/usr/bin/env python3
"""LPX20 analysis-by-synthesis encoder, 125 or 156.25 kHz.
Clip-trained VQ; not a generalization benchmark. One silent EOF bank is added.
"""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import argparse, json, math, struct, time
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly,butter,sosfiltfilt,correlate
from scipy.io.wavfile import read,write
from pystoi import stoi
import encoder_core as c
from build import make,unpack,CPU,widths_for
from verify import verify,ref
ROOT=Path(__file__).resolve().parent
FS=15625;SR=48000;PERIOD=128;PULSES=10;LEVELS=77

def wav(p,x,sr=SR):write(str(p),sr,np.clip(np.rint(x*32767),-32768,32767).astype('<i2'))
def lp(x,cutoff):return sosfiltfilt(butter(5,cutoff,fs=SR,output='sos'),x)
def render(y):
 # Exact mean of rectangular PWM over four bins per carrier cycle.
 mid=LEVELS//2;lut=np.asarray(widths_for(PERIOD,LEVELS));w=lut[np.clip(mid+(y.astype(np.int32)*mid+64)//128,0,2*mid)]
 ww=np.repeat(w,PULSES);binwidth=PERIOD//4
 z=(np.clip(ww[:,None]-np.arange(4)*binwidth,0,binwidth).astype(np.float32)*2/binwidth-1).ravel()
 g=math.gcd(SR*binwidth,CPU);z=resample_poly(z,SR*binwidth//g,CPU//g);return lp(z,7000)

def align_metric(x,y):
 L=min(len(x),len(y));x=x[:L].astype(float);y=y[:L].astype(float);x-=x.mean();y-=y.mean()
 # Gain fit and sub-ms latency alignment only, to compare unlike output stages.
 cc=correlate(y,x,mode='full',method='fft');mid=L-1;delay=int(np.argmax(cc[mid-16:mid+17])-16)
 if delay>=0:a=x[:L-delay];b=y[delay:L]
 else:a=x[-delay:L];b=y[:L+delay]
 g=np.dot(a,b)/(np.dot(b,b)+1e-20);b*=g;e=a-b
 return dict(snr=float(10*np.log10((np.dot(a,a)+1e-20)/(np.dot(e,e)+1e-20))),stoi=float(stoi(resample_poly(a,1,3),resample_poly(b,1,3),16000)),delay=delay,gain=float(g))
def pack(path,tb,bk,bm,idx):
 # 0 is EOF: one separate zero predictor bank, one zero excitation vector.
 order=tb.shape[1];block=bk.shape[1];banks=tb.shape[0]+1
 t=np.concatenate([np.zeros((1,order,256),np.int16),tb]);b=np.vstack([np.zeros((1,block),np.int16),bk]);m=np.r_[0,bm+1].astype(np.uint8);i=(idx.astype(np.uint16)+1).astype(np.uint8)
 raw=b'LP20'+bytes([order,block,banks])+struct.pack('<HBBI',PERIOD,PULSES,LEVELS,len(idx)*block)+t.astype(np.uint8).tobytes()+m.tobytes()+np.ascontiguousarray(b.T,dtype=np.uint8).tobytes()+i.tobytes();path.write_bytes(raw)
 return len(raw)
def run(source,output,profiles,beamwidth,rounds,baseline=None):
 output.mkdir(parents=True,exist_ok=True);x=c.load(source);xr=resample_poly(x,384,125); # 15625 -> 48000 = 384/125
 wav(output/'reference.wav',xr);report=[]
 if baseline:
  sr,z=read(baseline);z=z.astype(float)/32768;g=math.gcd(sr,SR);z=resample_poly(z,SR//g,sr//g);report.append(dict(profile='v0.7',**align_metric(lp(xr,3500),lp(z,3500)),snr_fullband=align_metric(lp(xr,7000),lp(z,7000))['snr']));print(report[-1],flush=True)
 for order,n,nb in profiles:
  name=f'lpc{order}_b{n}_{nb}banks';t=np.pad(np.clip(x*c.SCALE,-128,127),(0,(-len(x))%n));start=time.time();a,tb,bk,bm=c.initialize(t,order,nb,n);print(name,'initialized',a.tolist(),flush=True)
  ii,yy,hh,cost,over=c.beam(t,bk,tb,bm,beamwidth,.25,LEVELS//2);print(name,'beam',cost,over,time.time()-start,flush=True)
  for it in range(rounds):
   pos=np.argsort(ii).astype(np.int32);off=np.r_[0,np.cumsum(np.bincount(ii,minlength=c.K))].astype(np.int32);b2,m2=c.refine(bk,tb,bm,t,hh,pos,off,max(1,2-it),.25,LEVELS//2);jj,zz,h2,c2,w2=c.beam(t,b2,tb,m2,beamwidth,.25,LEVELS//2)
   if c2<cost:bk,bm,ii,yy,hh,cost,over=b2,m2,jj,zz,h2,c2,w2
   print(name,'refine',it,cost,over,time.time()-start,flush=True)
  payload=output/(name+'.lp20');sz=pack(payload,tb,bk,bm,ii);args=unpack(payload)
  # CPU expected decoder bytes are compared against the reference encoder.
  r=np.frombuffer(ref(*args[:7],tail=0),np.int8)[1:];assert np.array_equal(r,yy.astype(np.int8))
  pwm=render(yy);ref7=lp(xr,7000);m=align_metric(ref7,pwm);m3=align_metric(lp(xr,3500),lp(pwm,3500))
  wav(output/(name+'.wav'),pwm/(2*(PERIOD*3//10)/PERIOD*c.SCALE/128)*.88);wav(output/(name+'.pcm.wav'),yy/c.SCALE*.88,FS)
  d=dict(profile=name,order=order,block=n,active_banks=nb,pcm_hz=FS,pwm_hz=CPU/PERIOD,levels=LEVELS,seconds=len(yy)/FS,payload_bps=FS*8/n,stream_bytes=len(ii),container_bytes=sz,effective_bps=sz*8/(len(yy)/FS),overflows=int(over),snr_fullband=m['snr'],stoi_fullband=m['stoi'],snr_0_3500=m3['snr'],stoi_0_3500=m3['stoi'],delay=m['delay'],gain=m['gain'])
  try:
   rom,asm,meta=make(*args);p=output/name;p.with_suffix('.bin').write_bytes(rom);p.with_suffix('.asm').write_text(asm);p.with_suffix('.json').write_text(json.dumps(meta,indent=2));test=verify(args,rom,meta);d.update(rom_used=meta['used'],decoder_t=meta['decoder_t'],padding_t=meta['padding_t'],machine_test=test)
  except Exception as e:d['machine_error']=str(e)
  report.append(d);(output/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(d),flush=True)
 return report

def main():
 global PERIOD,PULSES,LEVELS
 p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--out',required=True);p.add_argument('--profiles',default='4:8:4,6:8:4,8:8:4,8:4:4,8:16:4');p.add_argument('--beam',type=int,default=4);p.add_argument('--rounds',type=int,default=1);p.add_argument('--baseline');p.add_argument('--carrier',type=int,choices=[125000,156250],default=156250);a=p.parse_args();PERIOD,PULSES,LEVELS=(160,8,97) if a.carrier==125000 else (128,10,77);run(a.input,Path(a.out),[tuple(map(int,s.split(':'))) for s in a.profiles.split(',')],a.beam,a.rounds,a.baseline)
if __name__=='__main__':main()

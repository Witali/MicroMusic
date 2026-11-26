#!/usr/bin/env python3
"""Read self-contained PH2F, reconstruct LPC, harmonic correction and PWM.
Desktop only. No reference waveform or pitch tracker required for decoding.
The external dictionary in PH20 is packaged as a compact LP10G model (0 tokens).
"""
from harmonic import *
import argparse,tempfile,zlib,math
from pack_context import pack as pack_model,unpack as unpack_model
import pattern_balance
from scipy.signal import resample_poly
H=struct.Struct('<4sIII')

def make_file(d,m,payload,path):
 with tempfile.TemporaryDirectory() as td:
  file=Path(td)/'model.lp10g';pack_model(dict(d,idx=np.empty(0,np.int16)),m,file);md=file.read_bytes()
 data=md+payload;Path(path).write_bytes(H.pack(b'PH2F',len(md),len(payload),zlib.crc32(data))+data);return len(md),len(data)+H.size

def read_file(path):
 a=Path(path).read_bytes();magic,l,n,crc=H.unpack_from(a);assert magic==b'PH2F' and len(a)==H.size+l+n and zlib.crc32(a[H.size:])==crc
 with tempfile.TemporaryDirectory() as td:
  model_file=Path(td)/'model.lp10g';model_file.write_bytes(a[H.size:H.size+l]);d,m=unpack_model(model_file)
 ix,y,yy=unpack(d,a[H.size+l:]);return d,m,ix,y,yy

def render(d,m,y):
 w=f.lut10(d['ww10'])[y+512];p=m['period'];pulses=2560//p;v,inv=np.unique(w,return_inverse=True);widths=np.array([pattern_balance.patterns(int(k),p,pulses,m['grid'],m['pattern_alpha']) for k in v],dtype=np.int16)[inv].ravel();bw=p//4;g=math.gcd(48000*bw,20000000);z=(np.clip(widths[:,None]-np.arange(4)*bw,0,bw).astype(np.float32)*2/bw-1).ravel();return f.e.lp(resample_poly(z,48000*bw//g,20000000//g),7000)/.875*128/127

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('file');p.add_argument('wav');p.add_argument('--raw-level',action='store_true');a=p.parse_args();d,m,ix,y,yy=read_file(a.file);z=f.e.lp(render(d,m,yy),3500);z-=z.mean();z=z if a.raw_level else z*.98/max(abs(z));f.e.wav(a.wav,z);print('Decoded samples:',len(y),'tokens:',len(ix),'corrected samples:',np.count_nonzero(yy!=y))
if __name__=='__main__':main()

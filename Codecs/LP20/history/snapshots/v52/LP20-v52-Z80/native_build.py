#!/usr/bin/env python3
"""Rebuild and verify the two legacy LPC firmware variants. Python emits
machine code + ASM; test_lpc is an independent opcode-subset interpreter.
The 'native255-experimental' variant explicitly exceeds 16 KiB.
"""
import argparse,os,sys,json,subprocess
from pathlib import Path
os.environ.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',LP20_ALIAS8='1')
import numpy as np
ROOT=Path(__file__).resolve().parent;S=ROOT/'sources'
sys.path[:0]=[str(S/p) for p in ['LP20_v38','LP20_v17_gain','LP20_v22','LP20_v25','LP20_v15/LP20_v15','LP20_v15/LP20_v9','LP20_v15/LP20_v9/tools']]
import schedule_opt

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('profile',choices=['native63','native255-experimental']);ap.add_argument('clip',choices=['first','second']);args=ap.parse_args();profile,clip=args.profile,args.clip
 if profile=='native63':
  import zero_builder52 as b
  p=np.load(ROOT/'native63-grid.npz');sums=p['sums'];patterns=p['patterns'];tie=1e-9*abs(sums[None,:]-1280)
 else:
  import zero_builder255 as b
  patterns=np.load(ROOT/'pwm255.npy');sums=patterns.sum(1);tie=0
 b.share_tails.choose=schedule_opt.choose
 lut=np.argmin(abs((1280+np.arange(-512,512)*1120/512)[:,None]-sums[None,:])+tie,axis=1)
 if profile=='native63':assert np.ptp(lut.reshape(256,4),axis=1).max()<=1
 b.pattern_balance.patterns=lambda w,*args:tuple(map(int,patterns[np.searchsorted(sums,w)]))
 b.lut10=lambda ww:sums[lut]
 out=ROOT/profile/clip
 m=b.build(out/'model.npz',out/'decoder',period=320,grid=[35,100,135,145,150,160,170,175,185,220,285],alpha=.001)
 exe=ROOT/'test_lpc'
 if not exe.exists():subprocess.run(['g++','-O3','-std=c++17',str(S/'test_lpc.cpp'),'-o',str(exe)],check=True)
 test=json.loads(subprocess.check_output([str(exe),str(out/'decoder.bin'),str(out/'decoder.map'),str(out/'decoder.expected'),'320','8','0','16',str(out/'decoder.threads')],text=True));(out/'test.json').write_text(json.dumps(test,indent=2));print(m['used']-m['stream_bytes'],test)
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Rebuild and verify the stand-alone PWM test ROMs."""
from pathlib import Path
import subprocess, json
import numpy as np
from build_pwm import build,ROOT

def main():
    exe=ROOT/'test_pwm'
    if not exe.exists():
        subprocess.run(['g++','-O3','-std=c++17',str(ROOT/'test_pwm.cpp'),'-o',str(exe)],check=True)
    p=ROOT/'test';p.mkdir(exist_ok=True)
    build(np.arange(255,dtype=np.uint8),p/'all255')
    # The compressed PCM map stores a base per high byte and three
    # packed two-bit increments, in unsigned high-byte order.
    pcm=np.arange(-512,512,dtype=np.int16)
    mp=np.fromfile(ROOT/'pcm-to-pwm255.bin',np.uint8).astype(int)
    h=(pcm//4)&255;f=pcm&3
    levels=mp[h]+np.where(f==0,0,(mp[256+h]>>np.maximum(0,2*(f-1)))&3)
    # Expected indices can be computed independently from table sums.
    pats=np.load(ROOT/'pwm255.npy');s=pats.sum(axis=1)
    assert np.array_equal(levels,np.fromfile(p/'all1024.idx',np.uint8))
    build(levels,p/'all1024',pcm=pcm)
    for n in ('all255','all1024'):
        d=json.loads(subprocess.check_output([str(exe),str(p/(n+'.bin')),str(p/(n+'.widths'))],text=True))
        (p/(n+'-test.json')).write_text(json.dumps(d,indent=2)+'\n');print(n,d)
if __name__=='__main__':main()

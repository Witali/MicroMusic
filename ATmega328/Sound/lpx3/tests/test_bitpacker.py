#!/usr/bin/env python3
"""Regression for NumPy's 8-bit left-shift overflow on 5/6-bit symbols."""
import sys,numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from pack_lpx3_avr import pack_bits_lsb
for bits in (2,3,4,5,6):
  vals=np.asarray(list(range(1<<bits))*3+[0,(1<<bits)-1,12%(1<<bits),17%(1<<bits)],dtype=np.uint8)
  v=[int(x)%(1<<bits) for x in vals]
  data=pack_bits_lsb(vals,bits)
  buf=n=0;q=[]
  for byte in data:
    buf|=int(byte)<<n;n+=8
    while n>=bits and len(q)<len(v):
      q.append(buf&((1<<bits)-1));buf>>=bits;n-=bits
  assert q==v,(bits,q,v)
print('PASS NumPy uint8 packer roundtrip 2/3/4/5/6-bit words')

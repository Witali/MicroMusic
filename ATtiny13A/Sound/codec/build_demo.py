#!/usr/bin/env python3
"""Build a wholly synthetic example (no recordings needed)."""
from pathlib import Path
import numpy as np
from build_hq import compile_one
root=Path(__file__).resolve().parent
f=[];lengths=[]
for i in range(32):
 pitch=0 if i%11==0 else 20+(i*3)%26
 gain=min(15,2+int(abs(np.sin(i*.3))*9))
 mode=i%4
 coeff=[0x79,0x7B,0x88,0x88] if i%4==0 else [0x69,0x8A,0x88,0x88]
 f.append([pitch,(mode<<4)|gain,*coeff]);lengths.append([256,128,64,128][i%4])
record=compile_one('demo',np.asarray(f,dtype=np.uint8),np.asarray(lengths,dtype=np.uint16),True)
print('Compiled synthetic example',record)

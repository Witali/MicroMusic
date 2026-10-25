#!/usr/bin/env python3
"""Produce a compact rights-free synthetic probe in L3AV for the Arduino example."""
from pathlib import Path
import struct,math
from pack_lpx3_avr import HEADER,coeff_pack,pack_bits_lsb
root=Path(__file__).resolve().parents[1]
sr=8000;duration=2.0;n=int(sr*duration)
# Test constant stable voiced source; Q12 LPC coefficient -0.8, excitation q3 pulses.
header=HEADER.pack(b'L3AV',1,0,sr,n,round(.85*16384),round(.18*16384),160,80)
rec=bytearray(header);prev=None
for f in range((n+159)//160):
 coeff=(100,(-80,10,-2,0,0,0,0,0,0,0))
 rec.extend(coeff_pack(coeff,prev));prev=coeff
 for b in range(2):
  st=f*160+b*80;count=min(80,n-st)
  if not count:continue
  q=[]
  for i in range(count):
   j=st+i
   pulse=3 if j%36==0 else (-1 if j%36==1 else 0)
   q.append(pulse+4)
  rec.extend((3,240));rec.extend(pack_bits_lsb(q,3))
out=root/'examples/LPX3_PROGMEM/synthetic_voice.l3av';out.write_bytes(rec)
print('synthetic L3AV',out,len(rec),'bytes')

#!/usr/bin/env python3
"""Deterministic fuzz of Codec2Tiny parameter decode against independent Python."""
import sys,random
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from test_codec2tiny import parse_asm,AVR,fields,expected_steps
ins,labels,sym=parse_asm()
sim=AVR(ins,labels,sym);sim.run('codec2tiny_init')
rng=random.Random(398231)
maxcycles=0
for i in range(2048):
    raw=bytes(rng.getrandbits(8) for _ in range(8))
    f=bytes([0]*8) if i==0 else bytes([255]*8) if i==1 else raw
    d=fields(f);sim.mem[0x60:0x68]=f
    cycles=sim.run('codec2tiny_decode_frame');maxcycles=max(maxcycles,cycles)
    assert tuple(sim.mem[0x68:0x6c])==tuple(d[:4]),('header',i)
    steps=[sim.mem[0x6e+2*j]+(sim.mem[0x6f+2*j]<<8) for j in range(3)]
    assert steps==expected_steps(d),('dds',i)
print('PASS: 2048 stress frames, maximum decode cycles:',maxcycles)

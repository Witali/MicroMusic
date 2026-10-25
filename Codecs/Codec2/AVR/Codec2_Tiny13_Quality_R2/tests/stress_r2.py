#!/usr/bin/env python3
"""Deterministic regression and edge stress for Codec2 Tiny13 R2.
This is an AVR source-level instruction interpreter, NOT hardware timing proof.
"""
from pathlib import Path
import sys, random, hashlib, statistics, wave, struct
from test_resonator import AVR,reference_decoder,GAIN_TAB
from codec2_test_common import parse_asm, fields
ROOT=Path(__file__).resolve().parents[1]
inst,labels,sym=parse_asm(ROOT/'src/codec2tiny_resonator.S')

def graypack(values):
    val=0;bits=0
    for width,n in values:
        assert 0 <= n < (1<<width)
        g=n^(n>>1)
        val=(val<<width)|g
        bits+=width
    assert bits==64,bits
    return val.to_bytes(8,'big')

def make_frame(v0,v1,p,e,ls):
    return graypack([(1,v0),(1,v1),(7,p),(5,e)]+[(5,int(a)) for a in ls])


def full_stream_test():
    rng=random.Random(20261024)
    # Main challenge: extreme coefficient changes, gain changes, boundary pitches,
    # and voiced/unvoiced transitions. Last four LSPs must be freely variable.
    cases=[make_frame(v0,v1,p,e,[q]*10)
        for v0,v1 in ((0,0),(0,1),(1,0),(1,1))
        for p,e,q in ((0,0,0),(127,31,31),(0,31,0),(127,0,31))]
    for k in range(40):
        cases.append(make_frame(rng.randrange(2),rng.randrange(2),rng.randrange(128),
                rng.randrange(32),[rng.randrange(32) for _ in range(10)]))
    sim=AVR(inst,labels,sym);sim.run('codec2tiny_init')
    expected,traces=reference_decoder(cases,debug=True)
    worst_decode=0;worst_sample=0
    for i,fr in enumerate(cases):
        sim.mem[0x60:0x68]=fr
        c=sim.run('codec2tiny_decode_frame')
        worst_decode=max(worst_decode,c)
        for n in range(160):
            c=sim.run('codec2tiny_sample')
            worst_sample=max(worst_sample,c)
            actual=sim.r[16]
            q=tuple(sim.mem[j] for j in (0x71,0x73,0x75))
            y=tuple(sim.mem[j] for j in (0x72,0x74,0x76))
            if (q,y,tuple(sim.mem[0x6e:0x71]))!=traces[i*160+n][:3]:
                raise AssertionError(('internal-state mismatch',i,n,(q,y,tuple(sim.mem[0x6e:0x71])),traces[i*160+n],actual,expected[i*160+n]))
            assert actual==expected[i*160+n],(i,n,actual,expected[i*160+n], 'voice',tuple(sim.mem[0x68:0x6a]), 'energy',sim.mem[0x6b], 'half',sim.mem[0x7f], 'sample',sim.mem[0x78], 'states',tuple(sim.mem[0x71:0x77]),'prev',sim.mem[0x7e])
    print('AVR_EDGE_STRESS',len(cases),'frames',len(expected),'PCM samples passed',
           'decode max',worst_decode,'sample max',worst_sample)
    return worst_decode,worst_sample


def multiply_test():
    sim=AVR(inst,labels,sym)
    n=0
    for signed_value in range(-128,128):
        for coeff in range(60):
            sim.r[20]=signed_value&255
            sim.r[21]=coeff
            sim.run('mul_coeff')
            s=signed_value*coeff
            reference=(s//32) if s>=0 else -((-s)//32)
            assert sim.r[22]==(reference&255),(signed_value,coeff,sim.r[22],reference)
            n+=1
    print('AVR_MULT',n,'input pairs passed')

if __name__=='__main__':
    multiply_test()
    full_stream_test()

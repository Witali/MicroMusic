#!/usr/bin/env python3
"""Regression tests: one-pass dual CRC16 vs two-pass baseline on Intel 8080.
No RAM, no tables; only standard-library Python dependencies.
Run: python3 test_compare.py
"""
from pathlib import Path
from math import lcm
from random import Random
import sys, time
from onepass_8080_tools import assemble
from emulate_onepass import emulate as emulate_onepass

ROOT=Path(__file__).resolve().parent
ROM_BYTES=65536
N_BITS=ROM_BYTES*8
P1,P2=0x0007,0x0009
EXPECTED_ONE_BYTES=68
EXPECTED_ONE_CYCLES=12066385
EXPECTED_TWO_BYTES=66
EXPECTED_TWO_CYCLES=13049432

def crc16(data,poly):
    value=0
    for b in data:
        value^=b<<8
        for _ in range(8):
            value=((value<<1) ^ (poly if value&0x8000 else 0))&0xFFFF
    return value

def gf2_product(a,b):
    v=0
    while b:
        if b&1: v^=a
        a<<=1;b>>=1
    return v

P32=gf2_product((1<<16)|P1,(1<<16)|P2)&0xFFFFFFFF

def crc32(data):
    value=0
    for b in data:
        value^=b<<24
        for _ in range(8):
            value=((value<<1) ^ (P32 if value&0x80000000 else 0))&0xFFFFFFFF
    return value

def rom_for(code, *, fill=0xFF, random=False, seed=0x8080):
    assert len(code)<=65532
    image=bytearray([fill])*65536
    image[:len(code)]=code
    if random:
        rng=Random(seed)
        image[len(code):-4]=rng.randbytes(65532-len(code))
    image[-4:]=crc32(image[:-4]).to_bytes(4,'big')
    assert crc32(image)==crc16(image,P1)==crc16(image,P2)==0
    return bytes(image)

def flipbits(rom,bits):
    result=bytearray(rom)
    for pos in bits:
        assert 0<=pos<N_BITS
        result[pos//8]^=1<<(7-(pos%8))
    return bytes(result)

def math_random_tests():
    r=Random(0x808080)
    for poly in (P1,P2):
        for _ in range(30000):
            old=r.randrange(65536);octet=r.randrange(256)
            t=(old>>8)^octet
            if poly==0x0007:
                newhigh=((old&0xFF)^(t>>7)^(t>>6))&255
                newlow=(t^(t<<1)^(t<<2))&255
            else:
                newhigh=((old&0xFF)^(t>>5))&255
                newlow=(t^(t<<3))&255
            actual=newhigh*256+newlow
            reference=old^(octet<<8)
            for _ in range(8):
                reference=((reference<<1) ^ (poly if reference&0x8000 else 0))&65535
            assert actual==reference,(hex(poly),old,octet,actual,reference)
    print('60,000 random byte-state transitions: PASS',flush=True)

def main():
    start=time.monotonic()
    math_random_tests()
    one_src=(ROOT/'dual_crc_0007_0009_onepass.asm').read_text()
    one_code,labels=assemble(one_src)
    assert one_code==(ROOT/'dual_crc_0007_0009_onepass.bin').read_bytes()
    assert len(one_code)==EXPECTED_ONE_BYTES
    assert P32==0x000E003F
    print('One-pass assembly + composite polynomial: PASS',flush=True)

    good=rom_for(one_code)
    assert good==(ROOT/'dual_crc_0007_0009_onepass_ROM_64KiB.bin').read_bytes()
    value=emulate_onepass(good,trace=True)
    assert value['cycles']==EXPECTED_ONE_CYCLES,value
    assert value['bc']==value['de']==0 and value['inte'] and value['sp']==65535
    assert value['reads']==65536 and value['unique_reads']==65536
    print(f"One pass: {len(one_code)} B, {value['cycles']:,} T, {value['cycles']/65536:.6f} T/B, every ROM address exactly once as data: PASS",flush=True)

    for mode in ('zero','random','other_random'):
        candidate=rom_for(one_code,fill=0 if mode=='zero' else 0xFF,
                          random=('random' in mode),seed=100 if mode=='random' else 200)
        result=emulate_onepass(candidate)
        assert result['inte'] and result['bc']==result['de']==0 and result['reads']==65536
    print('Empty, 0xFF, and random payload ROMs: PASS',flush=True)

    # Corrupt data or one of the four footer bytes, not executable code.
    for addr,mask in [(0x0100,1),(0x7FFF,0x40),(0x8000,0x80),
                      (0xFFFB,1),(0xFFFC,0x10),(0xFFFD,1),(0xFFFE,0x02),(0xFFFF,0x80)]:
        broken=bytearray(good);broken[addr]^=mask
        ref1=crc16(broken,P1);ref2=crc16(broken,P2)
        assert ref1!=0 or ref2!=0
        result=emulate_onepass(broken)
        assert (result['bc'],result['de'])==(ref1,ref2),(addr,result,ref1,ref2)
        assert not result['inte'] and result['reads']==65536
    print('Eight one-bit ROM faults (incl. all footer bytes): PASS',flush=True)

    # Corruption chosen to be missed by only one of the two CRCs.
    base=100000
    for period in (32767,57337):
        broken=flipbits(good,[base,base+period])
        ref1=crc16(broken,P1);ref2=crc16(broken,P2)
        assert (ref1==0) != (ref2==0)
        result=emulate_onepass(broken)
        assert (result['bc'],result['de'])==(ref1,ref2)
        assert not result['inte']
    print('Two-bit collisions against each single polynomial individually: PASS',flush=True)

    # A documented undetectable 4-bit error (same limitations as two-pass code).
    offsets=(0,777,1076,2007)
    bits=[N_BITS-1-50000-k for k in offsets]
    deliberately_missed=flipbits(good,bits)
    assert crc16(deliberately_missed,P1)==crc16(deliberately_missed,P2)==0
    res=emulate_onepass(deliberately_missed)
    assert res['inte'] and res['bc']==res['de']==0
    print('Documented 4-bit collision: test confirms limitation, PASS',flush=True)

    baseline=(ROOT/'baseline')
    sys.path.insert(0,str(baseline))
    from crc8080_tools import assemble as old_assemble,emulate as old_emulate
    two_source=(baseline/'dual_crc_0007_0009.asm').read_text()
    two_code,_=old_assemble(two_source)
    assert len(two_code)==EXPECTED_TWO_BYTES
    assert (baseline/'dual_crc_0007_0009.bin').read_bytes()==two_code
    two_img=rom_for(two_code)
    t=old_emulate(two_img,crc_layout='HC')
    assert t['cycles']==EXPECTED_TWO_CYCLES and t['INTE'] and t['rom_reads']==131072
    print(f'Two passes: {len(two_code)} B, {t["cycles"]:,} T, {t["cycles"]/65536:.6f} T/B: PASS',flush=True)
    print(f'BEST RESULT: one-pass time saving {t["cycles"]-value["cycles"]:,} T, '
          f'{100*(t["cycles"]-value["cycles"])/t["cycles"]:.3f}%'
          f'; code delta +{len(one_code)-len(two_code)} B',flush=True)
    print(f'ALL TESTS PASSED. Runtime {time.monotonic()-start:.1f} seconds.',flush=True)

if __name__=='__main__':main()

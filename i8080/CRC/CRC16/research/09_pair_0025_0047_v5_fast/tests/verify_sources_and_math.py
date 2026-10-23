#!/usr/bin/env python3
"""Self-contained v5 source/binary/ROM/CRC correctness checks."""
from __future__ import annotations
from pathlib import Path
import math
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'tools'))
from tiny8080_assembler import assemble
from build_rom import crc16,crc32,patch,POLYS

NAMES = [
 'baseline_fast75','baseline_compact73','baseline_compact_reset72',
 'baseline_unroll2_120','fast75_peephole','fast_p47_rotate',
 'speed74_reset','speed81_reset',
]
ROM_NAMES = ['baseline_fast75','fast75_peephole','fast_p47_rotate','speed74_reset','speed81_reset']
SIZES={
 'baseline_fast75':75,'baseline_compact73':73,'baseline_compact_reset72':72,
 'baseline_unroll2_120':120,'fast75_peephole':75,'fast_p47_rotate':82,
 'speed74_reset':74,'speed81_reset':81,
}

def polymod(poly,divisor):
    while poly.bit_length() >= divisor.bit_length():
        poly ^= divisor << (poly.bit_length()-divisor.bit_length())
    return poly

def polynomial_period(poly):
    residue=1
    for k in range(1,65536):
        residue = ((residue << 1) ^ (poly if residue & 0x8000 else 0)) & 65535
        if residue == 1: return k
    return None

def main():
    for name in NAMES:
        code = (ROOT/'bin'/f'{name}.bin').read_bytes()
        src = (ROOT/'asm'/f'{name}.asm').read_text()
        rebuilt,labels=assemble(src)
        assert code==rebuilt, f'ASM/BIN mismatch {name}'
        assert len(code)==SIZES[name],name
        print(f'  {name:26s}: {len(code):3d} bytes ASM==BIN OK')
    for name in ROM_NAMES:
        code=(ROOT/'bin'/f'{name}.bin').read_bytes()
        rom=(ROOT/'rom'/f'{name}_64K.bin').read_bytes()
        assert len(rom)==65536 and rom == patch(code),name
        assert rom[:len(code)]==code
        assert crc32(rom)==0,name
        assert all(crc16(rom,p)==0 for p in POLYS),name
        print(f'  {name:26s}: 64-KiB ROM CRC-16 pair 0/0, footer {rom[-4:].hex()}')

    # Byte update as a 16-bit field polynomial, not merely modulo 256:
    for t in range(256):
        def gf_product(t,p):
            y=0
            for i in range(16):
                if p>>i&1:y^=t<<i
            return y&0xffff
        assert gf_product(t,0x0025) == ((t ^ (t<<3))<<2 ^ t)&65535
        assert gf_product(t,0x0047) == (t ^ (t<<1) ^ (t<<2) ^ (t<<6))&65535

    g1=(1<<16)|0x0025
    g2=(1<<16)|0x0047
    product=0
    for i in range(17):
        if g2>>i&1:product ^=g1<<i
    assert product == 0x1006209BB,hex(product)
    assert polynomial_period(0x25)==1023
    assert polynomial_period(0x47)==21845
    assert math.lcm(1023,21845)>65536*8-1
    # The four-bit witness is a NON-DETECTED pattern for both CRCs.
    e=(1<<0)^(1<<1065)^(1<<1278)^(1<<3920)
    assert polymod(e,g1)==0 and polymod(e,g2)==0
    print('  Verified composite polynomial, both periods, four-bit collision')
    print('PASS: all source/binary/ROM/math checks')

if __name__=='__main__':main()

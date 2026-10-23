#!/usr/bin/env python3
"""Pure-Python mathematical and ROM-layout audit of key CRC handoff claims."""
from pathlib import Path
from math import gcd, lcm
import random
ROOT=Path(__file__).resolve().parent
N=65536

def gf2_mul(a,b):
    r=0
    while b:
        if b&1:r^=a
        a <<=1;b>>=1
    return r

def gf2_mod(a,b):
    while a.bit_length()>=b.bit_length(): a^=b<<(a.bit_length()-b.bit_length())
    return a

def gf2_gcd(a,b):
    while b:a,b=b,gf2_mod(a,b)
    return a

def bit_crc(data,poly,width,init=0):
    state=init;mask=(1<<width)-1;top=1<<(width-1)
    for byte in data:
        state^=byte<<(width-8)
        for _ in range(8):state=((state<<1)^(poly if state&top else 0))&mask
    return state

def period(poly):
    r=1
    for k in range(1,65536):
        r=((r<<1)^(poly if r&0x8000 else 0))&0xFFFF
        if r==1:return k
    raise AssertionError('cycle never returned')

def main():
    g1=0x10025;g2=0x10047
    assert gf2_mul(g1,g2)==0x1006209BB
    assert gf2_gcd(g1,g2)==1
    assert gf2_mod(g1,0b11)==0
    assert period(0x25)==1023 and period(0x47)==21845
    assert lcm(period(0x25),period(0x47))>8*N
    witness=sum(1<<pos for pos in (0,1065,1278,3920))
    assert gf2_mod(witness,g1)==0 and gf2_mod(witness,g2)==0
    rom=(ROOT/'SELECTED_FIRMWARE/milestone_dual_0025_0047_min42_DEMO_64KiB.bin').read_bytes()
    assert len(rom)==N
    assert bit_crc(rom[:-4],0x006209BB,32).to_bytes(4,'big')==rom[-4:]
    assert bit_crc(rom,0x006209BB,32)==0
    assert bit_crc(rom,0x0025,16)==0
    assert bit_crc(rom,0x0047,16)==0
    keys={'milestone_dual_0025_0047_min41_RESET.bin':41,
          'milestone_dual_0025_0047_min42.bin':42,
          'milestone_dual_0025_0047_mid57.bin':57,
          'milestone_dual_0025_0047_fast75.bin':75,
          'milestone_dual_0025_0047_fast82.bin':82}
    for filename,size in keys.items():
        assert len((ROOT/'SELECTED_FIRMWARE'/filename).read_bytes())==size
    rng=random.Random(0x80802547)
    for _ in range(16):
        corrupted=bytearray(rom)
        idx=rng.randrange(65536)
        corrupted[idx]^=1<<rng.randrange(8)
        assert bit_crc(corrupted,0x25,16)!=0 or bit_crc(corrupted,0x47,16)!=0
    print('PASS: polynomial product, coprimality, x+1 factor, syndrome periods, undetectable four-bit witness')
    print('PASS: selected ROM footer, zero CRC16 residues, zero composite CRC32, correct key firmware sizes')
    print('PASS: 16 independent single-bit corruptions rejected by dual CRC16')

if __name__=='__main__':main()

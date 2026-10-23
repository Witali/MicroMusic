#!/usr/bin/env python3
"""Run reproducible two-pass ROM tests. Python 3 stdlib, no third-party deps.

Each profile checks an executable binary against an assembler, independent
CRC-32 and two CRC-16 software remainders, then executes Intel 8080 machine
code on complete 64 KiB images (positive and negative tests).
"""
from __future__ import annotations
from pathlib import Path
from math import lcm
from random import Random
from crc8080_tools import assemble,crc as crc16,emulate
from dual_crc_rom_tool import PROFILES, combined_poly_low, crc32_slow, build_image, gf2_gcd

ROOT=Path(__file__).resolve().parent
NBIT=65536*8
# p1=0007 for all three; shortest undetectable four-bit bursts were found by
# exhaustive search of 0<u<v<w increasing w (search_4bit_burst.c).
PROPERTIES={
 'dual_crc_0007_0009': {'len':66,'cycles':13049432,'period2':57337,'span':2008,'four':(0,777,1076,2007)},
 'dual_crc_0007_001B': {'len':71,'cycles':15015507,'period2':59055,'span':2656,'four':(0,505,1390,2655)},
 'dual_crc_0007_002D': {'len':72,'cycles':15670867,'period2':65535,'span':1929,'four':(0,95,163,1928)},
}

def flip_bits(image, positions):
    result=bytearray(image)
    for pos in positions:
        assert 0 <= pos < NBIT
        result[pos//8] ^= 1<<(7-pos%8)
    return bytes(result)

def offsets_from_end(exponents, shift=50000):
    return [NBIT-1-shift-k for k in exponents]

def one_profile(name, profile):
    p1,p2=profile; info=PROPERTIES[name]
    source=(ROOT/(name+'.asm')).read_text()
    program,labels=assemble(source)
    assert len(program)==info['len'],(name,len(program))
    assert program==(ROOT/(name+'.bin')).read_bytes()
    image=build_image(program,p1,p2)
    assert image==(ROOT/(name+'_ROM_64KiB.bin')).read_bytes()
    product=combined_poly_low(p1,p2)
    assert gf2_gcd((1<<16)|p1,(1<<16)|p2)==1
    assert lcm(32767,info['period2'])>NBIT
    assert crc32_slow(image,product)==0
    assert crc16(image,p1)==crc16(image,p2)==0
    good=emulate(image,crc_layout='HC')
    assert good['CRC']==0 and good['INTE'] and good['rom_reads']==2*65536 and good['DE']==0
    assert good['cycles']==info['cycles']

    # Rebuild the checksums for a random application payload, preserving code.
    rng = Random(0x8080 + p2)
    random_image = bytearray(image)
    random_image[len(program):-4] = rng.randbytes(65532-len(program))
    random_image[-4:] = crc32_slow(random_image[:-4], product).to_bytes(4,'big')
    assert crc16(random_image,p1)==crc16(random_image,p2)==0
    checked_random = emulate(random_image,crc_layout='HC')
    assert checked_random['INTE'] and checked_random['rom_reads']==131072

    # Each checksum individually has a known double-bit collision; the other
    # checksum must detect that exact same damaged ROM.
    base=100000
    p1_collision=flip_bits(image,[base,base+32767])
    assert crc16(p1_collision,p1)==0 and crc16(p1_collision,p2)!=0
    fail_after_second=emulate(p1_collision,crc_layout='HC')
    assert not fail_after_second['INTE'] and fail_after_second['rom_reads']==131072
    p2_collision=flip_bits(image,[base,base+info['period2']])
    assert crc16(p2_collision,p2)==0 and crc16(p2_collision,p1)!=0
    fail_after_first=emulate(p2_collision,crc_layout='HC')
    assert not fail_after_first['INTE'] and fail_after_first['rom_reads']==65536

    # Single-bit, triple-bit and burst errors always detected.
    for changes in ([12345],[23456,23470,23519],list(range(40000,40032))):
        modified=flip_bits(image,changes)
        assert (crc16(modified,p1),crc16(modified,p2))!=(0,0)

    # Known intentional FOUR-bit collision under both CRCs. This is why the
    # full 64KiB code has minimum Hamming distance 4, NOT 5.
    assert max(info['four'])+1==info['span']
    collision=flip_bits(image,offsets_from_end(info['four']))
    assert crc16(collision,p1)==crc16(collision,p2)==0
    assert crc32_slow(collision,product)==0
    pass_corrupt=emulate(collision,crc_layout='HC')
    assert pass_corrupt['INTE'] and pass_corrupt['rom_reads']==131072

    # Cross-check the bit error syndromes using independent 32-bit recurrence.
    state=1
    for k in range(NBIT):
        assert state!=0
        state=((state<<1)^ (product if state&0x80000000 else 0))&0xFFFFFFFF

    print(f'{name}: code={len(program)} B, footer=4 B, '
          f'cycles={good["cycles"]}, cycles/byte={good["cycles"]/65536:.6f}, '
          f'4bit_min_span={info["span"]}; PASS',flush=True)
    return True

def main():
    for name,profile in PROFILES.items():one_profile(name,profile)
    print('ALL PASSED (with documented, intentional four-bit collisions)')

if __name__=='__main__':main()

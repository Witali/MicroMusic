#!/usr/bin/env python3
"""Reproducible tests for the compact, fast, table-free 8080 CRC-16 ROM checker.

No external Python dependencies. Builds code from .asm, executes instruction-level
simulation, uses an independent bit-by-bit polynomial division implementation,
checks bit-error syndromes, and intentionally demonstrates a CRC-16 collision.

python3 test_crc16_8080_extended.py
"""
from pathlib import Path
import random
import sys
import time

from crc8080_tools import assemble, crc, emulate, patch_rom

ROOT=Path(__file__).resolve().parent
POLY=0x002D
EXPECTED={
    'crc16_8080_fast38': (38,9371702),
    'crc16_8080_fast39': (39,8785713),
    'crc16_8080_fast40': (40,10027062),
    'crc16_8080_fast42': (42,9441078),
}


def msg(s):
    print('  '+s,flush=True)


def byte_step(crc16, octet):
    """Independent direct byte formula; tested against bitwise crc() in tools."""
    t=(octet^(crc16>>8))&255
    u=t^(t<<2)
    return (((crc16&255)<<8)^(u^(u<<3)))&65535


def xtime(value):
    return (((value<<1)^ (POLY if (value&0x8000) else 0))&0xFFFF)


def test_reference_and_syndromes():
    msg('Checking 200,000 random byte transitions against bitwise CRC...')
    rng=random.Random(0x8008)
    for _ in range(200000):
        prev=rng.randrange(65536)
        b=rng.randrange(256)
        ref=prev^(b<<8)
        for j in range(8):ref=xtime(ref)
        assert byte_step(prev,b)==ref

    msg('Enumerating all 65,535 nonzero single-bit syndromes...')
    seen=set(); syndrome=POLY
    for k in range(65535):
        assert syndrome!=0 and syndrome not in seen,(k,syndrome)
        seen.add(syndrome)
        syndrome=xtime(syndrome)
    assert syndrome==POLY

    msg('Checking all 524,288 one-bit positions mathematically...')
    syndrome=POLY
    for bit_from_end in range(65536*8):
        assert syndrome!=0,bit_from_end
        syndrome=xtime(syndrome)

    # Exhibit unavoidable 16-bit CRC limitation on a 65536-byte ROM:
    # 0x2000 bit7 and 0x3FFF bit0 are exactly 65535 transmitted bits apart.
    msg('Checking a known *undetectable* two-bit-error pattern (65535-bit separation)...')
    assert (0x3FFF-0x2000)*8+(7-0)==65535
    single=bytearray(65536)
    single[0x2000]^=0x80
    single[0x3FFF]^=0x01
    assert crc(single)==0,'CRC must miss this deliberate two-bit pattern'

    # Nearby double-bit changes have distinct syndromes (but not all pairs do).
    for _ in range(300):
        p=rng.randrange(65536*8-1000)
        distance=rng.randrange(1,1000)
        assert distance%65535!=0
        err=bytearray(65536)
        for bit in (p,p+distance):
            idx=bit//8; shift=7-bit%8
            err[idx]^=1<<shift
        assert crc(err)!=0


def test_assembled_roms():
    rng=random.Random(0x8080)
    builds={}
    for name,(expected_size,expected_cycles) in EXPECTED.items():
        source=(ROOT/(name+'.asm')).read_text()
        assembled,labels=assemble(source)
        assert len(assembled)==expected_size,(name,len(assembled))
        assert assembled==(ROOT/(name+'.bin')).read_bytes(),name
        assert labels['NEXT']==5,name
        builds[name]=assembled
        # All variants must have 65536 ROM reads including crc footer;
        # use address tracer on the new fastest program.
        rom=patch_rom(assembled)
        assert len(rom)==65536
        assert crc(rom)==0
        assert rom[-2:]==crc(rom[:-2]).to_bytes(2,'big')
        sim=emulate(rom,init=rng.randrange(256),crc_layout='HC',trace_addresses=(name=='crc16_8080_fast39'))
        assert sim['cycles']==expected_cycles,(name,sim['cycles'],expected_cycles)
        assert sim['rom_reads']==65536 and sim['DE']==0 and sim['CRC']==0 and sim['INTE']
        if name=='crc16_8080_fast39':assert sim['unique_rom_reads']==65536
        msg(f'{name}: {expected_size} bytes; {sim["cycles"]:,} T per 64 KiB; {sim["cycles"]/65536:.6f} T/byte; PASS')

    # Test random payloads / different erased-ROM values and random starting registers.
    for name in ('crc16_8080_fast38','crc16_8080_fast39'):
        code=builds[name]
        for mode in ('random','zero'):
            rom=bytearray(patch_rom(code,fill=0 if mode=='zero' else 0xFF))
            if mode=='random':
                rom[len(code):-2]=rng.randbytes(65534-len(code))
                rom[-2:]=crc(rom[:-2]).to_bytes(2,'big')
            assert crc(rom)==0
            good=emulate(rom,init=rng.randrange(256),crc_layout='HC')
            assert good['CRC']==0 and good['INTE'] and good['rom_reads']==65536
            msg(f'{name}, {mode} ROM: PASS')

    # For every mutation, compare CPU-computed CRC with independent reference.
    code=builds['crc16_8080_fast39']
    original=bytearray(patch_rom(code))
    for address, bit in ((0x0050,0x01),(0x00FF,0x80),(0x0100,0x01),
                         (0x7FFF,0x08),(0x8000,0x80),(0xFFFD,0x40),
                         (0xFFFE,0x80),(0xFFFF,0x01)):
        rom=bytearray(original);rom[address]^=bit
        reference=crc(rom)
        assert reference!=0
        result=emulate(rom,init=rng.randrange(256),crc_layout='HC')
        assert result['CRC']==reference and not result['INTE'] and result['rom_reads']==65536,(address,bit,result,reference)
    msg('Eight full-ROM single-bit faults, including CRC footer: FAIL detected correctly')

    # Explicitly check documented limitation in the actual 8080 machine code.
    undetected=bytearray(original)
    undetected[0x2000]^=0x80
    undetected[0x3FFF]^=0x01
    assert crc(undetected)==0
    result=emulate(undetected,init=rng.randrange(256),crc_layout='HC')
    assert result['CRC']==0 and result['INTE']
    msg('Known CRC-16 two-bit collision: checker accepts corrupted ROM (expected limitation)')

    return builds


def main():
    start=time.monotonic()
    print('Intel 8080 CRC-16 (poly 0x002D) extended regression suite')
    test_reference_and_syndromes()
    test_assembled_roms()
    print('PASS: all tests completed in %.2f s' %(time.monotonic()-start))
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print('FAILED: '+repr(exc),file=sys.stderr)
        raise

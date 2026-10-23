#!/usr/bin/env python3
"""Extensive regression tests of Intel 8080 ROM-only CRC32 verifiers.
Run: python3 test_crc32_8080.py
Full CPU simulation executes ~40+ million instructions and takes time.
No third-party Python packages required.
"""
from pathlib import Path
import random,zlib
from i8080_crc32_tools import assemble,crc32,patch_rom,emulate

ROOT=Path(__file__).resolve().parent
PROFILES={
 'crc32_mpeg2_8080':(0x04C11DB7,103,58043088),
 'crc32_mpeg2_8080_compact':(0x04C11DB7,78,68937832),
 'crc32c_msb_8080':(0x1EDC6F41,103,58069132),
 'crc32c_msb_8080_compact':(0x1EDC6F41,78,68937832),
}
N=65536*8

def syndrome_pair_triple_counts(poly):
    """No undetected 2-bit patterns? Exact count of undetected triples.
    Uses linearity and translation invariance to reduce O(N^3) to O(N).
    Every unique non-zero polynomial residue of x^k fits in 32-bit dict.
    """
    cur=1;seen={};triples=0;shapes=0;first=None
    for k in range(N):
        if cur in seen:raise AssertionError('Undetected double bit error within 64 KiB')
        if k:
            j=seen.get(cur ^ 1)
            if j is not None and j>0:
                shapes+=1;triples+=N-k
                if first is None:first=(0,j,k)
        seen[cur]=k
        cur=((cur<<1)^(poly if cur&0x80000000 else 0))&0xFFFFFFFF
    return triples,shapes,first

def mutate(rom,bit_offsets_from_end):
    x=bytearray(rom)
    for p in bit_offsets_from_end:
        addr=65535-p//8; bit=p%8
        assert addr>256 and addr<65532, (p,addr)
        x[addr]^=1<<bit
    return bytes(x)

def check_emu(image,poly,expected_cycles=None,trace=False,success=True):
    result=emulate(image,trace=trace)
    assert result['CRC32']==crc32(image,poly), (result,hex(crc32(image,poly)))
    assert result['INTE']==success and result['SP']==0 and result['rom_reads']==65536
    if trace:assert result['unique_reads']==65536
    if expected_cycles is not None:assert result['cycles']==expected_cycles,(result['cycles'],expected_cycles)
    return result

def main():
    assert crc32(b'123456789')==0x0376E6E7
    assert zlib.crc32(b'123456789')==0xCBF43926
    assert crc32(b'123456789',0x1EDC6F41)==0xFABBF0EA
    print('Reference test vectors: PASS',flush=True)
    for profile,(poly,size,cycles) in PROFILES.items():
        data,_=assemble((ROOT/(profile+'.asm')).read_text())
        assert len(data)==size and data==(ROOT/(profile+'.bin')).read_bytes()
        img=(ROOT/(profile+'_ROM_64KiB.bin')).read_bytes()
        assert img==patch_rom(data,poly=poly)
        assert img[-4:]==crc32(img[:-4],poly).to_bytes(4,'big')
        result=check_emu(img,poly,expected_cycles=cycles,trace=True)
        print(f'{profile}: {size} bytes, {result["cycles"]:,} T, {result["cycles"]/65536:.3f} T/B, all ROM bytes read once: PASS',flush=True)

    # Fault cases, including the CRC trailer, on the faster MPEG2 program.
    poly=0x04C11DB7
    rom=(ROOT/'crc32_mpeg2_8080_ROM_64KiB.bin').read_bytes()
    for addr,mask in ((0x0100,1),(0xFFFF,0x10)):
        damaged=bytearray(rom);damaged[addr]^=mask
        assert crc32(damaged,poly)!=0
        check_emu(bytes(damaged),poly,success=False)
    print('Single-bit corruption in main ROM and CRC footer: caught',flush=True)

    # Exact IEEE 3-bit collision: exponents [0, 41678, 91639].
    # All bits shifted 64 places from end to avoid CRC footer and source code.
    bad3=[64,64+41678,64+91639]
    damaged=mutate(rom,bad3)
    assert crc32(damaged,poly)==0
    check_emu(damaged,poly,success=True)
    print('IEEE three-bit CRC collision: confirmed by CPU emulation',flush=True)

    # Same errors are caught by a CRC-32C polynomial variant.
    poly=0x1EDC6F41
    c32c=(ROOT/'crc32c_msb_8080_ROM_64KiB.bin').read_bytes()
    damaged=mutate(c32c,bad3)
    assert crc32(damaged,poly)!=0
    check_emu(damaged,poly,success=False)
    print('Castagnoli polynomial detects the IEEE three-bit collision',flush=True)

    # Exhaustive analytic testing of all 524288 one-bit and all two-bit errors,
    # plus exact counts of three-bit undetected error patterns.
    for label,poly,expected in (
        ('IEEE',0x04C11DB7,5816260),
        ('Castagnoli',0x1EDC6F41,0),
        ('two CRC16 0007+0009',0x000E003F,0),
        ('two CRC16 0007+001B',0x001C0041,0),
    ):
        triples,shapes,first=syndrome_pair_triple_counts(poly)
        assert triples==expected,(label,triples)
        print(f'{label}: 0 missed single/double bit errors; missed three-bit patterns={triples:,}; anchor patterns={shapes}; first={first}',flush=True)

    rng=random.Random(8080)
    # Independent mathematical random reference for differing content.
    for poly in (0x04C11DB7,0x1EDC6F41):
        blob=bytearray(rng.randbytes(65532));blob.extend(crc32(blob,poly).to_bytes(4,'big'))
        # Reference init FF zero final property
        assert crc32(blob,poly)==0
    print('Random ROM CRC trailer validation: PASS',flush=True)
    print('PASS: All CRC32 tests',flush=True)

if __name__=='__main__':main()

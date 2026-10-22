#!/usr/bin/env python3
"""Build Intel 8080 64-KiB ROM with a four-byte footer for dual CRC16.

Two CRC-16 polynomials: 0x0007 and 0x0021, init=0, MSB-first,
no reflection, xorout=0.  Their product is 0x1002600E7 (degree 32).
Footer is CRC-32 remainder with low 32-bit poly 0x002600E7, big-endian.
No third-party packages.

Usage: python3 patch_rom_0007_0021.py firmware.bin patched_64k.bin
Input may be a short firmware (<65533 B) or exactly 65536 bytes;
existing footer (last four bytes) is always replaced.
"""
from pathlib import Path
import sys
POLY32=0x002600E7
POLYS=(0x0007,0x0021)

def calc_crc(data,poly,bits):
    mask=(1<<bits)-1; top=1<<(bits-1); state=0
    for byte in data:
        state ^= byte << (bits-8)
        for _ in range(8):
            state=((state<<1)^(poly if state&top else 0)) & mask
    return state

def patch(data):
    if len(data)>65536 or 65532<len(data)<65536:
        raise ValueError('Use firmware <=65532 bytes or a complete 65536-byte ROM')
    rom=bytearray([0xFF]*65536)
    rom[:len(data)]=data
    rom[-4:]=calc_crc(rom[:-4],POLY32,32).to_bytes(4,'big')
    assert calc_crc(rom,POLY32,32)==0
    assert all(calc_crc(rom,p,16)==0 for p in POLYS)
    return bytes(rom)

if __name__=='__main__':
    if len(sys.argv)!=3:raise SystemExit(__doc__)
    result=patch(Path(sys.argv[1]).read_bytes())
    Path(sys.argv[2]).write_bytes(result)
    print('ROM bytes:',len(result),'footer:',result[-4:].hex().upper(),'CRC16: OK/OK')

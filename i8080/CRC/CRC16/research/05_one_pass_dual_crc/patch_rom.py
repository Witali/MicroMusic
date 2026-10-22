#!/usr/bin/env python3
"""Construct a 64KiB ROM for the one-pass Intel 8080 dual CRC16 checker.

CRC16/0x0007 + CRC16/0x0009 are combined into generator polynomial
x^32 + 0x000E003F. Entire 64KiB image, including 4 footer bytes,
has zero remainder for both checks.

Usage:
  python3 patch_rom.py dual_crc_0007_0009_onepass.bin rom_onepass.bin
  python3 patch_rom.py existing_unpatched_ROM_64KiB.bin patched_ROM_64KiB.bin
"""
from pathlib import Path
import sys
POLY32=0x000E003F
POLY16=(0x0007,0x0009)

def crc32(data):
    value=0
    for b in data:
        value^=b<<24
        for _ in range(8):
            value=((value<<1)^(POLY32 if value&0x80000000 else 0))&0xFFFFFFFF
    return value

def crc16(data,poly):
    value=0
    for b in data:
        value^=b<<8
        for _ in range(8):
            value=((value<<1)^(poly if value&0x8000 else 0))&0xFFFF
    return value

def patch(image,fill=0xFF):
    if len(image)>65536:raise ValueError('Input larger than 64 KiB')
    if len(image)>65532 and len(image)!=65536:
        raise ValueError('Input overlaps four reserved footer bytes')
    rom=bytearray([fill]*65536)
    rom[:len(image)]=image
    footer=crc32(rom[:-4]).to_bytes(4,'big')
    rom[-4:]=footer
    if crc32(rom)!=0 or any(crc16(rom,poly)!=0 for poly in POLY16):
        raise AssertionError('Incorrect footer')
    return bytes(rom)

if __name__=='__main__':
    if len(sys.argv)!=3:
        raise SystemExit(__doc__)
    inp=Path(sys.argv[1]);out=Path(sys.argv[2])
    data=patch(inp.read_bytes());out.write_bytes(data)
    print(f'{out}: {len(data)} B, footer={data[-4:].hex().upper()}, verified CRCs')

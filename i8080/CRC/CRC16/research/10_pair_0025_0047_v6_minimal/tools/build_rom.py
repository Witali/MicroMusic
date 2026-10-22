#!/usr/bin/env python3
"""Create an Intel 8080 ROM image and Intel HEX with matching CRC16(0x0025,0x0047).

Poly product: (x^16+x^5+x^2+1)(x^16+x^6+x^2+x+1)
  = x^32 + 0x006209BB, non-reflected/MSB-first, init/xorout=0.
The FOUR bytes in addresses FFFCh..FFFFh contain the product-polynomial
remainder, most-significant byte first.  Both 16-bit CRC final residues == 0.

Usage:
    python3 build_rom.py fast_75.bin fast_75_64K.bin --hex fast_75_64K.hex
    python3 build_rom.py app_image_64K.bin patched_64K.bin --fill FF
"""
from __future__ import annotations
import argparse
from pathlib import Path
N=65536
POLY32=0x006209BB
POLYS=(0x0025,0x0047)

def crc16(blob: bytes,poly: int) -> int:
    c=0
    for b in blob:
        c ^= b << 8
        for _ in range(8):
            c=((c<<1)^(poly if c&0x8000 else 0))&0xFFFF
    return c

def crc32(blob: bytes) -> int:
    c=0
    for b in blob:
        c ^= b << 24
        for _ in range(8):
            c=((c<<1)^(POLY32 if c&0x80000000 else 0))&0xFFFFFFFF
    return c

def patch(data:bytes, fill:int=0xFF) -> bytes:
    if len(data)>N or N-4<len(data)<N:
        raise ValueError('Input must be <=65532 bytes or full 65536-byte ROM image')
    rom=bytearray([fill]*N)
    rom[:len(data)]=data
    footer=crc32(rom[:-4]).to_bytes(4,'big')
    rom[-4:]=footer
    assert crc32(rom)==0,'Composite polynomial CRC-32 failed'
    assert all(crc16(rom,p)==0 for p in POLYS),'At least one CRC16 did not reach zero'
    return bytes(rom)

def intel_hex(blob:bytes) -> str:
    records=[]
    for pos in range(0,len(blob),16):
        chunk=blob[pos:pos+16]
        record=bytes((len(chunk),pos>>8&255,pos&255,0))+chunk
        checksum=(-sum(record))&255
        records.append(':'+record.hex().upper()+f'{checksum:02X}')
    records.append(':00000001FF')
    return '\n'.join(records)+'\n'

def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input',type=Path)
    ap.add_argument('output',type=Path)
    ap.add_argument('--fill',default='FF',help='ROM fill byte in HEX, default FF')
    ap.add_argument('--hex',dest='hexpath',type=Path,help='Optional full 64-KiB Intel HEX output')
    args=ap.parse_args()
    f=int(args.fill,16)
    if not 0<=f<=255:ap.error('--fill must be a hexadecimal byte')
    image=patch(args.input.read_bytes(),f)
    args.output.write_bytes(image)
    if args.hexpath:args.hexpath.write_text(intel_hex(image),encoding='ascii')
    print(f'{args.output}: {len(image)} bytes; footer={image[-4:].hex().upper()}; '
          f'CRC25=0 CRC47=0; composite CRC32=0')
if __name__=='__main__':
    main()

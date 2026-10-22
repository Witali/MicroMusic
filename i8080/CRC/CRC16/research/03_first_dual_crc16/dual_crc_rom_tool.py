#!/usr/bin/env python3
"""Build two-pass, table-free Intel 8080 64-KiB ROM image.

Polynomial representation: degree-16 binary polynomials (x^16 + low 16 bits).
Multiply these over GF(2); write the big-endian four-byte CRC-32 remainder
at FFFCh..FFFFh. The ENTIRE 64-KiB image then has zero residue under each
constituent CRC-16 and under their product polynomial.

Usage: python3 dual_crc_rom_tool.py dual_crc_0007_0009.asm
"""
from __future__ import annotations
from pathlib import Path
import sys
from crc8080_tools import assemble, crc as crc16

PROFILES = {"dual_crc_0007_0009": (0x0007, 0x0009),
            "dual_crc_0007_002D": (0x0007, 0x002D),
            "dual_crc_0007_001B": (0x0007, 0x001B)}

def gf2_mul(a: int, b: int) -> int:
    result = 0
    while b:
        if b & 1: result ^= a
        a <<= 1; b >>= 1
    return result

def gf2_rem(a: int, b: int) -> int:
    while a.bit_length() >= b.bit_length():
        a ^= b << (a.bit_length() - b.bit_length())
    return a

def gf2_gcd(a: int, b: int) -> int:
    while b: a, b = b, gf2_rem(a, b)
    return a

def combined_poly_low(p1: int, p2: int) -> int:
    a = (1 << 16) | p1
    b = (1 << 16) | p2
    assert gf2_gcd(a, b) == 1, "Choose coprime polynomials"
    product = gf2_mul(a, b)
    assert product.bit_length() == 33
    return product & 0xFFFFFFFF

def crc32_slow(data: bytes | bytearray, low32: int) -> int:
    crc = 0
    for b in data:
        crc ^= b << 24
        for _ in range(8):
            crc = (((crc << 1) ^ (low32 if crc & 0x80000000 else 0)) & 0xFFFFFFFF)
    return crc

def build_image(binary: bytes, p1: int, p2: int, fill=0xFF) -> bytes:
    if len(binary) > 65532: raise ValueError('Code overlaps 4-byte footer')
    image = bytearray([fill] * 65536)
    image[:len(binary)] = binary
    low32 = combined_poly_low(p1,p2)
    image[-4:] = crc32_slow(image[:-4],low32).to_bytes(4,'big')
    assert crc32_slow(image,low32) == 0
    assert crc16(image,p1) == crc16(image,p2) == 0
    return bytes(image)

def main(argv):
    if len(argv) != 2: raise SystemExit(__doc__)
    p=Path(argv[1]); p1,p2=PROFILES[p.stem]
    binary,_=assemble(p.read_text())
    p.with_suffix('.bin').write_bytes(binary)
    image=build_image(binary,p1,p2)
    p.with_name(p.stem+'_ROM_64KiB.bin').write_bytes(image)
    print(f'program={len(binary)} bytes, CRC footer={image[-4:].hex().upper()}, '
          f'compound poly=0x1{combined_poly_low(p1,p2):08X}, total ROM=65536')

if __name__=='__main__':main(sys.argv)

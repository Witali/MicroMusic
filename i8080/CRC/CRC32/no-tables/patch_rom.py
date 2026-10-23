#!/usr/bin/env python3
"""Recalculate four final ROM bytes for the tableless 8080 CRC-32C checker.

Format: reflected CRC-32C, init=FFFFFFFF, no xorout applied to the raw
remainder, final 4-byte correction field stores raw prefix remainder LE.
Code and data must already be present in input ROM image.
"""
from __future__ import annotations
from argparse import ArgumentParser
from pathlib import Path
from intel8080_tools import crc_raw, crc32c

def patch(payload: bytes) -> bytes:
    if len(payload) not in (24576, 32768):
        raise ValueError('Image must contain exactly 24576 or 32768 bytes.')
    field = crc_raw(payload[:-4]).to_bytes(4,'little')
    output = payload[:-4]+field
    assert crc_raw(output)==0
    return output

if __name__=='__main__':
    p=ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    raw=args.input.read_bytes()
    fixed=patch(raw)
    args.output.write_bytes(fixed)
    print(f'{len(fixed)} bytes, fixup={fixed[-4:].hex(" ")}, raw residue={crc_raw(fixed):08X}, final CRC-32C={crc32c(fixed):08X}')

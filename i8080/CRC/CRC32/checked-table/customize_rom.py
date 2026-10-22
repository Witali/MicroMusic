#!/usr/bin/env python3
"""Safely insert a raw binary payload into the checked Intel 8080 ROM image.

Only the area from 0600h through END-5 is available for user data/code;
0000h..05FFh are reserved for the self-check and its table.
The final four bytes are regenerated automatically (CRC-32C raw residue).

Example:
 python3 customize_rom.py crc32c_8080_checked_32k.bin game.bin 0x0600 game_rom.bin
"""
from __future__ import annotations
import sys
from pathlib import Path
from intel8080_tools import crc_raw, ihex, table_crc32c


def expected_table():
    tbl=table_crc32c()
    return b''.join(bytes((x>>(8*page))&0xff for x in tbl) for page in range(4))


def patch_checksum(rom: bytearray):
    if len(rom) not in (0x6000,0x8000):
        raise ValueError('Only 24 KiB or 32 KiB complete ROM images are supported')
    if bytes(rom[0x100:0x500])!=expected_table():
        raise ValueError('CRC32C table differs from the standard validated table')
    value=crc_raw(rom[:-4]);rom[-4:]=value.to_bytes(4,'little')
    assert crc_raw(rom)==0
    return value


def main():
    if len(sys.argv)!=5:
        raise SystemExit(f'Usage: {sys.argv[0]} base.bin payload.bin offset out.bin')
    base,payload,offset,out=sys.argv[1:]
    offset=int(offset,0)
    rom=bytearray(Path(base).read_bytes())
    data=Path(payload).read_bytes()
    if offset<0x0600 or offset+len(data)>len(rom)-4:
        raise ValueError('Payload MUST fit into reserved-safe range [0600h, ROM_end-4)')
    rom[offset:offset+len(data)]=data
    trailer=patch_checksum(rom)
    Path(out).write_bytes(rom)
    Path(out).with_suffix('.hex').write_text(ihex(rom),encoding='ascii')
    print(f'Created {out} ({len(rom)} bytes), payload={len(data)} @ {offset:04X}h, trailer={trailer:08X}h')
    print('NOTE: this base firmware still executes EI;HLT on success; adding payload does not auto-start it.')

if __name__=='__main__':main()

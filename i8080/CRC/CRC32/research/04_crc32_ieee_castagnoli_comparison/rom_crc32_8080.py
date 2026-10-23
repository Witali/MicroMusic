#!/usr/bin/env python3
"""Patch the last 4 bytes of 64KiB Intel 8080 ROM with an MSB-first CRC-32.

Examples:
  python3 rom_crc32_8080.py patch firmware.bin -o verified_rom.bin --poly ieee
  python3 rom_crc32_8080.py assemble crc32_mpeg2_8080.asm -o check.bin
  python3 rom_crc32_8080.py demo crc32_mpeg2_8080.asm -o demo_rom.bin --poly ieee
  python3 rom_crc32_8080.py check demo_rom.bin --poly ieee

'ieee' = standard CRC-32/MPEG-2 params (MSB-first, init FFFFFFFF, xorout0).
'castagnoli-msb' = non-standard MSB-first *variant* using 0x1EDC6F41,
                    same error-detection polynomial as CRC-32C but not CRC-32C wire format.
"""
from pathlib import Path
import argparse
from i8080_crc32_tools import assemble,crc32

P={'ieee':0x04C11DB7,'castagnoli-msb':0x1EDC6F41}

def make_rom(data,poly=0x04C11DB7):
    if len(data)>65536:raise ValueError('Image exceeds 65536 bytes')
    rom=bytearray(data.ljust(65536,b'\xff'))
    rom[-4:]=crc32(rom[:-4],poly).to_bytes(4,'big')
    assert crc32(rom,poly)==0
    return bytes(rom)

def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command',choices=['assemble','patch','demo','check'])
    ap.add_argument('file',type=Path)
    ap.add_argument('-o','--output',type=Path)
    ap.add_argument('--poly',choices=P.keys(),default='ieee')
    a=ap.parse_args();poly=P[a.poly]
    if a.command in ('assemble','demo'):
        data,_=assemble(a.file.read_text(encoding='utf-8'))
    else:data=a.file.read_bytes()
    if a.command=='check':
        if len(data)!=65536:raise SystemExit('check requires a 65536-byte ROM image')
        rem=crc32(data,poly)
        print('CRC32 remainder = 0x%08X, valid = %s'%(rem,rem==0))
        raise SystemExit(0 if rem==0 else 1)
    if a.command=='assemble':
        out=a.output or a.file.with_suffix('.bin');out.write_bytes(data)
        print('Code:',len(data),'bytes; saved',out)
    else:
        out=a.output or a.file.with_name(a.file.stem+'_patched.bin')
        rom=make_rom(data,poly)
        out.write_bytes(rom)
        print('ROM:',len(rom),'bytes; polynomial=0x%08X; footer=%s; saved %s'%(poly,rom[-4:].hex().upper(),out))
if __name__=='__main__':main()

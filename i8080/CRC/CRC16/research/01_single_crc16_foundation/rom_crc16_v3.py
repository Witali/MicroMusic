#!/usr/bin/env python3
"""Build, patch and verify 64 KiB Intel 8080 CRC-16 ROMs.

Use --profile matching the assembler executable. Wrong profile is rejected
rather than silently creating a ROM the CPU would reject.

  python3 rom_crc16_v3.py build strong rom.bin
  python3 rom_crc16_v3.py build fastest rom.bin
  python3 rom_crc16_v3.py patch strongest.bin my_full_rom.bin --profile strong
  python3 rom_crc16_v3.py check rom.bin --profile strong

Profiles: strong (0x002D, primitive, 39B code), fastest (0x0009,
reducible, 33B), balanced (0x001B, 38B), speed (0x000F, 37B).
No third-party modules.
"""
from pathlib import Path
import argparse
from crc8080_tools import assemble,crc

ROOT=Path(__file__).resolve().parent
PROFILES={
    'strong': ('crc16_8080_fast39',0x002D),
    'fastest': ('crc16_8080_fast33z_poly0009',0x0009),
    'balanced': ('crc16_8080_fast38_poly001B',0x001B),
    'speed': ('crc16_8080_fast37_poly000F',0x000F),
}

def profile_data(name):
    src_name,poly=PROFILES[name]
    code,_=assemble((ROOT/(src_name+'.asm')).read_text())
    return code,poly

def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    sub=ap.add_subparsers(dest='command',required=True)
    for action in ('build','patch','check'):
        p=sub.add_parser(action)
        p.add_argument('file',type=Path,help='output ROM for build; input ROM for patch/check')
        if action=='patch':p.add_argument('output',type=Path)
        p.add_argument('--profile',choices=tuple(PROFILES),default='strong')
        if action in ('build','patch'):p.add_argument('--fill',type=lambda s:int(s,0),default=0xff)
    args=ap.parse_args()
    code,poly=profile_data(args.profile)
    if args.command=='check':
        rom=args.file.read_bytes()
        if len(rom)!=65536:ap.error('ROM must have exactly 65536 bytes')
        if not rom.startswith(code):ap.error('Wrong ROM code for selected profile')
        value=crc(rom,poly)
        print(f'CRC=0x{value:04X}: {"PASS" if value==0 else "FAIL"} ({args.profile}, poly=0x{poly:04X})')
        raise SystemExit(0 if value==0 else 1)
    if not 0<=args.fill<=255:ap.error('Fill byte must be in 0..255')
    if args.command=='build':
        rom=bytearray([args.fill]*65536)
        rom[:len(code)]=code
        dest=args.file
    else:
        source=args.file.read_bytes()
        if not source.startswith(code):ap.error('Source does not start with the selected code; check --profile')
        if len(source)>65536 or len(source)==65535:ap.error('Invalid source length')
        if len(source)==65536:source=source[:-2]
        rom=bytearray([args.fill]*65536)
        rom[:len(source)]=source
        dest=args.output
    rom[-2:]=crc(rom[:-2],poly).to_bytes(2,'big')
    assert crc(rom,poly)==0
    dest.write_bytes(rom)
    print(f'{dest}: 65536 bytes; {args.profile}; code={len(code)}; CRC footer={rom[-2:].hex().upper()}')

if __name__=='__main__':main()

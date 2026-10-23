#!/usr/bin/env python3
"""Build, patch and check Intel 8080 CRC-16 ROMs, including poly=0x0007.
Run from the project root: python3 tools/rom_tool.py build odd-fast myrom.bin
"""
from pathlib import Path
import argparse
from crc8080_tools import assemble,crc,patch_rom

ROOT=Path(__file__).resolve().parents[1]
PROFILES={
    'odd-fast':('poly0007_36B',0x0007),
    'fastest':('poly0009_33B',0x0009),
    'balanced':('poly001B_38B',0x001B),
    'primitive':('poly002D_39B',0x002D),
}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('build','patch','check'))
    parser.add_argument('profile',choices=tuple(PROFILES))
    parser.add_argument('input_or_output',type=Path)
    parser.add_argument('output',nargs='?',type=Path)
    parser.add_argument('--fill',type=lambda s:int(s,0),default=0xff)
    args=parser.parse_args()
    name,poly=PROFILES[args.profile]
    code,labels=assemble((ROOT/'src'/f'{name}.asm').read_text())
    if args.command=='check':
        image=args.input_or_output.read_bytes()
        if len(image)!=65536:parser.error('ROM must contain exactly 65536 bytes')
        if not image.startswith(code):parser.error('ROM code does not match selected profile')
        remainder=crc(image,poly)
        print(f'{args.input_or_output}: {args.profile} CRC=0x{remainder:04X} '+('PASS' if remainder==0 else 'FAIL'))
        raise SystemExit(0 if remainder==0 else 1)
    if not 0<=args.fill<=255:parser.error('--fill must be 0..255')
    if args.command=='build':
        if args.output:parser.error('build takes one output filename')
        image=patch_rom(code,poly=poly,fill=args.fill)
        out=args.input_or_output
    else:
        if not args.output:parser.error('patch needs input ROM and output ROM')
        raw=args.input_or_output.read_bytes()
        if not raw.startswith(code):parser.error('Input ROM does not start with selected code')
        if len(raw)>65536:parser.error('Input too large')
        if len(raw)==65536:raw=raw[:-2]
        base=bytearray([args.fill]*65536)
        base[:len(raw)]=raw
        base[-2:]=crc(base[:-2],poly).to_bytes(2,'big')
        image=bytes(base)
        out=args.output
    assert len(image)==65536 and crc(image,poly)==0
    out.write_bytes(image)
    print(f'{out}: 65536 bytes {args.profile}; CRC={image[-2:].hex().upper()} PASS')

if __name__=='__main__':main()

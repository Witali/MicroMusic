#!/usr/bin/env python3
"""Build a C quarter-step mailbox with untouched Xiph interpolation as oracle."""
import argparse
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc',required=True)
    args=parser.parse_args()
    out=build.ROOT/'build/quarter-unit';out.mkdir(parents=True,exist_ok=True)
    _,source=build.prepare('reference')
    build.run([args.avr_gcc,'-std=c11','-mmcu=atmega328p','-Os','-flto',
        '-mcall-prologues','-mrelax','-fwrapv','-fno-strict-aliasing','-Wno-pointer-to-int-cast',
        '-ffunction-sections','-fdata-sections',*['-D'+d for d in build.DEFINES],
        '-I'+str(source/'include'),'-I'+str(source/'libspeex'),'-I'+str(build.ROOT/'src'),
        source/'libspeex/lsp.c',build.ROOT/'tests/avr_interpolate.c',
        '-Wl,--gc-sections','-o',out/'quarter.elf'])
    prefix=str(Path(args.avr_gcc).with_name('avr-'))
    extension='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+extension,'-O','binary','-R','.eeprom',out/'quarter.elf',out/'quarter.bin'])
    symbols=subprocess.check_output([prefix+'nm'+extension,'-n',out/'quarter.elf'],text=True)
    (out/'symbols.txt').write_text(symbols,encoding='utf-8')

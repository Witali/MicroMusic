#!/usr/bin/env python3
"""Build independent native/AVR tests of the validated NB3 packet map."""
import argparse
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc')
    parser.add_argument('--avr-gcc')
    args=parser.parse_args()
    if not (args.cc or args.avr_gcc):parser.error('Choose --cc and/or --avr-gcc')
    out=build.ROOT/'build/subframe-unit';out.mkdir(parents=True,exist_ok=True)
    if args.cc:
        exe=out/'native.exe'
        build.run([args.cc,'-std=c11','-O2','-fwrapv','-fno-strict-aliasing',
            '-I'+str(build.ROOT/'src'),build.ROOT/'tests/subframe.c','-o',exe])
        result=subprocess.check_output([exe],text=True);print(result,end='')
        (out/'native.log').write_text(result,encoding='utf-8')
    if args.avr_gcc:
        build.run([args.avr_gcc,'-std=c11','-mmcu=atmega328p','-Os','-flto',
            '-mcall-prologues','-mrelax','-fwrapv','-fno-strict-aliasing',
            '-DSPEEX_NB3_ENABLE_ASM=0','-I'+str(build.ROOT/'src'),'-I'+str(build.VENDOR/'include'),
            build.ROOT/'tests/avr_subframe.c',build.ROOT/'src/bits.c','-o',out/'subframe.elf'])
        prefix=str(Path(args.avr_gcc).with_name('avr-'))
        ext='.exe' if args.avr_gcc.endswith('.exe') else ''
        build.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',out/'subframe.elf',out/'subframe.bin'])
        symbols=subprocess.check_output([prefix+'nm'+ext,'-n',out/'subframe.elf'],text=True)
        (out/'symbols.txt').write_text(symbols,encoding='utf-8')

#!/usr/bin/env python3
"""Build a small ATmega328P mailbox for exact arithmetic/ABI tests."""
import argparse
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc',required=True)
    args=parser.parse_args()
    output=build.ROOT/'build/math'
    output.mkdir(parents=True,exist_ok=True)
    build.run([args.avr_gcc,'-mmcu=atmega328p','-O3','-flto','-fwrapv',
               '-DSPEEX_NB3_ENABLE_ASM=1',
               '-I'+str(build.ROOT/'src'),build.ROOT/'tests/avr_math.c',build.ROOT/'src/q14.S',
               '-o',output/'math.elf'])
    prefix=str(Path(args.avr_gcc).with_name('avr-'))
    extension='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+extension,'-O','binary','-R','.eeprom',output/'math.elf',output/'math.bin'])
    symbols=subprocess.check_output([prefix+'nm'+extension,'-n',output/'math.elf'],text=True)
    (output/'symbols.txt').write_text(symbols,encoding='utf-8')
if __name__=='__main__':main()

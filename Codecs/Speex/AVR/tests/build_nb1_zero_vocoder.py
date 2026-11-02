#!/usr/bin/env python3
"""Build isolated general/zero-vector controls and explicit C/ASM selection."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--avr-gcc',required=True);args=parser.parse_args()
    prefix=str(Path(args.avr_gcc).with_name('avr-'));ext='.exe' if args.avr_gcc.endswith('.exe') else ''
    for backend in ['asm','c']:
        out=ROOT/'build/zero-vocoder-unit'/backend;out.mkdir(parents=True,exist_ok=True)
        subprocess.run([args.avr_gcc,'-std=c11','-Werror=implicit-function-declaration','-Os','-flto','-fwrapv','-fno-strict-aliasing',
            '-mmcu=atmega328p','-mcall-prologues','-mrelax','-DSPEEX_NB3_ENABLE_ASM='+str(int(backend=='asm')),
            '-DSPEEX_ENABLE_NB1=1','-DSPEEX_ENABLE_WB1=1','-I'+str(ROOT/'src'),
            ROOT/'tests/avr_nb1_zero_vocoder.c',ROOT/'src/nb1_vocoder.c',ROOT/'src/nb1_vocoder.S',
            '-o',out/'unit.elf'],check=True)
        subprocess.run([prefix+'objcopy'+ext,'-O','binary',out/'unit.elf',out/'unit.bin'],check=True)
        (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',out/'unit.elf'],text=True))
        (out/'input.json').write_bytes((json.dumps(dict(backend=backend,binarySha256=hashlib.sha256((out/'unit.bin').read_bytes()).hexdigest(),
            scope='Isolated C/ASM vector primitives; full C decoder is not executed or timed'),indent=2)+'\n').encode())


if __name__=='__main__':main()

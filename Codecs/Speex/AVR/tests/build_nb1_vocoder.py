#!/usr/bin/env python3
"""Build isolated NB1 vector arithmetic C/ASM mailbox, not a C decoder."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True);args=p.parse_args()
    out=ROOT/'build/vocoder-unit';out.mkdir(parents=True,exist_ok=True)
    subprocess.run([args.avr_gcc,'-std=c11','-Os','-flto','-fwrapv','-fno-strict-aliasing',
        '-mmcu=atmega328p','-mcall-prologues','-mrelax','-DSPEEX_NB3_ENABLE_ASM=1',
        '-DSPEEX_ENABLE_NB1=1','-DSPEEX_ENABLE_WB1=1','-I'+str(ROOT/'src'),
        ROOT/'tests/avr_nb1_vocoder.c',ROOT/'src/nb1_vocoder.c',ROOT/'src/nb1_vocoder.S',
        '-o',out/'unit.elf'],check=True)
    prefix=str(Path(args.avr_gcc).with_name('avr-'));ext='.exe' if args.avr_gcc.endswith('.exe') else ''
    subprocess.run([prefix+'objcopy'+ext,'-O','binary',out/'unit.elf',out/'unit.bin'],check=True)
    (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',out/'unit.elf'],text=True))
    (out/'input.json').write_text(json.dumps(dict(backend='asm',
        binarySha256=hashlib.sha256((out/'unit.bin').read_bytes()).hexdigest()),indent=2)+'\n')


if __name__=='__main__':main()

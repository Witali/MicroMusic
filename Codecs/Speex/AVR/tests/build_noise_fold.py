#!/usr/bin/env python3
"""Build old/vector/new-table ASM and explicitly callable C scalar paths."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_wb


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True);args=p.parse_args()
    source=build_wb.prepare();out=ROOT/'build/noise-fold-unit';out.mkdir(parents=True,exist_ok=True)
    subprocess.run([args.avr_gcc,*build_wb.flags(source,'asm',True,7),'-mmcu=atmega328p',
        '-Os','-flto','-mcall-prologues','-mrelax','-ffunction-sections','-fdata-sections',
        ROOT/'tests/avr_noise_fold.c',ROOT/'src/wb_fold.c',ROOT/'src/wb_fold.S',
        '-Wl,--gc-sections','-o',out/'unit.elf'],check=True)
    prefix=str(Path(args.avr_gcc).with_name('avr-'));ext='.exe' if args.avr_gcc.endswith('.exe') else ''
    subprocess.run([prefix+'objcopy'+ext,'-O','binary',out/'unit.elf',out/'unit.bin'],check=True)
    (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',out/'unit.elf'],text=True))
    (out/'input.json').write_bytes((json.dumps(dict(binarySha256=hashlib.sha256((out/'unit.bin').read_bytes()).hexdigest(),
        scope='Arithmetic/table lookup only; C decoder is not executed'),indent=2)+'\n').encode())


if __name__=='__main__':main()

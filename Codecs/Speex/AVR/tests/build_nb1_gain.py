#!/usr/bin/env python3
"""Build isolated original/coefficient/factored/lookup C gain controls on AVR."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True);args=p.parse_args()
    prefix=str(Path(args.avr_gcc).with_name('avr-'));ext='.exe' if args.avr_gcc.endswith('.exe') else ''
    for backend in ['asm','c']:
        out=ROOT/'build/nb1-gain-unit'/backend;out.mkdir(parents=True,exist_ok=True)
        subprocess.run([args.avr_gcc,'-std=c11','-fwrapv','-fno-strict-aliasing','-mmcu=atmega328p','-Os','-flto',
            '-mcall-prologues','-mrelax','-ffunction-sections','-fdata-sections','-I'+str(ROOT/'src'),
            '-DSPEEX_NB3_ENABLE_ASM='+str(int(backend=='asm')),ROOT/'tests/avr_nb1_gain.c',
            '-Wl,--gc-sections','-o',out/'unit.elf'],check=True)
        subprocess.run([prefix+'objcopy'+ext,'-O','binary',out/'unit.elf',out/'unit.bin'],check=True)
        (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',out/'unit.elf'],text=True))
        (out/'input.json').write_bytes((json.dumps(dict(backend=backend,binarySha256=hashlib.sha256((out/'unit.bin').read_bytes()).hexdigest(),
            scope='Isolated C scalar control arithmetic; C decoder not executed or timed'),indent=2)+'\n').encode())
    assert (ROOT/'build/nb1-gain-unit/asm/unit.bin').read_bytes()==(ROOT/'build/nb1-gain-unit/c/unit.bin').read_bytes()


if __name__=='__main__':main()

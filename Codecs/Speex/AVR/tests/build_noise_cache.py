#!/usr/bin/env python3
"""Build the actual WB decoder with cache-address observation metadata."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--avr-gcc',required=True)
    args=p.parse_args()
    out=ROOT/'build/noise-cache-unit';out.mkdir(parents=True,exist_ok=True)
    source=build_wb.prepare();exe=out/'cache.elf'
    build.run([args.avr_gcc,*build_wb.flags(source,'asm',True,7),'-Os','-flto','-mmcu=atmega328p',
        '-mcall-prologues','-mrelax','-ffunction-sections','-fdata-sections',*build_wb.sources(source),
        *[ROOT/'src'/s for s in build.ASM_SOURCES+build_wb.ASM_SOURCES],ROOT/'tests/avr_noise_cache.c',
        '-Wl,--gc-sections','-o',exe])
    prefix=str(Path(args.avr_gcc).with_name('avr-'));ext='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',exe,out/'cache.bin'])
    (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',exe],text=True))
    (out/'input.json').write_bytes((json.dumps(dict(backend='asm',
        binarySha256=hashlib.sha256((out/'cache.bin').read_bytes()).hexdigest()),indent=2)+'\n').encode())


if __name__=='__main__':main()

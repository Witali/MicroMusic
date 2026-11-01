#!/usr/bin/env python3
"""Build target ASM mailboxes that exercise variable-size public APIs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True)
    p.add_argument('--out',type=Path,default=ROOT/'build/low-api');args=p.parse_args()
    source=build_wb.prepare()
    for wb in [0,1]:
        out=(args.out/('wb' if wb else 'nb')).resolve();out.mkdir(parents=True,exist_ok=True)
        exe=out/'api.elf';units=build_wb.sources(source)
        build.run([args.avr_gcc,*build_wb.flags(source,'asm',True,7),'-mmcu=atmega328p',
            '-Os','-flto','-mcall-prologues','-mrelax','-ffunction-sections','-fdata-sections',
            '-DSPEEX_TEST_WIDEBAND='+str(wb),*units,*[ROOT/'src'/s for s in build.ASM_SOURCES+build_wb.ASM_SOURCES],
            ROOT/'tests/avr_low_api.c','-Wl,--gc-sections','-o',exe])
        prefix=str(Path(args.avr_gcc).with_name('avr-'));ext='.exe' if args.avr_gcc.endswith('.exe') else ''
        build.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',exe,out/'api.bin'])
        (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',exe],text=True))
        (out/'backend.json').write_bytes((json.dumps(dict(backend='asm',wideband=bool(wb),
            binarySha256=hashlib.sha256((out/'api.bin').read_bytes()).hexdigest()),indent=2)+'\n').encode())

if __name__=='__main__':main()

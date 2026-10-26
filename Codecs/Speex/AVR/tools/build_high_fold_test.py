#!/usr/bin/env python3
"""Build the NB4/HB1 fused kernel with its independently callable pure C path."""
import argparse
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build,build_wb
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True);p.add_argument('--out',type=Path);args=p.parse_args()
    source=build_wb.prepare();out=args.out or build.ROOT/'build/high-fold-unit';out.mkdir(parents=True,exist_ok=True)
    exe=out/'unit.elf';build.run([args.avr_gcc,*build_wb.flags(source,'asm'),'-Os','-flto','-mmcu=atmega328p','-mcall-prologues','-mrelax',
        '-ffunction-sections','-fdata-sections',build.ROOT/'src/wb_fold.c',build.ROOT/'src/wb_fold.S',
        source/'libspeex/exc_10_32_table.c',source/'libspeex/exc_8_128_table.c',build.ROOT/'tests/avr_high_fold.c','-Wl,--gc-sections','-o',exe])
    prefix=str(Path(args.avr_gcc).with_name('avr-'));ext='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',exe,out/'unit.bin'])
    (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',exe],text=True),encoding='utf-8')
if __name__=='__main__':main()

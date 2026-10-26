#!/usr/bin/env python3
"""Build the bounded NB4 packet reader independently of decoder arithmetic."""
import argparse
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True);p.add_argument('--out',type=Path);a=p.parse_args()
    out=a.out or build.ROOT/'build/nb4-fields-unit';out.mkdir(parents=True,exist_ok=True);exe=out/'unit.elf'
    build.run([a.avr_gcc,'-std=c11','-Os','-flto','-mmcu=atmega328p','-mcall-prologues','-mrelax','-fwrapv','-fno-strict-aliasing',
        '-DSPEEX_NB3_ENABLE_ASM=0','-I'+str(build.ROOT/'src'),build.ROOT/'tests/avr_nb4_fields.c','-o',exe])
    prefix=str(Path(a.avr_gcc).with_name('avr-'));ext='.exe' if a.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',exe,out/'unit.bin'])
    (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',exe],text=True),encoding='utf-8')
if __name__=='__main__':main()

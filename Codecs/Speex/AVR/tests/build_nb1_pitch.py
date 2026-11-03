#!/usr/bin/env python3
"""Build isolated exact pitch-root recipes and explicit arithmetic selection."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import apply_profile
import build


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--avr-gcc',required=True)
    args=p.parse_args()
    _,source=build.prepare('nb1-pitch-source')
    apply_profile.apply(source)
    prefix=str(Path(args.avr_gcc).with_name('avr-'))
    ext='.exe' if args.avr_gcc.endswith('.exe') else ''
    compiler_version=subprocess.check_output([args.avr_gcc,'--version'],text=True).splitlines()[0]
    for backend in ['asm','c']:
        for table in [1,0]:
            out=ROOT/'build/nb1-pitch-unit'/f'{backend}-table{table}'
            out.mkdir(parents=True,exist_ok=True)
            subprocess.run([args.avr_gcc,'-std=c11','-fwrapv','-fno-strict-aliasing','-mmcu=atmega328p',
                '-Os','-flto','-fno-ipa-icf','-mcall-prologues','-mrelax','-ffunction-sections','-fdata-sections',
                '-DSPEEX_AVR_FAST_MUL','-DSPEEX_NB3_ENABLE_ASM='+str(int(backend=='asm')),
                '-DSPEEX_NB1_PITCH_ROOT_TABLE='+str(table),'-DFIXED_POINT',
                '-I'+str(source/'include'),'-I'+str(source/'libspeex'),'-I'+str(ROOT/'src'),
                ROOT/'tests/avr_nb1_pitch.c','-Wl,--gc-sections','-o',out/'unit.elf'],check=True)
            subprocess.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',out/'unit.elf',out/'unit.bin'],check=True)
            (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',out/'unit.elf'],text=True),encoding='utf-8')
            (out/'sizes.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-S','--size-sort',out/'unit.elf'],text=True),encoding='utf-8')
            (out/'input.json').write_text(json.dumps(dict(backend=backend,tableEnabled=bool(table),
                compilerVersion=compiler_version,
                binarySha256=hashlib.sha256((out/'unit.bin').read_bytes()).hexdigest(),
                scope='Isolated scalar arithmetic; no C decoder execution or timing'),indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()

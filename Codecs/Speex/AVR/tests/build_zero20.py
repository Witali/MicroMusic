#!/usr/bin/env python3
"""Build exact zero-vector count0..20 C/ASM arithmetic and fixed-ten control."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_wb


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True)
    p.add_argument('--baseline-root',type=Path);args=p.parse_args()
    source=build_wb.prepare();out=ROOT/'build/zero20-unit';out.mkdir(parents=True,exist_ok=True)
    subprocess.run([args.avr_gcc,*build_wb.flags(source,'asm',True,7),'-mmcu=atmega328p',
        '-Os','-flto','-mcall-prologues','-mrelax','-ffunction-sections','-fdata-sections',
        ROOT/'tests/avr_zero20.c',ROOT/'src/innovation.S',source/'libspeex/exc_20_32_table.c',
        source/'libspeex/exc_10_32_table.c','-Wl,--gc-sections','-o',out/'unit.elf'],check=True)
    prefix=str(Path(args.avr_gcc).with_name('avr-'));ext='.exe' if args.avr_gcc.endswith('.exe') else ''
    subprocess.run([prefix+'objcopy'+ext,'-O','binary',out/'unit.elf',out/'unit.bin'],check=True)
    (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',out/'unit.elf'],text=True))
    metadata=dict(binarySha256=hashlib.sha256((out/'unit.bin').read_bytes()).hexdigest(),
        scope='Isolated scalar/vector C/ASM arithmetic; C decoder not executed or timed')
    if args.baseline_root:
        subprocess.run([args.avr_gcc,*build_wb.flags(source,'asm',True,7),'-mmcu=atmega328p',
            '-Os','-flto','-mcall-prologues','-mrelax','-ffunction-sections','-fdata-sections',
            ROOT/'tests/avr_zero20.c',args.baseline_root/'src/innovation.S',source/'libspeex/exc_20_32_table.c',
            source/'libspeex/exc_10_32_table.c','-Wl,--gc-sections','-o',out/'before.elf'],check=True)
        subprocess.run([prefix+'objcopy'+ext,'-O','binary',out/'before.elf',out/'before.bin'],check=True)
        assert (out/'before.bin').read_bytes()==(out/'unit.bin').read_bytes(),'Arithmetic firmware must remain byte-identical'
        metadata.update(beforeBinarySha256=hashlib.sha256((out/'before.bin').read_bytes()).hexdigest(),arithmeticFirmwareUnchanged=True)
    (out/'input.json').write_bytes((json.dumps(metadata,indent=2)+'\n').encode())


if __name__=='__main__':main()

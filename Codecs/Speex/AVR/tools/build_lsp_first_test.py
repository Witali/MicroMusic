#!/usr/bin/env python3
"""Build independent two-root arithmetic, flag, memory and ABI tests."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc');p.add_argument('--avr-gcc')
    p.add_argument('--backend',choices=['asm','c'],default='c');p.add_argument('--out',type=Path);args=p.parse_args()
    if not(args.cc or args.avr_gcc):p.error('Choose --cc and/or --avr-gcc')
    out=args.out or build.ROOT/('build/first-unit-'+args.backend);out.mkdir(parents=True,exist_ok=True)
    common=['-std=c11','-fwrapv','-fno-strict-aliasing','-ffunction-sections','-fdata-sections','-I'+str(build.ROOT/'src')]
    if args.cc:
        exe=out/'native.exe';build.run([args.cc,*common,'-O2','-DSPEEX_NB3_ENABLE_ASM=0',build.ROOT/'tests/lsp_first.c','-o',exe])
        log=subprocess.check_output([exe],text=True);(out/'native.log').write_text(log);print(log,end='')
    if args.avr_gcc:
        exe=out/'first.elf';backend=args.backend
        build.run([args.avr_gcc,*common,'-Os','-flto','-mmcu=atmega328p','-mcall-prologues','-mrelax',
            '-DSPEEX_NB3_ENABLE_ASM='+str(int(backend=='asm')),build.ROOT/'tests/avr_lsp_first.c',
            *([build.ROOT/'src/lsp_first.S'] if backend=='asm' else []),'-Wl,--gc-sections','-o',exe])
        prefix=str(Path(args.avr_gcc).with_name('avr-'));ext='.exe' if args.avr_gcc.endswith('.exe') else ''
        build.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',exe,out/'first.bin'])
        (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',exe],text=True))
        headers=Path(args.avr_gcc).resolve().parents[1]/'avr/include/avr'
        report={'compiler':'AVR GCC 7.3.0','target':'atmega328p','headers':
            {n:hashlib.sha256((headers/n).read_bytes()).hexdigest() for n in ['io.h','iom328p.h']},
            'sregAddressExpression':'_SFR_MEM_ADDR(SREG), from avr/io.h'}
        (out/'device-headers.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Build an AVR QMF-only benchmark and untouched upstream PC QMF oracle."""
import argparse
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc',required=True)
    parser.add_argument('--avr-gcc',required=True)
    args=parser.parse_args()
    output=build.ROOT/'build/qmf'
    output.mkdir(parents=True,exist_ok=True)
    source=build.ROOT/'build/rates-reference/source'
    sources=build.SOURCES+['modes_wb','sb_celp','high_lsp_tables','hexc_table','hexc_10_32_table']
    definitions=[d for d in build.DEFINES if d!='DISABLE_WIDEBAND']
    build.run([args.cc,'-O2','-fwrapv','-fno-strict-aliasing','-Wno-pointer-to-int-cast',
               '-D_CRT_SECURE_NO_WARNINGS',*['-D'+d for d in definitions],
               '-I'+str(source/'include'),'-I'+str(source/'libspeex'),'-I'+str(build.ROOT/'src'),
               *[source/'libspeex'/(s+'.c') for s in sources],build.ROOT/'tests/qmf_bench.c',
               '-o',output/'oracle.exe'])
    build.run([args.avr_gcc,'-mmcu=atmega328p','-O3','-flto','-fwrapv',
               '-I'+str(build.ROOT/'src'),build.ROOT/'src/qmf_memory.c',build.ROOT/'tests/qmf_bench.c',
               '-Wl,-Map='+str(output/'qmf.map'),'-o',output/'qmf.elf'])
    prefix=str(Path(args.avr_gcc).with_name('avr-'))
    extension='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+extension,'-O','binary','-R','.eeprom',output/'qmf.elf',output/'qmf.bin'])
    symbols=subprocess.check_output([prefix+'nm'+extension,'-n',output/'qmf.elf'],text=True)
    (output/'symbols.txt').write_text(symbols,encoding='utf-8')
    build.run([prefix+'size'+extension,'-C','--mcu=atmega328p',output/'qmf.elf'])

if __name__=='__main__':main()

#!/usr/bin/env python3
"""Compile independent Xiph prefix oracles and the C packet decoder test."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc');parser.add_argument('--avr-gcc')
    args=parser.parse_args()
    if not (args.cc or args.avr_gcc):parser.error('Choose --cc and/or --avr-gcc')
    build.verify_sources()
    out=build.ROOT/'build/prefix-unit';out.mkdir(parents=True,exist_ok=True)
    reference=out/'reference';shutil.copytree(build.VENDOR,reference,dirs_exist_ok=True)
    (reference/'include/speex/speex_config_types.h').write_text('#include <stdint.h>\n'
        'typedef int16_t spx_int16_t;typedef uint16_t spx_uint16_t;\n'
        'typedef int32_t spx_int32_t;typedef uint32_t spx_uint32_t;\n')
    tables=(build.VENDOR/'libspeex/lsp_tables_nb.c').read_text()
    text,count=re.subn(r'(const signed char \w+\[\d+\])\s*=',r'\1 AVR_TABLE =',tables)
    assert count==5
    (out/'production-tables.c').write_text('#include "avr_tables.h"\n'+text)
    aliases=['-Dlsp_unquant_lbr=reference_lsp_unquant_lbr',
        '-Dspeex_bits_unpack_unsigned=reference_bits_unpack_unsigned']
    aliases+=['-D'+n+'=reference_'+n for n in ['cdbk_nb','cdbk_nb_low1','cdbk_nb_low2','cdbk_nb_high1','cdbk_nb_high2']]
    for kind,compiler in [('native',args.cc),('avr',args.avr_gcc)]:
        if not compiler:continue
        flags=['-std=c11','-O2','-fwrapv','-fno-strict-aliasing','-ffunction-sections','-fdata-sections',
            '-DSPEEX_NB3_ENABLE_ASM=0',*['-D'+d for d in build.DEFINES],
            '-I'+str(reference/'include'),'-I'+str(reference/'libspeex'),'-I'+str(build.ROOT/'src')]
        if kind=='avr':flags+=['-mmcu=atmega328p','-mcall-prologues','-mrelax']
        objects=[]
        for name in ['quant_lsp','bits','lsp_tables_nb']:
            obj=out/(kind+'-reference-'+name+'.o');objects.append(obj)
            build.run([compiler,*flags,*aliases,'-c',reference/'libspeex'/(name+'.c'),'-o',obj])
        main=build.ROOT/'tests'/('prefix.c' if kind=='native' else 'avr_prefix.c')
        executable=out/('native.exe' if kind=='native' else 'prefix.elf')
        build.run([compiler,*flags,*objects,out/'production-tables.c',main,
            *(['-Wl,--gc-sections'] if kind=='avr' else []),'-o',executable])
        if kind=='native':
            result=subprocess.check_output([executable],text=True);print(result,end='')
            (out/'native.log').write_text(result)
        else:
            prefix=str(Path(compiler).with_name('avr-'));extension='.exe' if compiler.endswith('.exe') else ''
            build.run([prefix+'objcopy'+extension,'-O','binary','-R','.eeprom',executable,out/'prefix.bin'])
            symbols=subprocess.check_output([prefix+'nm'+extension,'-n',executable],text=True)
            (out/'symbols.txt').write_text(symbols)

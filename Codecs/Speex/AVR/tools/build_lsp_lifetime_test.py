#!/usr/bin/env python3
"""Build bounded LSP and in-place LPC tests with a separate Xiph oracle."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cc');p.add_argument('--avr-gcc');p.add_argument('--backend',choices=['asm','c'],default='c')
    p.add_argument('--mode',choices=['lifetime','margin'],default='lifetime')
    p.add_argument('--out',type=Path)
    args=p.parse_args()
    if not(args.cc or args.avr_gcc):p.error('Choose --cc and/or --avr-gcc')
    build.verify_sources()
    out=args.out or build.ROOT/('build/'+args.mode+'-unit-'+args.backend);out.mkdir(parents=True,exist_ok=True)
    reference=out/'reference';shutil.copytree(build.VENDOR,reference,dirs_exist_ok=True)
    (reference/'include/speex/speex_config_types.h').write_text('#include <stdint.h>\n'
        'typedef int16_t spx_int16_t;typedef uint16_t spx_uint16_t;\n'
        'typedef int32_t spx_int32_t;typedef uint32_t spx_uint32_t;\n')
    original=(reference/'libspeex/lsp.c').read_text()
    preamble=original[:original.index('#ifndef DISABLE_ENCODER')]
    preamble=preamble.replace('#include "math_approx.h"',
        '#include "avr_multiply.h"\n#include "avr_fixed.h"\n#include "math_approx.h"')
    production=out/'production-lsp.c'
    production.write_text(preamble+'\nSPEEX_NB3_NOINLINE void lsp_to_lpc(const spx_lsp_t *,spx_coef_t *,int,char *);\n'
        '#include "compact_lsp.c.inc"\n')
    for kind,compiler in [('native',args.cc),('avr',args.avr_gcc)]:
        if not compiler:continue
        common=['-std=c11','-fwrapv','-fno-strict-aliasing','-ffunction-sections','-fdata-sections',
            '-Wno-pointer-to-int-cast',*['-D'+d for d in build.DEFINES],
            '-I'+str(reference/'include'),'-I'+str(reference/'libspeex'),'-I'+str(build.ROOT/'src')]
        if kind=='avr':common+=['-mmcu=atmega328p','-mcall-prologues','-mrelax']
        oracle=[]
        for name in (['lsp','quant_lsp','bits','lsp_tables_nb'] if kind=='native' else ['lsp']):
            obj=out/(kind+'-reference-'+name+'.o');oracle.append(obj)
            build.run([compiler,*common,'-O2' if kind=='native' else '-Os','-DSPEEX_NB3_ENABLE_ASM=0',
                '-Dlsp_to_lpc=reference_lsp','-Dlsp_interpolate=reference_interpolate',
                '-Dlsp_unquant_lbr=reference_unquant','-c',reference/'libspeex'/(name+'.c'),'-o',obj])
        executable=out/('native.exe' if kind=='native' else 'lifetime.elf')
        flags=['-O2','-D_CRT_SECURE_NO_WARNINGS'] if kind=='native' else ['-Os','-flto']
        backend=args.backend if kind=='avr' else 'c'
        main=('nb3_margin.c' if kind=='native' else 'avr_nb3_margin.c') if args.mode=='margin' else ('lsp_lifetime.c' if kind=='native' else 'avr_lsp_lifetime.c')
        build.run([compiler,*common,*flags,'-DSPEEX_NB3_ENABLE_ASM='+str(int(backend=='asm')),
            *oracle,production,build.ROOT/'tests'/main,
            *([build.ROOT/'src'/s for s in build.ASM_SOURCES] if backend=='asm' else []),
            *(['-Wl,--gc-sections'] if kind=='avr' else []),'-o',executable])
        if kind=='native':
            log=subprocess.check_output([executable],text=True);print(log,end='');(out/'native.log').write_text(log)
        else:
            prefix=str(Path(compiler).with_name('avr-'));ext='.exe' if compiler.endswith('.exe') else ''
            build.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',executable,out/'lifetime.bin'])
            (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',executable],text=True))
if __name__=='__main__':main()

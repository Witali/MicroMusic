"""Build full-domain cosine tests against an untouched non-LTO Xiph object."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc');p.add_argument('--cc')
    p.add_argument('--backend',choices=['asm','c'],default='asm');p.add_argument('--irq',action='store_true')
    p.add_argument('--source-root',type=Path,default=build.ROOT);p.add_argument('--out',type=Path);args=p.parse_args()
    if not(args.avr_gcc or args.cc):p.error('Choose --avr-gcc and/or --cc')
    if args.irq and args.backend!='asm':p.error('--irq requires ASM')
    if args.irq and not args.avr_gcc:p.error('--irq requires --avr-gcc')
    build.verify_sources();out=args.out or build.ROOT/('build/angle-irq' if args.irq else 'build/angle-unit-'+args.backend);out.mkdir(parents=True,exist_ok=True)
    source=args.source_root.resolve()/'src';reference=out/'reference';shutil.copytree(build.VENDOR,reference,dirs_exist_ok=True,ignore=shutil.ignore_patterns('*.mid','*.midi','*.smf'))
    (reference/'include/speex/speex_config_types.h').write_text('#include <stdint.h>\ntypedef int16_t spx_int16_t;typedef uint16_t spx_uint16_t;typedef int32_t spx_int32_t;typedef uint32_t spx_uint32_t;\n',encoding='utf-8')
    if args.cc:
        flags=['-std=c11','-O2','-fwrapv','-fno-strict-aliasing',*['-D'+d for d in build.DEFINES],
            '-I'+str(reference/'include'),'-I'+str(reference/'libspeex')]
        original=out/'host-original.o'
        build.run([args.cc,*flags,'-c',build.ROOT/'tests/lsp_angle_reference.c','-o',original])
        for label,definitions in [('c-default',[]),('asm-unavailable',['SPEEX_NB3_ENABLE_ASM=1']),('unknown-arch',['SPEEX_NB3_ENABLE_ASM=1','SPEEX_NB3_ARCH=99'])]:
            exe=out/(label+'.exe');build.run([args.cc,*flags,*['-D'+d for d in definitions],'-I'+str(source),
                original,build.ROOT/'tests/lsp_angle.c','-o',exe]);build.run([exe])
        if not args.avr_gcc:return
    common=['-std=c11','-Os','-mmcu=atmega328p','-mcall-prologues','-mrelax','-fwrapv','-fno-strict-aliasing','-ffunction-sections','-fdata-sections']
    obj=out/'original.o';build.run([args.avr_gcc,*common,*['-D'+d for d in build.DEFINES],
        '-I'+str(reference/'include'),'-I'+str(reference/'libspeex'),'-c',build.ROOT/'tests/lsp_angle_reference.c','-o',obj])
    exe=out/'unit.elf';build.run([args.avr_gcc,*common,'-flto','-DSPEEX_NB3_ENABLE_ASM='+str(int(args.backend=='asm')),
        *(['-DSPEEX_ANGLE_IRQ_TEST'] if args.irq else []),'-I'+str(source),obj,build.ROOT/'tests/avr_lsp_angle.c',
        *([source/'lsp_angle.S'] if args.backend=='asm' else []),'-Wl,--gc-sections','-o',exe])
    prefix=str(Path(args.avr_gcc).with_name('avr-'));ext='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',exe,out/'unit.bin'])
    (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',exe],text=True),encoding='utf-8')
    headers=Path(args.avr_gcc).resolve().parents[1]/'avr/include/avr'
    (out/'device-headers.json').write_text(json.dumps({n:hashlib.sha256((headers/n).read_bytes()).hexdigest() for n in ['io.h','iom328p.h','interrupt.h']},indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()

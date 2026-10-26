"""Build both-order IIR tests with the production C fallback in separate objects."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True)
    p.add_argument('--source-root',type=Path,default=build.ROOT);p.add_argument('--out',type=Path)
    p.add_argument('--backend',choices=['asm','c'],default='asm');p.add_argument('--irq',action='store_true');args=p.parse_args()
    if args.irq and args.backend!='asm':p.error('IRQ proof requires the ASM build')
    build.verify_sources();out=(args.out or build.ROOT/('build/seed-iir-'+('irq' if args.irq else args.backend))).resolve();out.mkdir(parents=True,exist_ok=True)
    src=args.source_root.resolve()/'src';include=out/'include/speex';include.mkdir(parents=True,exist_ok=True)
    (include/'speex_config_types.h').write_text('#include <stdint.h>\ntypedef int16_t spx_int16_t;typedef uint16_t spx_uint16_t;typedef int32_t spx_int32_t;typedef uint32_t spx_uint32_t;\n',encoding='utf-8')
    common=['-mmcu=atmega328p','-std=c11','-Os','-mcall-prologues','-mrelax','-fwrapv','-fno-strict-aliasing','-ffunction-sections','-fdata-sections',
        '-I'+str(include),'-I'+str(build.VENDOR/'include'),'-I'+str(build.VENDOR/'libspeex'),'-I'+str(src)]
    objects=[]
    for name,source in [('nb',build.ROOT/'tests/iir_nb_forced_c.c'),('wb',src/'wb_iir.c')]:
        obj=out/(name+'.o');objects.append(obj)
        build.run([args.avr_gcc,*common,*['-D'+d for d in build.DEFINES],'-DSPEEX_NB3_ENABLE_ASM=0','-c',source,'-o',obj])
    exe=out/'unit.elf';build.run([args.avr_gcc,*common,'-flto','-DSPEEX_NB3_ENABLE_ASM='+str(int(args.backend=='asm')),
        *(['-DSPEEX_IIR_IRQ_TEST'] if args.irq else []),*objects,build.ROOT/'tests/avr_iir_block.c',
        *([src/'lpc_dot.S',src/'wb_iir.S'] if args.backend=='asm' else []),'-Wl,--gc-sections','-o',exe])
    prefix=str(Path(args.avr_gcc).with_name('avr-'));ext='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',exe,out/'unit.bin'])
    (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',exe],text=True),encoding='utf-8')
    headers=Path(args.avr_gcc).resolve().parents[1]/'avr/include/avr'
    (out/'backend.json').write_text(json.dumps(dict(backend=args.backend,irq=args.irq,binarySha256=hashlib.sha256((out/'unit.bin').read_bytes()).hexdigest(),
        headers={n:hashlib.sha256((headers/n).read_bytes()).hexdigest() for n in ['io.h','iom328p.h','interrupt.h']}),indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()

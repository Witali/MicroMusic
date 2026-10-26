"""Build paired-stage C/ASM tests, optionally with a real compiled AVR ISR."""
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
    p.add_argument('--backend',choices=['asm','c'],default='asm');p.add_argument('--irq',action='store_true')
    p.add_argument('--source-root',type=Path,default=build.ROOT);p.add_argument('--out',type=Path);args=p.parse_args()
    if args.irq and args.backend!='asm':p.error('--irq requires the ASM backend')
    out=args.out or build.ROOT/('build/pair-irq' if args.irq else 'build/pair-unit-'+args.backend);out.mkdir(parents=True,exist_ok=True)
    source=args.source_root.resolve()/'src';exe=out/'unit.elf'
    build.run([args.avr_gcc,'-std=c11','-Os','-flto','-fwrapv','-fno-strict-aliasing',
        '-ffunction-sections','-fdata-sections','-mmcu=atmega328p','-mcall-prologues','-mrelax',
        '-DSPEEX_NB3_ENABLE_ASM='+str(int(args.backend=='asm')),*(['-DSPEEX_PAIR_IRQ_TEST'] if args.irq else []),
        '-I'+str(source),build.ROOT/'tests/avr_lsp_pair.c',*([source/'lsp_pair.S'] if args.backend=='asm' else []),
        '-Wl,--gc-sections','-o',exe])
    prefix=str(Path(args.avr_gcc).with_name('avr-'));ext='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',exe,out/'unit.bin'])
    (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',exe],text=True),encoding='utf-8')
    headers=Path(args.avr_gcc).resolve().parents[1]/'avr/include/avr'
    (out/'device-headers.json').write_text(json.dumps({n:hashlib.sha256((headers/n).read_bytes()).hexdigest()
        for n in ['io.h','iom328p.h','interrupt.h']},indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()

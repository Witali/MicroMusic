#!/usr/bin/env python3
"""Build a real compiled AVR ISR for instruction-boundary stage preemption."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True);p.add_argument('--out',type=Path)
    args=p.parse_args();out=args.out or build.ROOT/'build/zero-stage-irq';out.mkdir(parents=True,exist_ok=True)
    exe=out/'irq.elf'
    build.run([args.avr_gcc,'-std=c11','-Os','-flto','-fwrapv','-fno-strict-aliasing','-ffunction-sections','-fdata-sections',
        '-mmcu=atmega328p','-mcall-prologues','-mrelax','-DSPEEX_NB3_ENABLE_ASM=1','-I'+str(build.ROOT/'src'),
        build.ROOT/'tests/avr_lsp_stage_irq.c',build.ROOT/'src/lsp_stage.S','-Wl,--gc-sections','-o',exe])
    prefix=str(Path(args.avr_gcc).with_name('avr-'));ext='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',exe,out/'irq.bin'])
    (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',exe],text=True),encoding='utf-8')
    headers=Path(args.avr_gcc).resolve().parents[1]/'avr/include/avr'
    data={'compiler':'AVR GCC 7.3.0','target':'atmega328p','headers':
        {n:hashlib.sha256((headers/n).read_bytes()).hexdigest() for n in ['io.h','iom328p.h','interrupt.h']},
        'descriptor':'SREG, TIMER2_COMPA_vect_num * (_VECTORS_SIZE / (SPM_READY_vect_num+1)) / 2, TIFR2/OCF2A, TIMSK2/OCIE2A from pinned ATmega328P avr/io.h'}
    (out/'device-headers.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()

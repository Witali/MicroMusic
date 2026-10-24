"""Build independent forty-sample excitation, bounds and AVR ABI tests."""
import argparse
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True);a=p.parse_args()
    out=build.ROOT/'build/long40-unit';out.mkdir(parents=True,exist_ok=True)
    (out/'test-codebook.h').write_text(','.join(str((i*73+19)%256-128) for i in range(320))+'\n')
    build.run([a.avr_gcc,'-std=c11','-mmcu=atmega328p','-Os','-flto','-fwrapv',
        '-fno-strict-aliasing','-mcall-prologues','-mrelax','-DSPEEX_NB3_ENABLE_ASM=1',
        '-I'+str(out),'-I'+str(build.ROOT/'src'),build.ROOT/'tests/avr_long40.c',
        build.ROOT/'src/innovation.S','-o',out/'long40.elf'])
    prefix=str(Path(a.avr_gcc).with_name('avr-'));ext='.exe' if a.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',out/'long40.elf',out/'long40.bin'])
    symbols=subprocess.check_output([prefix+'nm'+ext,'-n',out/'long40.elf'],text=True)
    (out/'symbols.txt').write_text(symbols,encoding='utf-8')

"""Build the independent fused pitch/innovation arithmetic and ABI mailbox."""
import argparse
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc',required=True)
    args=parser.parse_args()
    output=build.ROOT/'build/long-pitch-unit'
    output.mkdir(parents=True,exist_ok=True)
    (output/'test-shapes.h').write_text(','.join(str(i%256-128) for i in range(265))+'\n')
    build.run([args.avr_gcc,'-std=c11','-mmcu=atmega328p','-Os','-flto','-fwrapv',
        '-fno-strict-aliasing','-DSPEEX_NB3_ENABLE_ASM=1',
        '-I'+str(output),'-I'+str(build.ROOT/'src'),
        build.ROOT/'tests/avr_long_pitch.c',build.ROOT/'src/innovation.S',
        '-o',output/'long-pitch.elf'])
    prefix=str(Path(args.avr_gcc).with_name('avr-'))
    extension='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+extension,'-O','binary','-R','.eeprom',
               output/'long-pitch.elf',output/'long-pitch.bin'])
    symbols=subprocess.check_output([prefix+'nm'+extension,'-n',output/'long-pitch.elf'],text=True)
    (output/'symbols.txt').write_text(symbols,encoding='utf-8')

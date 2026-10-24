"""Build bounded zero-gain ASM/C and the independent packed ASM comparator."""
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
    output=build.ROOT/'build/zero-transform-unit'
    output.mkdir(parents=True,exist_ok=True)
    (output/'test-shapes.h').write_text(','.join(str(i%256-128) for i in range(265))+'\n')
    common=[args.avr_gcc,'-std=c11','-mmcu=atmega328p','-Os','-flto','-fwrapv',
            '-fno-strict-aliasing','-I'+str(output),'-I'+str(build.ROOT/'src')]
    build.run([*common,'-DSPEEX_NB3_ENABLE_ASM=0','-c',build.ROOT/'tests/zero_transform_c.c','-o',output/'c-worker.o'])
    build.run([*common,'-DSPEEX_NB3_ENABLE_ASM=1',build.ROOT/'tests/avr_zero_transform.c',
               build.ROOT/'src/innovation.S',output/'c-worker.o','-o',output/'zero-transform.elf'])
    prefix=str(Path(args.avr_gcc).with_name('avr-'))
    ext='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',output/'zero-transform.elf',output/'zero-transform.bin'])
    (output/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',output/'zero-transform.elf'],text=True))

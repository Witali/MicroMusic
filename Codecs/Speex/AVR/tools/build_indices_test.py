"""Build the NB3 index/header reader pairs with assembly explicitly disabled."""
import argparse,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc',required=True)
    args=parser.parse_args()
    output=build.ROOT/'build/indices';output.mkdir(parents=True,exist_ok=True)
    build.run([args.avr_gcc,'-mmcu=atmega328p','-std=c11','-Os','-flto','-fwrapv','-fno-strict-aliasing',
        '-DSPEEX_NB3_ENABLE_ASM=0','-I'+str(build.ROOT/'src'),'-I'+str(build.VENDOR/'include'),
        build.ROOT/'tests/avr_indices.c',build.ROOT/'src/bits.c','-o',output/'indices.elf'])
    prefix=str(Path(args.avr_gcc).with_name('avr-'));ext='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',output/'indices.elf',output/'indices.bin'])
    (output/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',output/'indices.elf'],text=True))

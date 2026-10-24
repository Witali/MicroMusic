"""Build both selected short-pitch backends over guarded full-scale history."""
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
    _,source=build.prepare('profile')
    out=build.ROOT/'build/short-pitch-unit';out.mkdir(parents=True,exist_ok=True)
    flags=['-std=c11','-mmcu=atmega328p','-Os','-flto','-fwrapv','-fno-strict-aliasing',
           '-I'+str(build.ROOT/'src'),'-I'+str(source/'include'),'-I'+str(source/'libspeex')]
    build.run([args.avr_gcc,*flags,'-DSPEEX_NB3_ENABLE_ASM=0','-c',
        build.ROOT/'tests/short_pitch_c.c','-o',out/'short-c.o'])
    build.run([args.avr_gcc,*flags,'-DSPEEX_NB3_ENABLE_ASM=1',
        build.ROOT/'tests/avr_short_pitch.c',out/'short-c.o',build.ROOT/'src/bits.c',
        build.ROOT/'src/innovation.S',source/'libspeex/gain_table_lbr.c',
        source/'libspeex/exc_10_32_table.c','-o',out/'short-pitch.elf'])
    prefix=str(Path(args.avr_gcc).with_name('avr-'))
    extension='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+extension,'-O','binary','-R','.eeprom',out/'short-pitch.elf',out/'short-pitch.bin'])
    (out/'symbols.txt').write_text(subprocess.check_output(
        [prefix+'nm'+extension,'-n',out/'short-pitch.elf'],text=True),encoding='utf-8')

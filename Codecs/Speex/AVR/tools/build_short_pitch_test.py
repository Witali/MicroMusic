"""Build both selected short-pitch backends over guarded full-scale history."""
import argparse
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build,apply_profile
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc',required=True)
    parser.add_argument('--enable-nb4',action='store_true',help='Exercise the shared ASM-side controller while retaining the NB3 numeric workload')
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    # Keep this primitive fixture separate from source-frozen decoder jobs.
    _,source=build.prepare('short-pitch-unit-source');apply_profile.apply(source)
    out=(args.out or build.ROOT/'build/short-pitch-unit').resolve();out.mkdir(parents=True,exist_ok=True)
    flags=['-std=c11','-mmcu=atmega328p','-Os','-flto','-fwrapv','-fno-strict-aliasing',
           '-DSPEEX_ENABLE_NB4='+str(int(args.enable_nb4)),
           '-I'+str(build.ROOT/'src'),'-I'+str(source/'include'),'-I'+str(source/'libspeex')]
    build.run([args.avr_gcc,*flags,'-DSPEEX_NB3_ENABLE_ASM=0','-c',
        build.ROOT/'tests/short_pitch_c.c','-o',out/'short-c.o'])
    build.run([args.avr_gcc,*flags,'-DSPEEX_NB3_ENABLE_ASM=1',
        build.ROOT/'tests/avr_short_pitch.c',out/'short-c.o',build.ROOT/'src/bits.c',
        build.ROOT/'src/innovation.S',source/'libspeex/gain_table_lbr.c',
        source/'libspeex/exc_10_32_table.c',
        *([source/'libspeex/exc_8_128_table.c'] if args.enable_nb4 else []),
        '-o',out/'short-pitch.elf'])
    prefix=str(Path(args.avr_gcc).with_name('avr-'))
    extension='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+extension,'-O','binary','-R','.eeprom',out/'short-pitch.elf',out/'short-pitch.bin'])
    (out/'symbols.txt').write_text(subprocess.check_output(
        [prefix+'nm'+extension,'-n',out/'short-pitch.elf'],text=True),encoding='utf-8')

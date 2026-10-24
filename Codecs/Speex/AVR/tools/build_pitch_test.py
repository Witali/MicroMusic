"""Build an independent AVR signed-byte-gain pitch arithmetic mailbox."""
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
    output=build.ROOT/'build/pitch-math'
    output.mkdir(parents=True,exist_ok=True)
    build.run([args.avr_gcc,'-mmcu=atmega328p','-O3','-flto','-fwrapv',
               build.ROOT/'tests/avr_pitch.c',build.ROOT/'src/pitch_add.S',
               '-o',output/'pitch.elf'])
    prefix=str(Path(args.avr_gcc).with_name('avr-'))
    extension='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+extension,'-O','binary','-R','.eeprom',output/'pitch.elf',output/'pitch.bin'])
    symbols=subprocess.check_output([prefix+'nm'+extension,'-n',output/'pitch.elf'],text=True)
    (output/'symbols.txt').write_text(symbols,encoding='utf-8')

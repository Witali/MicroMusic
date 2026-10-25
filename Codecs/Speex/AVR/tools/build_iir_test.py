"""Build the independent direct-LPC arithmetic and ABI mailbox."""
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
    output=build.ROOT/'build/iir'
    output.mkdir(parents=True,exist_ok=True)
    (output/'test-shapes.h').write_text(','.join(str(i%256-128) for i in range(265))+'\n')
    # innovation.S also contains the C40 entry and its global table reference.
    (output/'test-codebook.h').write_text(','.join(str((i*73+19)%256-128) for i in range(320))+'\n')
    build.run([args.avr_gcc,'-mmcu=atmega328p','-O3','-flto','-fwrapv',
               '-I'+str(output),'-I'+str(build.ROOT/'src'),
               build.ROOT/'tests/avr_iir.c',build.ROOT/'src/lpc_dot.S',
               build.ROOT/'src/innovation.S','-o',output/'iir.elf'])
    prefix=str(Path(args.avr_gcc).with_name('avr-'))
    extension='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+extension,'-O','binary','-R','.eeprom',output/'iir.elf',output/'iir.bin'])
    symbols=subprocess.check_output([prefix+'nm'+extension,'-n',output/'iir.elf'],text=True)
    (output/'symbols.txt').write_text(symbols,encoding='utf-8')

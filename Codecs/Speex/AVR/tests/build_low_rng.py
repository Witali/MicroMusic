#!/usr/bin/env python3
"""Build an isolated C/ASM LCG primitive mailbox with the real AVR ABI."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--avr-gcc', required=True)
    args = p.parse_args()
    out = ROOT/'build/low-rng-unit'
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([args.avr_gcc, '-std=c11', '-Os', '-flto', '-mmcu=atmega328p',
                    '-mcall-prologues', '-mrelax', '-fwrapv', '-fno-strict-aliasing',
                    '-DSPEEX_NB3_ENABLE_ASM=1', '-I'+str(ROOT/'src'),
                    ROOT/'tests/avr_low_rng.c', '-o', out/'rng.elf'], check=True)
    prefix = str(Path(args.avr_gcc).with_name('avr-'))
    ext = '.exe' if args.avr_gcc.endswith('.exe') else ''
    subprocess.run([prefix+'objcopy'+ext, '-O', 'binary', out/'rng.elf', out/'rng.bin'], check=True)
    (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext, '-n', out/'rng.elf'], text=True))
    (out/'input.json').write_bytes((json.dumps(dict(asmEnabled=True,
        binarySha256=hashlib.sha256((out/'rng.bin').read_bytes()).hexdigest()), indent=2)+'\n').encode())


if __name__ == '__main__': main()

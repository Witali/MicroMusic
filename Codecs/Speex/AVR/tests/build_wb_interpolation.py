#!/usr/bin/env python3
"""Build isolated existing/finite HB1 interpolation C recipes for AVR5."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ['original-loop-switch', 'difference-loop-switch',
           'difference-unswitched', 'finite-loop-margin', 'finite-unrolled-margin',
           'shared-quarter-loop', 'shared-quarter-finite-margin']


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc', required=True)
    parser.add_argument('--out', type=Path, default=ROOT/'build/wb-interpolation-unit')
    args = parser.parse_args()
    prefix = str(Path(args.avr_gcc).with_name('avr-'))
    ext = '.exe' if args.avr_gcc.endswith('.exe') else ''
    version = subprocess.check_output([args.avr_gcc, '--version'], text=True).splitlines()[0]
    flags = ['-std=c11', '-Os', '-flto', '-fwrapv', '-fno-strict-aliasing',
             '-mmcu=atmega328p', '-mcall-prologues', '-mrelax']
    for variant, recipe in enumerate(RECIPES):
        out = args.out/recipe
        out.mkdir(parents=True, exist_ok=True)
        subprocess.run([args.avr_gcc, *flags, '-DPROBE_VARIANT='+str(variant),
                        ROOT/'tests/avr_wb_interpolation.c', '-o', out/'unit.elf'], check=True)
        subprocess.run([prefix+'objcopy'+ext, '-O', 'binary', out/'unit.elf', out/'unit.bin'], check=True)
        symbols = subprocess.check_output([prefix+'nm'+ext, '-n', out/'unit.elf'], text=True)
        (out/'symbols.txt').write_text(symbols, encoding='utf-8')
        sizes = subprocess.check_output([prefix+'nm'+ext, '-S', '--size-sort', out/'unit.elf'], text=True)
        (out/'symbol-sizes.txt').write_text(sizes, encoding='utf-8')
        report = dict(scope='Isolated interpolation only; no full C decoder',
                      compiler=version, flags=flags, variant=variant, recipe=recipe,
                      binarySha256=hashlib.sha256((out/'unit.bin').read_bytes()).hexdigest(),
                      flashBytes=(out/'unit.bin').stat().st_size,
                      sourceSha256={p: digest(ROOT/p) for p in [
                          'tests/avr_wb_interpolation.c', 'tests/build_wb_interpolation.py',
                          'tests/check_wb_interpolation.py', 'tests/verify_wb_interpolation.mjs',
                          'vendor/speex-1.2.1/libspeex/high_lsp_tables.c']})
        (out/'input.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(recipe, report['flashBytes'], 'bytes', flush=True)


if __name__ == '__main__':
    main()

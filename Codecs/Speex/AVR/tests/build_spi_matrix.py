#!/usr/bin/env python3
"""Build separate long-file SPI player images without concurrent source generation."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--avr-gcc', required=True)
    p.add_argument('--driver-dir', type=Path)
    p.add_argument('--corpus', type=Path, default=ROOT/'build/spi-corpus')
    p.add_argument('--out', type=Path, default=ROOT/'build/spi-final')
    args = p.parse_args()
    for label in ['nb11', 'wb395', 'wb575', 'wb775', 'wb128', 'wb395-production']:
        profile = label.split('-')[0]
        command = [sys.executable, '-X', 'utf8', ROOT/'tools/build_spi_player.py',
                   '--avr-gcc', args.avr_gcc, '--backend', 'asm', '--low-rates', '7', '--enable-nb4',
                   '--stream', args.corpus/profile/'long.spxraw', '--out', args.out/label]
        if profile.startswith('wb'): command.append('--wideband')
        if not label.endswith('-production'): command.append('--capture-pcm')
        if args.driver_dir: command += ['--driver-dir', args.driver_dir]
        subprocess.run(command, check=True)
        print('Built', label, flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Build the noise-speed decoder, IRQ, mixed-mode and SPI admission images."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import build
import build_wb


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--avr-gcc', required=True)
    p.add_argument('--spi-stream', type=Path, required=True)
    args = p.parse_args()
    out = ROOT/'build/noise-final'
    build.avr(args.avr_gcc, backend='asm', packet_bytes=6, enable_nb4=True, low_rates=7, destination=out/'nb215')
    build_wb.avr(args.avr_gcc, 'asm', packet_bytes=10, enable_nb4=True, low_rates=7, destination=out/'wb395')
    for load in [0, 19200, 25600]:
        subprocess.run([sys.executable, ROOT/'tools/build_wb_stream_test.py', '--avr-gcc', args.avr_gcc,
                        '--packet-bytes', '10', '--low-rates', '7', '--enable-nb4',
                        '--frame-load-cycles', str(load), '--out', out/('irq-'+str(load))], check=True)
    subprocess.run([sys.executable, ROOT/'tools/build_spi_player.py', '--avr-gcc', args.avr_gcc,
                    '--backend', 'asm', '--wideband', '--enable-nb4', '--stream', args.spi_stream,
                    '--out', out/'spi'], check=True)
    subprocess.run([sys.executable, ROOT/'tests/build_low_api.py', '--avr-gcc', args.avr_gcc,
                    '--out', out/'api'], check=True)
    subprocess.run([sys.executable, ROOT/'tests/check_low_disabled.py', '--avr-gcc', args.avr_gcc], check=True)
    for label in ['wb395', 'nb11']:
        stream = args.spi_stream.parent.parent/label/'long.spxraw'
        command = [sys.executable, ROOT/'tools/build_spi_player.py', '--avr-gcc', args.avr_gcc,
                   '--backend', 'c', '--enable-nb4', '--stream', stream, '--out', out/('c-'+label)]
        if label.startswith('wb'): command.append('--wideband')
        subprocess.run(command, check=True)
    print('Built noise-speed admission images; C images are compile/link only')


if __name__ == '__main__': main()

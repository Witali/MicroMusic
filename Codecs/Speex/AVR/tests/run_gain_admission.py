#!/usr/bin/env python3
"""Run matched ASM gain-divider admission; never execute the C decoder."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--node', required=True)
    p.add_argument('--low-corpus', type=Path, required=True)
    p.add_argument('--legacy-corpus', type=Path, required=True,
                   help='AVR/build containing wb-corpus and higher-corpus')
    p.add_argument('--spi-corpus', type=Path, required=True)
    p.add_argument('--mixed-corpus', type=Path, required=True)
    p.add_argument('--spi-model', type=Path, required=True)
    p.add_argument('--phase', choices=['before', 'after', 'irq', 'transport-api'], required=True)
    args = p.parse_args()

    def run(test, firmware, *options):
        with (firmware/'run.log').open('w', encoding='utf-8') as log:
            subprocess.run([args.node, ROOT/'tests'/test, *options],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        print('PASS', args.phase, firmware.name, flush=True)

    if args.phase == 'transport-api':
        for label in ['wb395', 'wb128']:
            fw = ROOT/'build/gain-spi'/label
            run('verify_spi_player.mjs', fw, fw, args.spi_corpus/label/'long.spxraw',
                args.spi_corpus/label/'long.pcm', args.spi_model)
        for label in ['nb', 'wb']:
            fw = ROOT/'build/gain-api'/label
            run('verify_low_api.mjs', fw, fw, args.mixed_corpus/label)
    else:
        for label in ['wb395', 'wb575', 'wb775', 'wb98', 'wb128']:
            if label in ['wb395', 'wb575', 'wb775']:
                corpus = args.low_corpus/label
            elif label == 'wb98':
                corpus = args.legacy_corpus/'wb-corpus'
            else:
                corpus = args.legacy_corpus/'higher-corpus/wb128'
            fw = ROOT/('build/gain-'+args.phase)/label
            run('verify_wb_stream.mjs' if args.phase == 'irq' else 'verify_wb.mjs', fw,
                '--firmware', fw, '--streams', corpus/'streams', '--oracle', corpus/'oracle')


if __name__ == '__main__':
    main()

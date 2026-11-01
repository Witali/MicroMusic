#!/usr/bin/env python3
"""Run affected ASM modes and active-output gates; C decoder is excluded."""
import argparse
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--node',required=True)
    p.add_argument('--low-corpus',type=Path,required=True)
    p.add_argument('--mixed-corpus',type=Path,required=True)
    p.add_argument('--spi-corpus',type=Path,required=True)
    p.add_argument('--spi-model',type=Path,required=True)
    p.add_argument('--phase',choices=['raw','irq','transport-api'],required=True)
    args=p.parse_args()

    def run(test,firmware,*options):
        with (firmware/'run.log').open('w',encoding='utf-8') as log:
            subprocess.run([args.node,ROOT/'tests'/test,*options],check=True,stdout=log,stderr=subprocess.STDOUT)
        print('PASS',args.phase,firmware.name,flush=True)

    out=ROOT/'build/mean-final'
    if args.phase=='raw':
        for label in ['nb215','wb395']:
            fw=out/label;corpus=args.low_corpus/label
            options=['--firmware',fw,'--streams',corpus/'streams','--oracle',corpus/'oracle']
            if label=='nb215':options.append('--verify-reset')
            run('verify_avr.mjs' if label=='nb215' else 'verify_wb.mjs',fw,*options)
    elif args.phase=='irq':
        fw=out/'irq';corpus=args.low_corpus/'wb395'
        run('verify_wb_stream.mjs',fw,'--firmware',fw,'--streams',corpus/'streams','--oracle',corpus/'oracle')
    else:
        fw=out/'spi';corpus=args.spi_corpus/'wb395'
        run('verify_spi_player.mjs',fw,fw,corpus/'long.spxraw',corpus/'long.pcm',args.spi_model)
        for label in ['nb','wb']:
            fw=out/'api'/label
            run('verify_low_api.mjs',fw,fw,args.mixed_corpus/label,'--count-mean')


if __name__=='__main__':main()

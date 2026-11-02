#!/usr/bin/env python3
"""Run fresh ASM gain-zero decoding and output; no full C decoder execution."""
import argparse
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--node',required=True)
    for name in ['low-corpus','mixed-corpus','spi-corpus','spi-model']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--phase',choices=['raw','irq8','irq11','transport-api'],required=True);args=p.parse_args()
    out=ROOT/'build/nb1-zero-final'

    def run(test,folder,*options):
        with (folder/'run.log').open('w',encoding='utf-8') as log:
            subprocess.run([args.node,ROOT/'tests'/test,*map(str,options)],stdout=log,stderr=subprocess.STDOUT,check=True)
        print('PASS',args.phase,folder,flush=True)

    if args.phase=='raw':
        for label,wb in [('nb215',False),('wb395',True)]:
            folder=out/'after'/label;corpus=args.low_corpus/label
            run('verify_wb.mjs' if wb else 'verify_avr.mjs',folder,'--firmware',folder,'--streams',corpus/'streams',
                '--oracle',corpus/'oracle','--packet-timing',*([] if wb else ['--verify-reset']))
    elif args.phase in ['irq8','irq11']:
        folder=out/'after'/args.phase;corpus=args.low_corpus/'wb395'
        run('verify_wb_stream.mjs',folder,'--firmware',folder,'--streams',corpus/'streams','--oracle',corpus/'oracle')
    else:
        for label in ['nb215','wb395']:
            folder=out/'after/spi'/label;corpus=args.spi_corpus/label
            run('verify_spi_player.mjs',folder,folder,corpus/'long.spxraw',corpus/'long.pcm',args.spi_model)
        for epoch in ['before','after']:
            for label in ['nb','wb']:
                folder=out/epoch/'api'/label;options=['--count-noise-prepare','--count-vocoder','--count-noise-values','--count-nb1-gain']
                if label=='wb':options.append('--count-noise-fold')
                run('verify_low_api.mjs',folder,folder,args.mixed_corpus/label,*options)
        folder=ROOT/'build/noise-cache-unit';run('verify_nb1_streaming.mjs',folder,folder,args.mixed_corpus/'wb')
        for label,wb in [('nb215',False),('wb395',True)]:
            folder=out/'features/asm'/label;corpus=ROOT/'build/nb1-gain-screen-data'/label
            run('verify_wb.mjs' if wb else 'verify_avr.mjs',folder,'--firmware',folder,'--streams',corpus/'streams',
                '--oracle',corpus/'oracle',*([] if wb else ['--verify-reset']))


if __name__=='__main__':main()

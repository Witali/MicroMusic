#!/usr/bin/env python3
"""Run ASM decoding/output and independent state; never execute a full C decoder."""
import argparse
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--node',required=True)
    for name in ['low-corpus','mixed-corpus','spi-corpus','spi-model']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--phase',choices=['raw','irq8','irq11','transport-api'],required=True);args=parser.parse_args()
    out=ROOT/'build/zero-synthesis-final'

    def run(test,folder,*options):
        with (folder/'run.log').open('w',encoding='utf-8') as log:
            subprocess.run([args.node,ROOT/'tests'/test,*map(str,options)],stdout=log,stderr=subprocess.STDOUT,check=True)
        print('PASS',args.phase,folder,flush=True)

    if args.phase=='raw':
        folder=out/'after/wb395';corpus=args.low_corpus/'wb395'
        run('verify_wb.mjs',folder,'--firmware',folder,'--streams',corpus/'streams','--oracle',corpus/'oracle','--packet-timing')
    elif args.phase in ['irq8','irq11']:
        folder=out/'after'/args.phase;corpus=args.low_corpus/'wb395'
        run('verify_wb_stream.mjs',folder,'--firmware',folder,'--streams',corpus/'streams','--oracle',corpus/'oracle')
    else:
        folder=out/'after/spi/wb395';corpus=args.spi_corpus/'wb395'
        run('verify_spi_player.mjs',folder,folder,corpus/'long.spxraw',corpus/'long.pcm',args.spi_model)
        for epoch in ['before','after']:
            for label in ['nb','wb']:
                folder=out/epoch/'api'/label;options=['--count-noise-prepare','--count-vocoder','--count-noise-values','--count-nb1-gain']
                if label=='wb':options.append('--count-noise-fold')
                run('verify_low_api.mjs',folder,folder,args.mixed_corpus/label,*options)
        folder=ROOT/'build/noise-cache-unit';run('verify_nb1_streaming.mjs',folder,folder,args.mixed_corpus/'wb')
        # Prefixes are complete 128-frame histories from three unchanged streams.
        from screen_nb1_gain import prepare_data
        prepare_data(args.low_corpus);folder=out/'features/asm';corpus=ROOT/'build/nb1-gain-screen-data/wb395'
        run('verify_wb.mjs',folder,'--firmware',folder,'--streams',corpus/'streams','--oracle',corpus/'oracle')


if __name__=='__main__':main()

#!/usr/bin/env python3
"""Run exact ASM output checks; never execute or time the C decoder."""
import argparse
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--node',required=True)
    for name in ['low-corpus','mixed-corpus','spi-corpus','spi-model']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--phase',choices=['raw','irq8','irq11','transport-api'],required=True)
    args=p.parse_args();out=ROOT/'build/noise-prefold-final'

    def run(test,fw,*options):
        with (fw/'run.log').open('w',encoding='utf-8') as log:
            subprocess.run([args.node,ROOT/'tests'/test,*map(str,options)],check=True,stdout=log,stderr=subprocess.STDOUT)
        print('PASS',args.phase,fw.name,flush=True)

    if args.phase=='raw':
        fw=out/'wb395';corpus=args.low_corpus/'wb395'
        run('verify_wb.mjs',fw,'--firmware',fw,'--streams',corpus/'streams','--oracle',corpus/'oracle')
    elif args.phase=='transport-api':
        fw=out/'spi';corpus=args.spi_corpus/'wb395'
        run('verify_spi_player.mjs',fw,fw,corpus/'long.spxraw',corpus/'long.pcm',args.spi_model)
        for label in ['nb','wb']:
            fw=out/'api'/label;options=['--count-vocoder','--count-noise-values','--count-noise-prepare']
            if label=='wb':options.append('--count-noise-fold')
            run('verify_low_api.mjs',fw,fw,args.mixed_corpus/label,*options)
        fw=ROOT/'build/noise-cache-unit';run('verify_nb1_streaming.mjs',fw,fw,args.mixed_corpus/'wb')
    else:
        fw=out/args.phase;corpus=args.low_corpus/'wb395'
        run('verify_wb_stream.mjs',fw,'--firmware',fw,'--streams',corpus/'streams','--oracle',corpus/'oracle')


if __name__=='__main__':main()

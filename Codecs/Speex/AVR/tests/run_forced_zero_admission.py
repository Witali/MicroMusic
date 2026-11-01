#!/usr/bin/env python3
"""Run exact ASM decoding and output, never execute/time the C decoder."""
import argparse
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
PROFILES={'nb395':False,'wb575':True}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--node',required=True)
    for name in ['low-corpus','mixed-corpus','spi-corpus','spi-model']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--phase',choices=['before','after','irq','transport-api'],required=True);args=p.parse_args()
    out=ROOT/'build/forced-zero-final'

    def run(test,fw,*options):
        with (fw/'run.log').open('w',encoding='utf-8') as log:
            subprocess.run([args.node,ROOT/'tests'/test,*map(str,options)],check=True,stdout=log,stderr=subprocess.STDOUT)
        print('PASS',args.phase,fw,flush=True)

    if args.phase in ['before','after']:
        for label,wb in PROFILES.items():
            fw=out/args.phase/label;corpus=args.low_corpus/label
            run('verify_wb.mjs' if wb else 'verify_avr.mjs',fw,'--firmware',fw,'--streams',corpus/'streams',
                '--oracle',corpus/'oracle','--forced-zero-timing',*([] if wb else ['--verify-reset']))
    elif args.phase=='irq':
        fw=out/'irq/wb575';corpus=args.low_corpus/'wb575'
        run('verify_wb_stream.mjs',fw,'--firmware',fw,'--streams',corpus/'streams','--oracle',corpus/'oracle')
    else:
        for label,wb in PROFILES.items():
            fw=out/'spi'/label
            raw=args.spi_corpus/label/'long.spxraw' if wb else args.low_corpus/label/'streams/coverage4096.spxraw'
            pcm=args.spi_corpus/label/'long.pcm' if wb else args.low_corpus/label/'oracle/coverage4096.pcm'
            run('verify_spi_player.mjs',fw,fw,raw,pcm,args.spi_model)
            fw=out/'features/asm'/label;corpus=ROOT/'build/forced-zero-screen-data'/label
            run('verify_wb.mjs' if wb else 'verify_avr.mjs',fw,'--firmware',fw,'--streams',corpus/'streams',
                '--oracle',corpus/'oracle',*([] if wb else ['--verify-reset']))
        for label in ['nb','wb']:
            fw=out/'api'/label;run('verify_low_api.mjs',fw,fw,args.mixed_corpus/label,'--count-forced-zero')


if __name__=='__main__':main()

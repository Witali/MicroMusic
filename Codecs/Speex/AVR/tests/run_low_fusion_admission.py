#!/usr/bin/env python3
"""Run matched ASM decoder and actual IRQ/SPI; never execute the C decoder."""
import argparse
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--node',required=True)
    for name in ['low-corpus','mixed-corpus','spi-corpus','spi-model']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--phase',choices=['before','after','irq','transport-api'],required=True)
    args=p.parse_args();out=ROOT/'build/low-fusion-final'

    def run(test,fw,*options):
        with (fw/'run.log').open('w',encoding='utf-8') as log:
            subprocess.run([args.node,ROOT/'tests'/test,*map(str,options)],check=True,stdout=log,stderr=subprocess.STDOUT)
        print('PASS',args.phase,fw.name,flush=True)

    if args.phase=='transport-api':
        for label in ['wb575','wb775']:
            fw=out/'spi'/label;corpus=args.spi_corpus/label
            run('verify_spi_player.mjs',fw,fw,corpus/'long.spxraw',corpus/'long.pcm',args.spi_model)
            fw=out/'features/asm'/label;corpus=ROOT/'build/low-fuse-screen-data'/label
            run('verify_wb.mjs',fw,'--firmware',fw,'--streams',corpus/'streams','--oracle',corpus/'oracle')
        for label in ['nb','wb']:
            fw=out/'api'/label
            run('verify_low_api.mjs',fw,fw,args.mixed_corpus/label,'--count-low-fusion')
    else:
        for label in ['wb575','wb775']:
            fw=out/args.phase/label;corpus=args.low_corpus/label
            run('verify_wb_stream.mjs' if args.phase=='irq' else 'verify_wb.mjs',fw,
                '--firmware',fw,'--streams',corpus/'streams','--oracle',corpus/'oracle')


if __name__=='__main__':main()

#!/usr/bin/env python3
"""Build all enabled NB/WB decoder and continuous-player admission images."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb
PROFILES={'nb215':6,'nb395':10,'nb595':15,'nb8':20,'nb11':28,
          'wb395':10,'wb575':15,'wb775':20,'wb98':25,'wb128':32}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True)
    p.add_argument('--out',type=Path,default=ROOT/'build/low-final')
    p.add_argument('--profiles',default=','.join(PROFILES))
    p.add_argument('--players',action='store_true');p.add_argument('--frame-load-cycles',type=int,default=0)
    args=p.parse_args()
    for label in args.profiles.split(','):
        width=PROFILES[label];out=args.out/label
        if args.players:
            if label.startswith('nb'):continue
            subprocess.run([sys.executable,'-X','utf8',ROOT/'tools/build_wb_stream_test.py',
                '--avr-gcc',args.avr_gcc,'--packet-bytes',str(width),'--low-rates','7','--enable-nb4',
                '--frame-load-cycles',str(args.frame_load_cycles),'--out',out],check=True)
        elif label.startswith('nb'):
            build.avr(args.avr_gcc,backend='asm',packet_bytes=width,enable_nb4=True,low_rates=7,destination=out)
        else:
            build_wb.avr(args.avr_gcc,'asm',packet_bytes=width,enable_nb4=True,low_rates=7,destination=out)
        print('Built',label,'player' if args.players else 'decoder',flush=True)

if __name__=='__main__':main()

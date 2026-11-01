#!/usr/bin/env python3
"""Rebuild the four minimum ASM profiles and prove disabled-feature identity."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True);args=p.parse_args()
    rows=[]
    for label,width,reference in [('nb8',20,'group4-nb8-asm.json'),('nb11',28,'group4-nb11-asm.json'),
                                  ('wb98',25,'wb-qmf-after-98.json'),('wb128',32,'wb-qmf-after-128.json')]:
        out=ROOT/'build/low-disabled'/label
        if label.startswith('nb'):
            build.avr(args.avr_gcc,backend='asm',packet_bytes=width,enable_nb4=width==28,destination=out)
            binary=out/'speex-test.bin'
        else:
            build_wb.avr(args.avr_gcc,'asm',packet_bytes=width,destination=out)
            binary=out/'wb.bin'
        sha=hashlib.sha256(binary.read_bytes()).hexdigest()
        before=json.loads((ROOT/'reports'/reference).read_text())
        assert sha==before['binarySha256'],label
        rows.append(dict(profile=label,sha256=sha,flashBytes=binary.stat().st_size,byteIdentical=True))
    report=dict(scope='Lower profiles disabled; four original ASM decoder images unchanged',images=rows)
    (ROOT/'build/low-disabled-identity.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print('PASS four minimum ASM images byte-identical with lower profiles disabled')

if __name__=='__main__':main()

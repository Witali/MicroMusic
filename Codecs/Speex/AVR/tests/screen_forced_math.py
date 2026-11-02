#!/usr/bin/env python3
"""Measure coefficient/Q6 variants with the same 384-frame ASM workloads."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb
from build_forced_zero_admission import prepare_data
PROFILES={'nb395':(10,False),'wb575':(15,True)}


def variant(original,coefficient,q6):
    text=original
    if coefficient or q6:
        text=text.replace('#include "forced_pitch.h"','#include "forced_pitch.h"\n#include "forced_math.h"')
    if coefficient:
        old='uint8_t coefficient=(2185L*(int16_t)(coded_coefficient<<6)+16384)>>15;'
        assert text.count(old)==1;text=text.replace(old,'uint8_t coefficient=speex_forced_coefficient_c(coded_coefficient);')
    if q6:
        old='while(depth--)value=(int16_t)speex_avr_asr13(\n        MULT16_16(value,(int16_t)coefficient<<7)+4096);'
        assert text.count(old)==1;text=text.replace(old,'while(depth--)value=speex_forced_q6(value,coefficient);')
    return text


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True);p.add_argument('--node',required=True)
    p.add_argument('--corpus',type=Path,required=True);p.add_argument('--baseline-images',type=Path,required=True)
    p.add_argument('--baseline-root',type=Path,required=True)
    args=p.parse_args();prepare_data(args.corpus);out=ROOT/'build/forced-math-screen';out.mkdir(parents=True,exist_ok=True)
    base=json.loads((ROOT/'reports/forced-one-admission.json').read_text())
    for n,h in base['sourceSha256'].items():assert hashlib.sha256((args.baseline_root/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==h,n
    source=ROOT/'src/lowrate_excitation.h';original=source.read_bytes()
    text=(args.baseline_root/'src/lowrate_excitation.h').read_text();rows=[]
    try:
        for name,coefficient,q6 in [('before',False,False),('coefficient',True,False),('q6',False,True),('both',True,True)]:
            current=variant(text,coefficient,q6);source.write_bytes(current.encode())
            for label,(width,wb) in PROFILES.items():
                folder=out/name/label
                if name=='before':
                    parent=args.baseline_images/label;filename='wb.bin' if wb else 'speex-test.bin'
                    expected=json.loads((ROOT/'reports'/('forced-one-after-'+label+'.json')).read_text())['binarySha256']
                    assert hashlib.sha256((parent/filename).read_bytes()).hexdigest()==expected
                    shutil.copytree(parent,folder,dirs_exist_ok=True)
                else:
                    builder=build_wb.avr if wb else build.avr
                    builder(args.avr_gcc,backend='asm',packet_bytes=width,enable_nb4=True,low_rates=7,destination=folder)
                corpus=ROOT/'build/forced-zero-screen-data'/label
                with (folder/'screen.log').open('w',encoding='utf-8') as log:
                    subprocess.run([args.node,ROOT/'tests'/('verify_wb.mjs' if wb else 'verify_avr.mjs'),
                        '--firmware',folder,'--streams',corpus/'streams','--oracle',corpus/'oracle','--forced-zero-timing',
                        *([] if wb else ['--verify-reset'])],stdout=log,stderr=subprocess.STDOUT,check=True)
                report=json.loads((folder/('verification.json' if wb else 'avr-verification.json')).read_text())
                trace=json.loads((folder/'forced-zero-timing.json').read_text());assert report['frames']==trace['frames']==384
                rows.append(dict(variant=name,profile=label,sourceSha256=hashlib.sha256(current.encode()).hexdigest(),
                    binarySha256=report['binarySha256'],flashBytes=report['flashBytes'],
                    meanCycles=sum(sum(r['cycles']) for r in trace['streams'])/384,
                    peakStack=report.get('peakStack',2303-report.get('minStackPointer',2303)),
                    pcmExact=True,resetExact=True))
                print('PASS',json.dumps(rows[-1]),flush=True)
    finally:source.write_bytes(original)
    (out/'summary.json').write_bytes((json.dumps(dict(scope='Matched three-stream 384-frame ASM screening; no IRQ or C decoder',
        rows=rows,baselineSourceVerified=True),indent=2)+'\n').encode())


if __name__=='__main__':main()

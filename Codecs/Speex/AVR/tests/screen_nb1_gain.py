#!/usr/bin/env python3
"""Compare exact NB1 coefficient, factored-gain and finite-table variants."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb
PROFILES={'nb215':(6,False),'wb395':(10,True)}


def variant(text,name):
    if name=='before':return text
    anchor='#if SPEEX_ENABLE_NB1\nstatic SPEEX_NB3_ALWAYS_INLINE int16_t speex_low_q15'
    assert text.count(anchor)==1
    header='forced_math.h' if name=='coefficient' else 'nb1_gain.h'
    text=text.replace(anchor,'#if SPEEX_ENABLE_NB1\n#include "'+header+'"\nstatic SPEEX_NB3_ALWAYS_INLINE int16_t speex_low_q15')
    old='int16_t coefficient=(2185L*(int16_t)(speex_packet_field(packet,30,4)<<6)+16384)>>15;'
    assert text.count(old)==1
    if name=='coefficient':return text.replace(old,'int16_t coefficient=speex_forced_coefficient_c(speex_packet_field(packet,30,4));')
    old+='\n    int16_t g=(int16_t)((24576L*(coefficient-13)+8192)>>14);\n    if(g<0)g=0;if(g>64)g=64;'
    assert text.count(old)==1
    suffix={'factored':'c','table':'table_c','bounded-table':'bounded_table_c','selected':'selected_c'}[name]
    return text.replace(old,'int16_t g=speex_nb1_gain_'+suffix+'(speex_packet_field(packet,30,4));')


def prepare_data(corpus):
    out=ROOT/'build/nb1-gain-screen-data';rows=[]
    for label,(width,wb) in PROFILES.items():
        for name in ['coverage4096','en_letter_a','ru_slutskaya_a']:
            row=dict(profile=label,stream=name,frames=128)
            for folder,suffix,size,key in [('streams','.spxraw',width,'input'),('oracle','.pcm',640 if wb else 320,'pcm')]:
                data=(corpus/label/folder/(name+suffix)).read_bytes();part=data[:128*size];assert len(part)==128*size
                path=out/label/folder/(name+suffix);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(part)
                row[key+'Sha256']=hashlib.sha256(part).hexdigest();row['source'+key.title()+'Sha256']=hashlib.sha256(data).hexdigest()
            rows.append(row)
    (out/'manifest.json').write_bytes((json.dumps(dict(streams=rows),indent=2)+'\n').encode())


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True);p.add_argument('--node',required=True)
    p.add_argument('--baseline-root',type=Path,required=True);p.add_argument('--corpus',type=Path,required=True);args=p.parse_args()
    base=json.loads((ROOT/'reports/forced-math-admission.json').read_text())
    for n,h in base['sourceSha256'].items():assert hashlib.sha256((args.baseline_root/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==h,n
    prepare_data(args.corpus);out=ROOT/'build/nb1-gain-screen';out.mkdir(parents=True,exist_ok=True)
    source=ROOT/'src/lowrate_excitation.h';original=source.read_bytes();before=(args.baseline_root/'src/lowrate_excitation.h').read_text();rows=[]
    try:
        for name in ['before','coefficient','factored','table','bounded-table','selected']:
            text=variant(before,name);source.write_bytes(text.encode())
            for label,(width,wb) in PROFILES.items():
                folder=out/name/label;builder=build_wb.avr if wb else build.avr
                builder(args.avr_gcc,backend='asm',packet_bytes=width,enable_nb4=True,low_rates=7,destination=folder)
                corpus=ROOT/'build/nb1-gain-screen-data'/label
                with (folder/'screen.log').open('w',encoding='utf-8') as log:
                    subprocess.run([args.node,ROOT/'tests'/('verify_wb.mjs' if wb else 'verify_avr.mjs'),
                        '--firmware',folder,'--streams',corpus/'streams','--oracle',corpus/'oracle','--packet-timing',
                        *([] if wb else ['--verify-reset'])],stdout=log,stderr=subprocess.STDOUT,check=True)
                report=json.loads((folder/('verification.json' if wb else 'avr-verification.json')).read_text())
                trace=json.loads((folder/'packet-timing.json').read_text());assert trace['frames']==report['frames']==384
                rows.append(dict(variant=name,profile=label,sourceSha256=hashlib.sha256(text.encode()).hexdigest(),
                    binarySha256=report['binarySha256'],flashBytes=report['flashBytes'],staticSramBytes=report['staticSramBytes'],
                    meanCycles=sum(sum(r['cycles']) for r in trace['streams'])/384,
                    peakStack=report.get('peakStack',2303-report.get('minStackPointer',2303)),pcmExact=True,resetExact=True))
                print('PASS',json.dumps(rows[-1]),flush=True)
    finally:source.write_bytes(original)
    (out/'summary.json').write_bytes((json.dumps(dict(scope='384-frame matched NB1 ASM variant screens; no IRQ or C decoder',
        baselineSourceVerified=True,rows=rows),indent=2)+'\n').encode())


if __name__=='__main__':main()

#!/usr/bin/env python3
"""Compare exact gain-zero preparation layouts in complete ASM decoders."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb
from screen_nb1_gain import PROFILES,prepare_data


def variant(text,name):
    if name=='before':return text
    assert text.count('#include "nb1_gain.h"')==1
    text=text.replace('#include "nb1_gain.h"','#include "nb1_gain.h"\n#include "nb1_zero_gain.h"')
    old='''    int16_t amplitude=(int16_t)((int32_t)spx_sqrt(2*(int16_t)pitch)*
        (int16_t)(((int32_t)g*((scale+8192)>>14)+32)>>6));
    int16_t noise_gain=32767-435*g,previous_gain=77*g;
    int16_t pulse_now=speex_low_q15(22938,amplitude);
    int16_t pulse_previous=speex_low_q15(9830,amplitude);'''
    new='''    int16_t noise_gain=32767,previous_gain=0,pulse_now=0,pulse_previous=0;
    if(g) {
        int16_t amplitude=(int16_t)((int32_t)spx_sqrt(2*(int16_t)pitch)*
            (int16_t)(((int32_t)g*((scale+8192)>>14)+32)>>6));
        noise_gain=32767-435*g;previous_gain=77*g;
        pulse_now=speex_low_q15(22938,amplitude);
        pulse_previous=speex_low_q15(9830,amplitude);
    }'''
    assert text.count(old)==1;text=text.replace(old,new)
    old_prior='int16_t prior_noise=speex_low_q15(previous_gain,st->voc_previous);'
    assert text.count(old_prior)==1;text=text.replace(old_prior,'int16_t prior_noise=g?speex_low_q15(previous_gain,st->voc_previous):0;')
    old_loop='''    for(uint8_t i=0;i<5;i++) {
        current[i]=speex_low_q15(noise_gain,noise[i]);
        previous[i]=speex_low_q15(previous_gain,noise[i]);
#if SPEEX_ENABLE_WB1
        /* HB1's first quantizer is frame-invariant; class2 is exactly zero. */
        prefold[i]=i==2?0:speex_low_q15(29491,noise[i]);
#endif
    }'''
    assert text.count(old_loop)==1
    if name=='root-only':return text
    if name=='loop':
        new_loop='''    for(uint8_t i=0;i<5;i++) {
        if(g) {
            current[i]=speex_low_q15(noise_gain,noise[i]);
            previous[i]=speex_low_q15(previous_gain,noise[i]);
        } else {
            current[i]=speex_nb1_noise_unity_c(noise[i]);previous[i]=0;
        }
#if SPEEX_ENABLE_WB1
        prefold[i]=i==2?0:speex_low_q15(29491,noise[i]);
#endif
    }'''
    elif name=='split':
        new_loop='''    if(g) {
        for(uint8_t i=0;i<5;i++) {
            current[i]=speex_low_q15(noise_gain,noise[i]);
            previous[i]=speex_low_q15(previous_gain,noise[i]);
#if SPEEX_ENABLE_WB1
            prefold[i]=i==2?0:speex_low_q15(29491,noise[i]);
#endif
        }
    } else {
        for(uint8_t i=0;i<5;i++) {
            current[i]=speex_nb1_noise_unity_c(noise[i]);previous[i]=0;
#if SPEEX_ENABLE_WB1
            prefold[i]=i==2?0:speex_low_q15(29491,noise[i]);
#endif
        }
    }'''
    elif name=='common-fold':
        new_loop='''    if(g) {
        for(uint8_t i=0;i<5;i++) {
            current[i]=speex_low_q15(noise_gain,noise[i]);
            previous[i]=speex_low_q15(previous_gain,noise[i]);
        }
    } else {
        for(uint8_t i=0;i<5;i++) {
            current[i]=speex_nb1_noise_unity_c(noise[i]);previous[i]=0;
        }
    }
#if SPEEX_ENABLE_WB1
    for(uint8_t i=0;i<5;i++)prefold[i]=i==2?0:speex_low_q15(29491,noise[i]);
#endif'''
    else:raise ValueError(name)
    return text.replace(old_loop,new_loop)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True);p.add_argument('--node',required=True)
    for n in ['baseline-root','baseline-images','corpus']:p.add_argument('--'+n,type=Path,required=True)
    args=p.parse_args();base=json.loads((ROOT/'reports/nb1-gain-admission.json').read_text())
    for n,h in base['sourceSha256'].items():assert hashlib.sha256((args.baseline_root/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==h,n
    prepare_data(args.corpus);out=ROOT/'build/nb1-zero-screen';out.mkdir(parents=True,exist_ok=True)
    path=ROOT/'src/lowrate_excitation.h';original=path.read_bytes();before=(args.baseline_root/'src/lowrate_excitation.h').read_text();rows=[]
    try:
        for name in ['before','root-only','loop','split','common-fold']:
            text=variant(before,name);path.write_bytes(text.encode())
            for label,(width,wb) in PROFILES.items():
                folder=out/name/label;filename='wb.bin' if wb else 'speex-test.bin'
                if name=='before':
                    parent=args.baseline_images/label;expected=json.loads((ROOT/'reports'/('nb1-gain-after-'+label+'.json')).read_text())
                    assert hashlib.sha256((parent/filename).read_bytes()).hexdigest()==expected['binarySha256']
                    shutil.copytree(parent,folder,dirs_exist_ok=True)
                else:(build_wb.avr if wb else build.avr)(args.avr_gcc,backend='asm',packet_bytes=width,enable_nb4=True,low_rates=7,destination=folder)
                data=ROOT/'build/nb1-gain-screen-data'/label
                with (folder/'screen.log').open('w',encoding='utf-8') as log:
                    subprocess.run([args.node,ROOT/'tests'/('verify_wb.mjs' if wb else 'verify_avr.mjs'),'--firmware',folder,
                        '--streams',data/'streams','--oracle',data/'oracle','--packet-timing',*([] if wb else ['--verify-reset'])],
                        stdout=log,stderr=subprocess.STDOUT,check=True)
                report=json.loads((folder/('verification.json' if wb else 'avr-verification.json')).read_text())
                trace=json.loads((folder/'packet-timing.json').read_text());assert trace['frames']==report['frames']==384
                rows.append(dict(variant=name,profile=label,sourceSha256=hashlib.sha256(text.encode()).hexdigest(),binarySha256=report['binarySha256'],
                    meanCycles=sum(sum(r['cycles']) for r in trace['streams'])/384,flashBytes=report['flashBytes'],staticSramBytes=report['staticSramBytes'],
                    peakStack=report.get('peakStack',2303-report.get('minStackPointer',2303)),pcmExact=True,resetExact=True))
                print('PASS',json.dumps(rows[-1]),flush=True)
    finally:path.write_bytes(original)
    (out/'summary.json').write_bytes((json.dumps(dict(scope='384-frame complete ASM layout screens; no C decoder/IRQ',
        baselineSourceVerified=True,rows=rows),indent=2)+'\n').encode())


if __name__=='__main__':main()

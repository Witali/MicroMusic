#!/usr/bin/env python3
"""Reproduce opt-in AVR5 IRQ profiles on retained A3 streams and long repeats.

Media remain external/ignored. The previous A3 report verifies each input hash.
Retain only the numeric report in Git. Optional private cases are marked training.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from lpx4 import encode, decode
from profile_avr import run as profile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from fuzzer import gen
from l3av_parse import unpack


def run(previous_report,media,output,report_path,avr_bin,runner,lib=None,wsl=None):
    previous_report,media,output,report_path=map(Path,(previous_report,media,output,report_path))
    previous=json.loads(previous_report.read_text(encoding='utf-8'))
    output.mkdir(parents=True,exist_ok=True);report_path.parent.mkdir(parents=True,exist_ok=True)
    report={'baseline_report_sha256':hashlib.sha256(previous_report.read_bytes()).hexdigest(),
            'profile':'ATmega328P 16 MHz / 8 kHz, -Os, explicit AVR5 ASM, 512-byte queue, 384-sample prefill',
            'cases':[],'fallback_cases':[]}

    def measure(key,source,category,asm=True,recipe=None):
        result=profile(source,output/key,avr_bin,runner,lib,wsl,enable_asm=asm)
        result.update(id=key,category=category)
        if recipe:result['recipe']=recipe
        report['cases' if asm else 'fallback_cases'].append(result)
        report_path.write_bytes((json.dumps(report,indent=2)+'\n').encode())
        print(key,round(result['mean_decode_wall_cycles'],2),'cycles/sample',
              result['underruns'],'underruns','exact',result['pwm_native_exact'],flush=True)
        if asm and (result['underruns'] or not result['min_queue_before_producer_eos'] or result['flash_bytes']>32768):
            raise AssertionError('AVR5 real-time profile failed: '+key)

    available={}
    for case in previous['cases']:
        key=case['id'];source=media/key/'global.l4hy'
        if not source.exists() and key in ('chego','otvechaesh'):continue
        blob=source.read_bytes()
        if hashlib.sha256(blob).hexdigest()!=case['output_sha256']:raise ValueError('Input hash mismatch: '+key)
        available[key]=blob
        measure(key,source,'training' if key in ('chego','otvechaesh') else 'corpus')
    for key,count,prefix in [('ru_kak',64000,8000),('en_intro',64000,24000),('chego',32000,9600)]:
        if key not in available:continue
        blob=available[key];frames,blocks,_=decode(blob)
        header=bytearray(blob[:20]);header[:5]=b'L3AV\x01';struct.pack_into('<I',header,8,count)
        doc={'raw':bytes(header),'sampleCount':count,
             'frames':[frames[i%(prefix//160)] for i in range(count//160)],
             'blocks':[blocks[i%(prefix//80)] for i in range(count//80)]}
        target=output/(key+'-long.l4hy');target.write_bytes(encode(doc,fast=True)[0])
        measure(key+'-long',target,'repeated training' if key=='chego' else 'repeated corpus',
                recipe={'source_case':key,'source_prefix_samples':prefix,'result_samples':count,
                        'repeat_frames_and_blocks':True,'fast_repack':True})
    # Nonzero Q14 filters, varied LSF/code widths, partial blocks and pitch modes.
    seed=20261027;made=0
    while made<8:
        doc=unpack(gen(seed));seed+=1
        if doc['sampleCount']<800:continue
        target=output/('generated-'+str(made)+'.l4hy');target.write_bytes(encode(doc,fast=True)[0])
        measure('generated-'+str(made),target,'synthetic correctness',recipe={'fuzzer_seed':seed-1})
        made+=1
    source=ROOT/'examples/SYNTHETIC_CELP_BUDGET/synthetic_celp_budget.l4hy'
    measure('sparse-synthetic',source,'synthetic sparse correctness')
    for key in ('ru_kak','synthetic_music','chego'):
        if key in available:measure(key+'-c',media/key/'global.l4hy','explicit C fallback',asm=False)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('previous_report',type=Path);ap.add_argument('media',type=Path)
    ap.add_argument('output',type=Path);ap.add_argument('report',type=Path)
    ap.add_argument('--avr-bin',type=Path,required=True);ap.add_argument('--sim-runner',type=Path,required=True)
    ap.add_argument('--sim-lib-dir',type=Path);ap.add_argument('--wsl')
    a=ap.parse_args();run(a.previous_report,a.media,a.output,a.report,a.avr_bin,a.sim_runner,a.sim_lib_dir,a.wsl)

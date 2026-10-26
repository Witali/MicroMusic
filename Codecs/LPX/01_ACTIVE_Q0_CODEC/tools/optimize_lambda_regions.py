#!/usr/bin/env python3
"""Experimental LPX4 region-wise rate reallocation; encoder only.

Computes costly per-region bit-allocation alternatives on PC, not AVR.
Tries beneficial low-lambda + offsetting high-lambda pairs and verifies actual
L4HY size and integer C++ PCM16 against the ORIGINAL baseline.
"""
from __future__ import annotations
import argparse, hashlib, json, tempfile, time, sys
from pathlib import Path
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'encoder_vbr'/'tools'))
from fast_vbr import Prepared,make_fast
from l3av_parse import unpack
from lpx4 import encode as pack
from tune_pcm16 import read_wav16,metrics
from batch_decoder import BatchSession


def run(data:Path,original:Path,lambda_base:float,output:Path,
        group_size=4,max_pairs=80,stoi_min_delta=0.0):
    t0=time.perf_counter();reference=read_wav16(data/'reference.wav')
    x,rate=sf.read(str(data/'reference.wav'))
    if rate!=8000:raise ValueError('Expected 8kHz reference')
    context=Prepared(x,data/'source_lsf_co.json',data/'source_coeff_trace.csv',data/'source_legacy.lpx3')
    nblocks=len(context.blocks);ngroups=(nblocks+group_size-1)//group_size
    baseline=original.read_bytes()
    if int.from_bytes(baseline[8:12],'little')!=len(reference):raise ValueError('Bad baseline')
    mods=np.ones(ngroups)
    with tempfile.TemporaryDirectory() as td,BatchSession('batch') as batch:
        file=Path(td)/'current.l3av'
        def generate(settings):
            block_lam=np.repeat(settings,group_size)[:nblocks]*lambda_base
            make_fast(x,data/'source_lsf_co.json',data/'source_coeff_trace.csv',
                      data/'source_legacy.lpx3',file,lambda_base,
                      context=context,block_lambdas=block_lam)
            blob,*_=pack(unpack(file.read_bytes()),fast=True)
            return blob
        baseline_pcm=batch.decode_one_s16(baseline,len(reference));base=metrics(reference,baseline_pcm)
        base_file=generate(mods);base_gen=metrics(reference,batch.decode_one_s16(base_file,len(reference)))
        options=[]
        for group in range(ngroups):
            for factor in (0.60,0.75,0.85,1.15,1.35,1.65,2.0):
                settings=mods.copy();settings[group]=factor
                blob=generate(settings)
                if blob==base_file:continue
                pcm=batch.decode_one_s16(blob,len(reference))
                if pcm is None:continue
                score=metrics(reference,pcm,False)
                options.append(dict(group=group,factor=factor,bytes=len(blob),
                     snr=score['pcm16_snr_db'],
                     snr_difference=score['pcm16_snr_db']-base_gen['pcm16_snr_db'],
                     byte_delta=len(blob)-len(base_file)))
        savings=sorted((a for a in options if a['byte_delta']<0),
                       key=lambda a:(a['snr_difference']/(-a['byte_delta']),-a['byte_delta']),reverse=True)[:15]
        quality=sorted((a for a in options if a['byte_delta']>0 and a['snr_difference']>0),
                       key=lambda a:a['snr_difference']/a['byte_delta'],reverse=True)[:15]
        trial_settings=[];used=set()
        for gain in quality:
            for save in savings:
                if save['group']==gain['group']:continue
                if gain['byte_delta']+save['byte_delta']>len(baseline)-len(base_file)+60:continue
                key=(gain['group'],gain['factor'],save['group'],save['factor'])
                if key in used:continue
                trial_settings.append((gain,save));used.add(key)
        trial_settings=trial_settings[:max_pairs]
        best=baseline;bestpcm=baseline_pcm;bestscore=base;win={'mode':'baseline'}
        if len(base_file)<=len(baseline) and (base_gen['pcm16_snr_db'],base_gen['stoi_pcm16'])>(bestscore['pcm16_snr_db'],bestscore['stoi_pcm16']) and base_gen['stoi_pcm16']>=base['stoi_pcm16']-stoi_min_delta:
            best=base_file;bestscore=base_gen;bestpcm=batch.decode_one_s16(best,len(reference));win={'mode':'uniform_lambda'}
        for idx,(gain,save) in enumerate(trial_settings):
            settings=mods.copy();settings[gain['group']]=gain['factor'];settings[save['group']]=save['factor']
            candidate=generate(settings)
            if len(candidate)>len(baseline):continue
            pcm=batch.decode_one_s16(candidate,len(reference))
            if pcm is None:continue
            q=metrics(reference,pcm)
            if q['stoi_pcm16']>=base['stoi_pcm16']-stoi_min_delta and (q['pcm16_snr_db'],q['stoi_pcm16'])>(bestscore['pcm16_snr_db'],bestscore['stoi_pcm16']):
                best,bestscore,bestpcm=candidate,q,pcm
                win={'mode':'lambda_pair','gain':gain,'save':save}
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_bytes(best)
        output.with_suffix('.pcm16le').write_bytes(bestpcm.astype('<i2').tobytes())
        report={'baseline_bytes':len(baseline),'final_bytes':len(best),
                'baseline_quality':base,'optimized_quality':bestscore,
                'uniform_lambda_quality':base_gen,
                'uniform_lambda_bytes':len(base_file),'group_size':group_size,
                'regions':ngroups,'single_region_trials':len(options),
                'pair_trials':len(trial_settings),'selected':win,
                'changed':best!=baseline,
                'original_hash':hashlib.sha256(baseline).hexdigest(),
                'final_hash':hashlib.sha256(best).hexdigest(),
                'elapsed_s':time.perf_counter()-t0,
                'note':'Only PC encoder changes, AVR decoder and format untouched'}
        output.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('data_dir',type=Path);p.add_argument('baseline_l4hy',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--lambda-base',type=float,required=True)
    p.add_argument('--group-size',type=int,default=4)
    p.add_argument('--max-pairs',type=int,default=80)
    o=p.parse_args()
    res=run(o.data_dir,o.baseline_l4hy,o.lambda_base,o.output,o.group_size,o.max_pairs)
    print(json.dumps({k:v for k,v in res.items() if k not in ('selected',)},indent=2,ensure_ascii=False))
if __name__=='__main__':main()

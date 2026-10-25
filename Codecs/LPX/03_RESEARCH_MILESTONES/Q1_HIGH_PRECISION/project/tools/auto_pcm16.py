#!/usr/bin/env python3
"""Size-capped rate/distortion LPX4 encoder optimizing signed PCM16 (not PWM).

Encodes several offline lambda candidates, evaluates C++ fixed-point PCM16,
rejects quality/bitstream size regressions and optionally tunes fixed-width
pre/bright Q14 fields. Nothing in this search runs on the microcontroller.
"""
from __future__ import annotations
import argparse, tempfile, json, hashlib, sys, time, subprocess
from pathlib import Path
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'encoder_vbr'/'tools'))
from encode_vbr_fixedexact import make as make_l3av
from fast_vbr import Prepared
from lpx4 import encode as make_lpx4
from l3av_parse import unpack
from batch_decoder import BatchSession
from tune_pcm16 import read_wav16,metrics,tune

ROOT=Path(__file__).resolve().parents[1]

def select(wav,source,analysis,trace,legacy,baseline,output,values,
           stoi_drop=0.0002,snr_drop=0.0,tune_header=True,header_trials=180,max_growth_pct=0.0,
           metrics_decoder=None,max_cost_growth=0.05):
    start=time.perf_counter()
    ref=read_wav16(wav)
    if not 0<=max_growth_pct<=1:raise ValueError("max_growth_pct must be in [0,1]")
    audio,rate=sf.read(str(wav))
    if rate!=8000 or np.ndim(audio)!=1 or len(ref)!=len(audio):raise ValueError('Expected mono PCM16/8kHz')
    old=baseline.read_bytes();limit=int(np.floor(len(old)*(1.0+max_growth_pct)+1e-9))
    expected=int.from_bytes(old[8:12],'little')
    if expected!=len(ref):raise ValueError('Reference length does not match LPX4 header')
    context=Prepared(audio,analysis,trace,legacy)
    all_options=[];generated=[]
    def cost_for(data:bytes,folder:Path):
        if metrics_decoder is None:return None
        f=folder/'cost_candidate.l4hy';f.write_bytes(data)
        result=subprocess.run([str(metrics_decoder.resolve()),str(f)],capture_output=True,text=True,check=True)
        return json.loads(result.stdout)
    def cost_ok(candidate,base):
        if base is None or candidate is None:return True
        for key in ('bit_calls','max_bit_calls_80','max_bit_calls_160'):
            if candidate[key]>base[key]*(1.0+max_cost_growth)+1.0:return False
        if candidate['max_bit_calls_sample']>base['max_bit_calls_sample']+8:return False
        if candidate['lsf_converts']>base['lsf_converts']:return False
        return True
    with tempfile.TemporaryDirectory(prefix='micromusic16_') as td:
        tmp=Path(td)
        for lamb in values:
            encoded=tmp/'candidate.l3av'
            try:
                make_l3av(audio,analysis,trace,legacy,encoded,float(lamb),fast=True,context=context)
                blob,meta,chunks,recovered=make_lpx4(unpack(encoded.read_bytes()),float('inf'),fast=True)
                generated.append((lamb,blob))
            except Exception as exc:
                all_options.append(dict(lambda_value=lamb,error=str(exc)))
        with BatchSession('batch') as batch:
            baseline_pcm=batch.decode_one_s16(old,len(ref))
            if baseline_pcm is None:raise RuntimeError('Baseline C++ decode failed')
            ref_quality=metrics(ref,baseline_pcm)
            baseline_cost=cost_for(old,tmp)
            best_blob=old; best_pcm=baseline_pcm; best_quality=ref_quality
            all_options.append(dict(lambda_value=None,size_bytes=len(old),**ref_quality,accepted=True,label='baseline',decode_cost_proxy=baseline_cost))
            for j in range(0,len(generated),16):
                group=generated[j:j+16]
                outs=batch.decode_many_s16([b for _,b in group],len(ref))
                for (lamb,blob),pcm in zip(group,outs):
                    if pcm is None:
                        all_options.append(dict(lambda_value=lamb,error='decoder rejected candidate'));continue
                    met=metrics(ref,pcm)
                    decode_cost=cost_for(blob,tmp)
                    accepted=(len(blob)<=limit and
                              met['stoi_pcm16']>=ref_quality['stoi_pcm16']-stoi_drop and
                              met['pcm16_snr_db']>=ref_quality['pcm16_snr_db']-snr_drop and
                              cost_ok(decode_cost,baseline_cost))
                    all_options.append(dict(lambda_value=lamb,size_bytes=len(blob),**met,accepted=accepted,decode_cost_proxy=decode_cost))
                    if accepted and (met['pcm16_snr_db'],met['stoi_pcm16'],-len(blob))>(best_quality['pcm16_snr_db'],best_quality['stoi_pcm16'],-len(best_blob)):
                        best_blob=blob;best_pcm=pcm;best_quality=met
            candidate_winner=best_quality.copy()
            q14_info=None
            if tune_header:
                optimized,highres,q14_info=tune(best_blob,ref,batch,header_trials,stoi_drop)
                q=metrics(ref,highres)
                if (q['pcm16_snr_db']>=ref_quality['pcm16_snr_db']-snr_drop and
                    q['stoi_pcm16']>=ref_quality['stoi_pcm16']-stoi_drop and
                    q['pcm16_snr_db']>best_quality['pcm16_snr_db']+1e-9 and
                    cost_ok(cost_for(optimized,tmp),baseline_cost)):
                    best_blob=optimized; best_pcm=highres; best_quality=q
            final_cost=cost_for(best_blob,tmp)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(best_blob)
    report=dict(sample_rate=8000,samples=len(ref),reference='source mono PCM16 WAV',
                reconstruction='signed PCM16 from post-LPC/postfilter Q14 × 2, before PWM',
                selection='max PCM16-SNR; cap final stream size and allow at most specified STOI loss',
                baseline_size=len(old),max_size_bytes=limit,max_growth_pct=max_growth_pct,final_size=len(best_blob),quality_baseline=ref_quality,
                quality_selected=best_quality,after_lambda=candidate_winner,
                baseline_cost_proxy=baseline_cost,final_cost_proxy=final_cost,
                max_cost_proxy_growth=max_cost_growth,
                lambda_candidates=all_options,
                q14_tuning=q14_info,
                output_sha256=hashlib.sha256(best_blob).hexdigest(),
                output_pcm16_sha256=hashlib.sha256(best_pcm.astype('<i2').tobytes()).hexdigest(),
                speed_sec=time.perf_counter()-start,
                avr_timing='Not measured. Search runs only on host; decoder arithmetic unchanged.')
    (output.parent/(output.stem+'_report.json')).write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    (output.parent/(output.stem+'.pcm16le')).write_bytes(best_pcm.astype('<i2').tobytes())
    return report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--data-dir',type=Path,required=True,help='Folder with reference.wav / source_v1.l3av / source_lsf_co.json / source_coeff_trace.csv / source_legacy.lpx3 / after.l4hy')
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--lambdas',default='0.0008,0.0009,0.001,0.0011,0.00115,0.0012,0.00125,0.0013,0.00135,0.0014,0.00145,0.0015,0.0016,0.0018')
    ap.add_argument('--max-stoi-drop',type=float,default=.0002)
    ap.add_argument('--max-snr-drop',type=float,default=0.0)
    ap.add_argument('--header-trials',type=int,default=180)
    ap.add_argument('--max-growth-pct',type=float,default=0.0,help='0 = no size growth, 0.10 = allow up to 10 percent larger compressed stream')
    ap.add_argument('--metrics-decoder',type=Path,help='instrumented C++ decoder; cap worst 160-sample read-bit activity')
    ap.add_argument('--max-cost-growth',type=float,default=0.05)
    o=ap.parse_args();root=o.data_dir
    values=[float(v) for v in o.lambdas.split(',')]
    r=select(root/'reference.wav',root/'source_v1.l3av',root/'source_lsf_co.json',
         root/'source_coeff_trace.csv',root/'source_legacy.lpx3',root/'after.l4hy',
         o.output,values,o.max_stoi_drop,o.max_snr_drop,header_trials=o.header_trials,max_growth_pct=o.max_growth_pct,
         metrics_decoder=o.metrics_decoder,max_cost_growth=o.max_cost_growth)
    print(json.dumps({k:v for k,v in r.items() if k not in ('lambda_candidates','q14_tuning')},indent=2,ensure_ascii=False))
if __name__=='__main__': main()

#!/usr/bin/env python3
"""MicroMusic LPX4 Q0: full rate-locked perceptual encoder optimization.

Stage A: per-region lambda allocation (new VBR streams encoded on host PC)
Stage B: local LSF / excitation fixed-codeword analysis-by-synthesis
Stage C: Q14 header adjustment with exact C++ PCM16 feedback
Only the *encoder* runs more computations. Original LPX4 AVR decoder unchanged.
"""
from __future__ import annotations
import argparse,hashlib,json,sys,tempfile, shutil, time, wave
from pathlib import Path
import numpy as np
from batch_decoder import BatchSession
from tune_pcm16 import read_wav16,metrics
from optimize_lambda_regions import run as optimize_regions
from optimize_old_lpc import run as optimize_fixed,probe


def cost_within(source,final,cap):
    keys=('bit_calls','max_bit_calls_sample','max_bit_calls_80','max_bit_calls_160')
    return all(final[k]<=source[k]*(1+cap)+1 for k in keys) and final['lsf_converts']<=source['lsf_converts']


def run(work_dir:Path,baseline_path:Path,output:Path,lamb:float,group=4,
        max_pairs=100,lsf_trials=3000,excite_trials=5500,header_trials=160,
        cost_probe=None,cost_growth=0.05):
    start=time.perf_counter()
    if not (0<lamb<1):raise ValueError('lambda must be positive and less than 1')
    reference=read_wav16(work_dir/'reference.wav')
    original=baseline_path.read_bytes()
    if int.from_bytes(original[8:12],'little')!=len(reference):raise ValueError('Input/recording length mismatch')
    with BatchSession('batch') as bt:
        y=bt.decode_one_s16(original,len(reference))
        if y is None:raise ValueError('Decoder rejected baseline')
        base_m=metrics(reference,y)
    baseline_cost=None
    if cost_probe:
        with tempfile.TemporaryDirectory() as td:
            baseline_cost=probe(cost_probe,original,Path(td))
    with tempfile.TemporaryDirectory(prefix='lpx4_old_enc_') as td:
        td=Path(td)
        intermediate=td/'region.l4hy'
        region=optimize_regions(work_dir,baseline_path,lamb,intermediate,group,max_pairs)
        final_tmp=td/'stage_b.l4hy'
        outcome=optimize_fixed(intermediate,work_dir/'reference.wav',final_tmp,
            lsf_trials=lsf_trials,excitation_trials=excite_trials,
            header_trials=header_trials,probe_path=cost_probe)
        candidate=final_tmp.read_bytes()
        cand_m=outcome['optimized_pcm16']
        cost_candidate=outcome.get('decoder_cost_calls_after')
        checks={'size':len(candidate)<=len(original),
             'snr':cand_m['pcm16_snr_db']>=base_m['pcm16_snr_db']-1e-10,
             'stoi':cand_m['stoi_pcm16']>=base_m['stoi_pcm16']-1e-10,
             'cost_proxy':baseline_cost is None or cost_within(baseline_cost,cost_candidate,cost_growth)}
        if all(checks.values()):
            result=candidate;selected=cand_m;decision='regional + fixed-bit refinements'
        else:
            result=original;selected=base_m;decision='retained original (failed safety gate)'
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_bytes(result)
        with BatchSession('batch') as bt:
            pcm=bt.decode_one_s16(result,len(reference))
            if pcm is None:raise AssertionError('Validation decode failure')
        sound=pcm.astype('<i2').tobytes()
        output.with_suffix('.pcm16le').write_bytes(sound)
        with wave.open(str(output.with_suffix('.wav')),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(sound)
    overall=dict(input_bytes=len(original),output_bytes=len(result),
        input_pcm16=base_m,output_pcm16=selected,chosen=decision,
        gates=checks,lambda_base=lamb,group_size=group,
        regional_search=region,fixedfield_search=outcome['steps'],
        cost_instrument_before=baseline_cost,
        cost_instrument_final=cost_candidate,
        avr_cycles='Not measured on 16 MHz AVR; cost instrument is not a cycle counter',
        decoder_firmware='Unchanged LPX4 Q0, 8 kHz, no PWM used in quality metric',
        sha256_input=hashlib.sha256(original).hexdigest(),
        sha256_output=hashlib.sha256(result).hexdigest(),
        elapsed_s=round(time.perf_counter()-start,3))
    output.with_suffix('.json').write_text(json.dumps(overall,ensure_ascii=False,indent=2)+'\n')
    return overall


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-dir',type=Path,required=True,help='reference.wav + source_lsf_co.json + source_coeff_trace.csv + source_legacy.lpx3')
    ap.add_argument('--baseline',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--lambda-base',type=float,required=True)
    ap.add_argument('--group-size',type=int,default=4)
    ap.add_argument('--max-pairs',type=int,default=100)
    ap.add_argument('--lsf-trials',type=int,default=3000)
    ap.add_argument('--excitation-trials',type=int,default=5500)
    ap.add_argument('--header-trials',type=int,default=160)
    ap.add_argument('--cost-probe',type=Path)
    ap.add_argument('--max-cost-growth',type=float,default=.05)
    v=ap.parse_args()
    res=run(v.data_dir,v.baseline,v.output,v.lambda_base,v.group_size,v.max_pairs,
        v.lsf_trials,v.excitation_trials,v.header_trials,v.cost_probe,v.max_cost_growth)
    print(json.dumps({k:res[k] for k in ('input_bytes','output_bytes','input_pcm16','output_pcm16','chosen','gates','elapsed_s')},indent=2,ensure_ascii=False))
if __name__=='__main__':main()

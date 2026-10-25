#!/usr/bin/env python3
"""MicroMusic LPC Q0: optimize *encoder*, keep AVR decoder frozen.

Input L4HY v2 + source mono 8 kHz 16-bit WAV; keeps the compressed stream
EXACTLY the same number of bytes, emits 16-bit reconstructed WAV, diagnostics.
Every acceptance depends on the unmodified integer C++ decoder output.
Does not change Q1, PWM or AVR firmware; no extra per-sample AVR operations.
"""
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys,time,wave
from pathlib import Path
import numpy as np
from batch_decoder import BatchSession
from tune_pcm16 import read_wav16,metrics,tune
from refine_lsf_pcm16 import optimize as lsf_opt
from refine_excitation_pcm16 import optimize as excitation_opt


def probe(probe_path,blob,work:Path):
    target=work/'to_probe.l4hy'
    target.write_bytes(blob)
    completed=subprocess.run([str(probe_path.resolve()),str(target)],capture_output=True,text=True,check=True)
    return json.loads(completed.stdout)


def run(source:Path,wav:Path,out:Path,lsf_trials=3000,excitation_trials=5000,
        stoi_tolerance=0.0,header_trials=120,probe_path=None):
    if lsf_trials<0 or excitation_trials<0 or header_trials<0:raise ValueError('Negative trial count')
    data=source.read_bytes();ref=read_wav16(wav)
    if int.from_bytes(data[8:12],'little')!=len(ref):
        raise ValueError('Mismatch between source WAV and LPX4 stream length')
    out.parent.mkdir(parents=True,exist_ok=True)
    old_hash=hashlib.sha256(data).hexdigest()
    t0=time.perf_counter()
    steps=[]
    with BatchSession('batch') as decoder:
        first=decoder.decode_one_s16(data,len(ref))
        if first is None:raise ValueError('C++ decoder rejected input')
        before=metrics(ref,first)
        best_data=data;best_pcm=first;best=before
        if lsf_trials:
            newer,pcm,r=lsf_opt(best_data,ref,decoder,max_trials=lsf_trials,
                step_sizes=(32,16,8,4,2,1),passes=1,min_stoi_delta=-stoi_tolerance)
            best_data,best_pcm,best=newer,pcm,metrics(ref,pcm)
            steps.append({'step':'spectral LSF10 + raw-delta search',
                'trials':r['meta']['trials'],'changes':len(r['accepted_changes']),'metrics':best})
        if excitation_trials:
            newer,pcm,r=excitation_opt(best_data,ref,decoder,max_trials=excitation_trials,
                  max_delta=4,per_40=16,passes=1,stoi_drop=stoi_tolerance)
            best_data,best_pcm,best=newer,pcm,metrics(ref,pcm)
            steps.append({'step':'rate-locked excitation codeword search',
                'trials':r['trials'],'changes':r['accepted'],'metrics':best})
        if header_trials:
            newer,pcm,r=tune(best_data,ref,decoder,trial_limit=header_trials,
                stoi_tolerance=stoi_tolerance)
            quality=metrics(ref,pcm)
            if quality['pcm16_snr_db']+1e-11>=best['pcm16_snr_db'] and quality['stoi_pcm16']>=before['stoi_pcm16']-stoi_tolerance-1e-12:
                best_data,best_pcm,best=newer,pcm,quality
            steps.append({'step':'existing Q14 header fields',
                'trials':r['trials'],'changes':len(r['accepted_changes']),'metrics':best})
        # Be conservative: reject marginal candidates outside the GLOBAL STOI gate.
        if best['pcm16_snr_db']+1e-11<before['pcm16_snr_db'] or best['stoi_pcm16']<before['stoi_pcm16']-stoi_tolerance-1e-11:
            best_data,best_pcm,best=data,first,before
        if len(data)!=len(best_data):raise AssertionError('Rate-locked constraint violated')
        independent=decoder.decode_one_s16(best_data,len(ref))
        if independent is None or not np.array_equal(best_pcm,independent):
            raise AssertionError('Independent C++ re-decode mismatch')
    # Reparse Python bitstream independently; preserves bitstream syntax.
    from lpx4 import decode as py_decode
    bfr,bbl,bq=py_decode(data)
    afr,abl,aq=py_decode(best_data)
    if (len(bfr),len(bbl),len(bq))!=(len(afr),len(abl),len(aq)):
        raise AssertionError('Recompression changed audio structure')
    p16=best_pcm.astype('<i2').tobytes()
    out.write_bytes(best_data)
    (out.with_suffix('.pcm16le')).write_bytes(p16)
    with wave.open(str(out.with_suffix('.wav')),'wb') as wf:
        wf.setnchannels(1);wf.setsampwidth(2);wf.setframerate(8000);wf.writeframes(p16)
    report=dict(name=source.name,baseline_bytes=len(data),output_bytes=len(best_data),
                input_sha256=old_hash,output_sha256=hashlib.sha256(best_data).hexdigest(),
                baseline_pcm16=before,optimized_pcm16=best,steps=steps,
                changed_pcm_sha256=hashlib.sha256(p16).hexdigest(),
                duration_seconds=len(ref)/8000,
                elapsed_seconds=round(time.perf_counter()-t0,3),
                contract='same L4HY v2 format, same byte length, original AVR C++ source untouched',
                quality_note='In-sample training, no blind-listening or unseen-speaker evaluation',
                timing_note='No AVR cycle-accurate timing or hardware underrun test')
    if probe_path:
        old=probe(probe_path,data,out.parent);new=probe(probe_path,best_data,out.parent)
        report['decoder_cost_calls_before']=old;report['decoder_cost_calls_after']=new
        unchanged=('samples','bit_calls','max_bit_calls_sample','max_bit_calls_80',
                   'max_bit_calls_160','rom_reads','lsf_converts')
        report['decode_cost_proxy_unchanged']=all(old.get(k)==new.get(k) for k in unchanged)
        # Some command sequences may change nonlinear branch paths; this proxy is
        # not a proof of identical or bounded ATmega328P CPU cycles.
    out.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path);p.add_argument('reference_wav',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--lsf-trials',type=int,default=3000)
    p.add_argument('--excitation-trials',type=int,default=5000)
    p.add_argument('--header-trials',type=int,default=120)
    p.add_argument('--max-stoi-drop',type=float,default=0.0)
    p.add_argument('--cost-probe',type=Path)
    o=p.parse_args()
    if not 0<=o.max_stoi_drop<=0.01:raise ValueError('Unsafe STOI loss tolerance')
    r=run(o.input,o.reference_wav,o.output,o.lsf_trials,o.excitation_trials,o.max_stoi_drop,o.header_trials,o.cost_probe)
    print(json.dumps({k:v for k,v in r.items() if k not in ('steps',)},indent=2,ensure_ascii=False))
if __name__=='__main__': main()

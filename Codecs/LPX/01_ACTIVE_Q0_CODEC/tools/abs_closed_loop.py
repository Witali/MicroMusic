#!/usr/bin/env python3
"""CELP offline search with actual decoded PCM in the decision loop.

No search, STOI or float code is added to the AVR firmware. Candidates use the
existing LPX4 40-sample pitch+sparse mode and exact fallback. The algorithm
computes candidate quant excitation first and rejects it unless the *real C++
decoder output* passes both PCM distortion and (when a source WAV is supplied)
STOI quality gates. A result not smaller than exact is always rejected.

This intentionally does NOT assert the AVR 16-MHz deadline: hardware cycle
measurements are a separate acceptance gate, documented in README.
"""
import argparse, json, math, subprocess, sys, tempfile, wave, hashlib, time
from pathlib import Path
import numpy as np
from l3av_parse import unpack
from lpx4 import encode
try:from pystoi import stoi
except ImportError:stoi=None
ROOT=Path(__file__).resolve().parent.parent

def build_decoder(output):
    cmd=['g++','-O3','-std=c++11','-DLPX4_ALLOW_SPARSE=1','-I'+str(ROOT/'src'),
         str(ROOT/'src/Lpx4HybridCore.cpp'),str(ROOT/'tests/decode_host.cpp'),'-o',str(output)]
    subprocess.run(cmd,check=True,capture_output=True,text=True)

def wav_truth(path):
    with wave.open(str(path),'rb') as wf:
        assert wf.getframerate()==8000 and wf.getnchannels()==1 and wf.getsampwidth()==2
        pcm=np.frombuffer(wf.readframes(wf.getnframes()),dtype='<i2').astype(np.float64)
    return pcm/32768.0

def main():
    ap=argparse.ArgumentParser(description='Closed-loop CELP candidate selection with C++ PCM feedback')
    ap.add_argument('source',type=Path,help='original L3AV version 1')
    ap.add_argument('output',type=Path)
    ap.add_argument('--truth',type=Path,help='optional original 8k mono s16 WAV for STOI')
    ap.add_argument('--min-pcm-snr',type=float,default=30.0)
    ap.add_argument('--max-stoi-loss',type=float,default=0.001)
    ap.add_argument('--max-peak-delta',type=float,default=8.0,help='max abs PCM difference, in 8-bit LSBs')
    ap.add_argument('--max-local-rms',type=float,default=2.5,help='worst 160-sample RMS PCM difference, 8-bit LSBs')
    ap.add_argument('--min-saving',type=int,default=2,help='net bytes of size gain, rounded to full bytes')
    ap.add_argument('--excitation-snr',type=float,default=12.0)
    ap.add_argument('--candidates',type=int,default=16)
    ap.add_argument('--report',type=Path)
    a=ap.parse_args()
    assert a.min_pcm_snr>=0 and a.max_stoi_loss>=0
    doc=unpack(a.source.read_bytes())
    with tempfile.TemporaryDirectory(prefix='lpx4_abs_') as td:
        work=Path(td);exe=work/'decoder'
        build_decoder(exe)
        def decode(b):
            (work/'tmp.l4hy').write_bytes(b)
            subprocess.run([str(exe),str(work/'tmp.l4hy'),str(work/'tmp.pcm')],check=True,capture_output=True,text=True)
            return np.frombuffer((work/'tmp.pcm').read_bytes(),dtype=np.uint8).astype(np.float64)/128.0-1.0
        start=time.perf_counter()
        exact,_,plain_chunks,_=encode(doc)
        reference=decode(exact)
        truth=wav_truth(a.truth) if a.truth else None
        if truth is not None:
            if stoi is None:raise RuntimeError('pystoi required with --truth')
            assert len(truth)==len(reference)
            base_stoi=float(stoi(truth,reference,8000,extended=False))
        else:base_stoi=None
        approx,_,approx_chunks,_=encode(doc,a.excitation_snr)
        direct={c['position']:c for c in plain_chunks}
        viable=[]
        for c in approx_chunks:
            if c['mode']!='sparse':continue
            saving=direct[c['position']]['bits']-c['bits']
            if saving>5:viable.append((saving,c['position']))
        viable.sort(reverse=True)
        attempts=[];kept=set();best_data=exact;best_pcm=reference;best_stoi=base_stoi
        # Search only a bounded number of most promising 40-sample candidates.
        for _estimated_bits,pos in viable[:a.candidates]:
            trial_data,_,trial_chunks,_=encode(doc,a.excitation_snr,allowed_sparse=kept|{pos})
            trial_modes={c['position']:c['mode'] for c in trial_chunks}
            if trial_modes.get(pos)!='sparse' or len(trial_data)>len(best_data)-a.min_saving:
                attempts.append({'position':pos,'accepted':False,'reason':'not selected or no net byte saving','bytes':len(trial_data)})
                continue
            trial_pcm=decode(trial_data)
            assert len(trial_pcm)==len(reference)
            err=trial_pcm-reference
            snr=10*math.log10(max(np.mean(reference**2),1e-30)/max(np.mean(err**2),1e-30))
            trial_stoi=float(stoi(truth,trial_pcm,8000,extended=False)) if truth is not None else None
            difference=(trial_pcm-reference)*128.0
            peak_delta=float(np.max(np.abs(difference)))
            local_rms=max(float(np.sqrt(np.mean(difference[i:i+160]**2))) for i in range(0,len(difference),160))
            qualifies=(snr>=a.min_pcm_snr and peak_delta<=a.max_peak_delta and
                local_rms<=a.max_local_rms and (base_stoi is None or trial_stoi>=base_stoi-a.max_stoi_loss))
            attempts.append({'position':pos,'accepted':bool(qualifies),'bytes':len(trial_data),
                             'pcm_snr':round(snr,2),'peak_delta':peak_delta,'worst_rms160':round(local_rms,3),'stoi':round(trial_stoi,5) if trial_stoi is not None else None})
            if qualifies:
                kept.add(pos);best_data=trial_data;best_pcm=trial_pcm;best_stoi=trial_stoi
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_bytes(best_data)
        pcmbytes=np.rint(np.clip((best_pcm+1)*128,0,255)).astype(np.uint8).tobytes()
        report=dict(format='L4HY v2',name=a.source.name,baseline_bytes=len(exact),output_bytes=len(best_data),
                exact_pcm_sha256=hashlib.sha256(np.rint(np.clip((reference+1)*128,0,255)).astype(np.uint8).tobytes()).hexdigest(),
                output_pcm_sha256=hashlib.sha256(pcmbytes).hexdigest(),
                exact_stoi=base_stoi,result_stoi=best_stoi,
                selected_sparse_positions=sorted(kept),tests=attempts,
                elapsed_sec=round(time.perf_counter()-start,1),
                policy={'min_pcm_snr_db':a.min_pcm_snr,'max_stoi_loss':a.max_stoi_loss,'max_pcm_peak_delta':a.max_peak_delta,'max_local_rms':a.max_local_rms},
                note='AVR cycle budget not proven until hardware/AVR-instruction simulator timing')
        if a.report:
            a.report.parent.mkdir(parents=True,exist_ok=True)
            a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:report[k] for k in ('name','baseline_bytes','output_bytes','exact_stoi','result_stoi','selected_sparse_positions','elapsed_sec')},ensure_ascii=False))
if __name__=='__main__':main()

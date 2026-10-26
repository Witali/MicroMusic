#!/usr/bin/env python3
"""Deterministic wall-clock comparison of host decoder launches vs native batches.

All timing is inside one warmed Python interpreter; compilation/startup excluded.
Uses synthetic CELP by default. Optionally pass a private test WAV+L4HY.
"""
from __future__ import annotations
import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import warnings
import wave
import numpy as np
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'tools'))
from batch_decoder import BatchSession
from tune_header_fixedrate import run as header_tune
from refine_fixedrate import refine as pulse_tune


def main():
    a=argparse.ArgumentParser()
    a.add_argument('--source',type=Path,default=ROOT/'examples/SYNTHETIC_CELP_BUDGET/synthetic_celp_budget.l4hy')
    a.add_argument('--wav',type=Path,default=None)
    a.add_argument('--mode',choices=['header','pulse'],default='pulse')
    a.add_argument('--trials',type=int,default=150)
    a.add_argument('--repeats',type=int,default=5)
    a.add_argument('--output',type=Path,default=None)
    v=a.parse_args()
    if v.repeats<1 or v.trials<1:raise ValueError('repeats and trials must be positive')
    with tempfile.TemporaryDirectory() as d, BatchSession('batch') as decoder:
        tmp=Path(d)
        host=tmp/'decode_host'
        subprocess.run(['g++','-O3','-std=c++11','-I'+str(ROOT/'src'),
                        str(ROOT/'src/Lpx4HybridCore.cpp'),
                        str(ROOT/'tests/decode_host.cpp'),'-o',str(host)],check=True,capture_output=True)
        if v.wav is None:
            pcm=decoder.decode_one(v.source.read_bytes(),3200)
            if pcm is None:raise RuntimeError('synthetic decoder failed')
            wav=tmp/'reference.wav'
            samples=((pcm.astype(np.int16)-128)*256).astype('<i2')
            with wave.open(str(wav),'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
                w.writeframes(samples.tobytes())
        else:wav=v.wav
        timings={'reference':[],'batch':[]};hashes={}
        # Alternate methods in each repetition to reduce order bias.
        with warnings.catch_warnings(),redirect_stdout(io.StringIO()):
            warnings.simplefilter('ignore',RuntimeWarning)
            for i in range(v.repeats):
                for mode in (['reference','batch'] if i%2==0 else ['batch','reference']):
                    target=tmp/f'{mode}_{i}.l4hy'
                    t0=time.perf_counter()
                    if v.mode=='header':
                        stats=header_tune(v.source,wav,host,target,tmp/f'{mode}_{i}.json',
                                          max_trials=v.trials,
                                          batch_decoder=decoder if mode=='batch' else None)
                    else:
                        stats=pulse_tune(v.source,wav,host,target,max_eval=v.trials,
                                         passes=1,batch_decoder=decoder if mode=='batch' else None)
                    duration=time.perf_counter()-t0
                    timings[mode].append(duration)
                    if mode not in hashes:hashes[mode]=target.read_bytes()
                    if target.read_bytes()!=hashes[mode]:raise AssertionError('method nondeterministic')
        if hashes['reference']!=hashes['batch']:raise AssertionError('PCM/search regression')
        t1=statistics.median(timings['reference']);t2=statistics.median(timings['batch'])
        out={'mode':v.mode,'trials_limit':v.trials,'repeats':v.repeats,
             'source_bytes':v.source.stat().st_size,
             'reference_times_s':timings['reference'],'batch_times_s':timings['batch'],
             'reference_median_s':t1,'batch_median_s':t2,'speedup':t1/t2,
             'identical_l4hy':True,'native_calls':decoder.calls,'native_streams':decoder.streams,
             'note':'Host CPU only; no AVR cycle count. Excludes initial compilation and Python startup.'}
        if v.output:
            v.output.parent.mkdir(parents=True,exist_ok=True)
            v.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__': main()

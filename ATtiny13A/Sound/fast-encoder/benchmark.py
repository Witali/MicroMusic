#!/usr/bin/env python3
"""Compare equivalent C vs Python STOI+spectral evaluations on identical PCM."""
import argparse,json,time
import numpy as np,soundfile as sf
from fast_train import Native,unpack_stream,SOURCE
from quality_reference import ReferenceMetrics

def median_time(fn,reps):
    times=[]
    for _ in range(3):
        start=time.perf_counter()
        for __ in range(reps):fn()
        times.append((time.perf_counter()-start)/reps)
    return float(np.median(times))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--voice',default='chego');a.add_argument('--reps',type=int,default=120);args=a.parse_args()
    b=SOURCE/args.voice
    ref,sr=sf.read(b/'original.wav');assert sr==7500
    f,d=unpack_stream((b/'speech.hq').read_bytes())
    N=Native(ref)
    pcm=N.decode(f,d)
    py=ReferenceMetrics(ref)
    exact=N.metrics(pcm);baseline=py.scores(pcm)
    assert np.allclose(exact,baseline,atol=1e-6,rtol=1e-6),(exact,baseline)
    t_c=median_time(lambda:N.metrics(pcm),args.reps)
    t_py=median_time(lambda:py.scores(pcm),max(10,args.reps//2))
    print(json.dumps(dict(voice=args.voice,pcm_samples=len(pcm),native_ms_per_evaluation=round(1000*t_c,4),python_ms_per_evaluation=round(1000*t_py,4),speedup=round(t_py/t_c,2),native=exact.tolist(),python=baseline),indent=2))
    N.close()

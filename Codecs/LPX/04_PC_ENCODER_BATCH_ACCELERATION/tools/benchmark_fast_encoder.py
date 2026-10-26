#!/usr/bin/env python3
"""Reproducible warm-cache LPX4 mode-selection microbenchmark.

This reports desktop ENCODER throughput only. It does not benchmark AVR cycles.
Use --repeats to mitigate timer noise. All outputs must be bit-identical.
"""
from pathlib import Path
import sys, time, argparse, statistics, hashlib, json
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'tools'))
from l3av_parse import unpack
from lpx4 import encode

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--file',type=Path,default=R/'examples/SYNTHETIC_SOURCE_ONLY/synthetic_v1.l3av')
    a.add_argument('--repeats',type=int,default=5)
    a.add_argument('--json',type=Path)
    v=a.parse_args()
    doc=unpack(v.file.read_bytes())
    # Warm up compiler AND verify output before measuring.
    baseline=encode(doc,fast=False)[0]
    fast=encode(doc,fast=True)[0]
    assert baseline==fast,'accelerated mode selector changed the bitstream'
    trials={'reference':[],'fast':[]}
    for _ in range(v.repeats):
        for key,kw in [('reference',False),('fast',True)]:
            t=time.perf_counter();out=encode(doc,fast=kw)[0]
            elapsed=time.perf_counter()-t
            assert out==baseline
            trials[key].append(elapsed)
    old=statistics.median(trials['reference']);new=statistics.median(trials['fast'])
    report={'input':v.file.name,'samples':doc['sampleCount'],'lpx4_bytes':len(baseline),
        'sha256':hashlib.sha256(baseline).hexdigest(),'reference_median_s':old,
        'fast_median_s':new,'speedup':old/new,'repeats':v.repeats,'detail_s':trials,
        'timing_scope':'only offline L3AV->LPX4 exact encoder, warmed Numba; not end-to-end or AVR'}
    print(json.dumps(report,indent=2))
    if v.json:v.json.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()

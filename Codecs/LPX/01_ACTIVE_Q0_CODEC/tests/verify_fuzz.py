#!/usr/bin/env python3
"""Mutation/reset checks under Linux GCC ASan+UBSan; Windows uses --wsl."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tests')]
from fuzzer import gen
from l3av_parse import unpack
from lpx4 import encode


def run(output,wsl=None,v3_features=0):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    inputs=[];seeds=list(range(20261101,20261113))
    for seed in seeds:
        p=output/(str(seed)+'.l4hy');p.write_bytes(encode(unpack(gen(seed)),fast=True)[0]);inputs.append(p)
        if v3_features:
            from compact_format import pack
            for mask in range(4,125,4):
                if mask&~v3_features:continue
                compact=output/f'{seed}-v3-{mask}.l4hy'
                compact.write_bytes(pack(p.read_bytes(),mask)[0]);inputs.append(compact)
    def path(p):
        p=Path(p).resolve()
        return '/mnt/'+p.drive[0].lower()+'/'+'/'.join(p.parts[1:]) if wsl else str(p)
    prefix=['wsl','-d',wsl,'--'] if wsl else []
    options=['-O1','-g','-std=c++11','-fno-omit-frame-pointer',
             '-fsanitize=address,undefined','-fno-sanitize-recover=all']
    if v3_features:options.append('-DLPX4_V3_FEATURES='+str(v3_features))
    subprocess.run(prefix+['g++',*options,'-I'+path(ROOT/'src'),path(ROOT/'tests/fuzz_decoder.cpp'),
                          path(ROOT/'src/Lpx4HybridCore.cpp'),'-o',path(output/'fuzz')],check=True)
    # Bounded argv also works with Windows CreateProcess / WSL's command limit.
    report={'cases':0,'rejected':0,'sample_capped':0,'reset_exact':True}
    for start in range(0,len(inputs),32):
        result=subprocess.run(prefix+[path(output/'fuzz'),*[path(p) for p in inputs[start:start+32]]],
                              check=True,capture_output=True,text=True)
        part=json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        for key in ('cases','rejected','sample_capped'):report[key]+=part[key]
        report['reset_exact']=report['reset_exact'] and part['reset_exact']
    report.update(compiler=subprocess.check_output(prefix+['g++','--version'],text=True).splitlines()[0],
        compiler_options=options,seeds=seeds,input_streams=len(inputs),v3_features=v3_features,max_samples_per_decode=4096,
        core_sha256=hashlib.sha256((ROOT/'src/Lpx4HybridCore.cpp').read_bytes()).hexdigest(),
        math_header_sha256=hashlib.sha256((ROOT/'src/Lpx4Math.h').read_bytes()).hexdigest(),
        harness_sha256=hashlib.sha256((ROOT/'tests/fuzz_decoder.cpp').read_bytes()).hexdigest())
    (output/'verification.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps(report,indent=2));return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('output',type=Path);ap.add_argument('--wsl')
    ap.add_argument('--v3-features',type=int,default=0)
    a=ap.parse_args();run(a.output,a.wsl,a.v3_features)

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


def run(output,wsl=None):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    inputs=[];seeds=list(range(20261101,20261113))
    for seed in seeds:
        p=output/(str(seed)+'.l4hy');p.write_bytes(encode(unpack(gen(seed)),fast=True)[0]);inputs.append(p)
    def path(p):
        p=Path(p).resolve()
        return '/mnt/'+p.drive[0].lower()+'/'+'/'.join(p.parts[1:]) if wsl else str(p)
    prefix=['wsl','-d',wsl,'--'] if wsl else []
    options=['-O1','-g','-std=c++11','-fno-omit-frame-pointer',
             '-fsanitize=address,undefined','-fno-sanitize-recover=all']
    subprocess.run(prefix+['g++',*options,'-I'+path(ROOT/'src'),path(ROOT/'tests/fuzz_decoder.cpp'),
                          path(ROOT/'src/Lpx4HybridCore.cpp'),'-o',path(output/'fuzz')],check=True)
    result=subprocess.run(prefix+[path(output/'fuzz'),*[path(p) for p in inputs]],check=True,capture_output=True,text=True)
    report=json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    report.update(compiler=subprocess.check_output(prefix+['g++','--version'],text=True).splitlines()[0],
        compiler_options=options,seeds=seeds,max_samples_per_decode=4096,
        core_sha256=hashlib.sha256((ROOT/'src/Lpx4HybridCore.cpp').read_bytes()).hexdigest(),
        math_header_sha256=hashlib.sha256((ROOT/'src/Lpx4Math.h').read_bytes()).hexdigest(),
        harness_sha256=hashlib.sha256((ROOT/'tests/fuzz_decoder.cpp').read_bytes()).hexdigest())
    (output/'verification.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps(report,indent=2));return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('output',type=Path);ap.add_argument('--wsl')
    a=ap.parse_args();run(a.output,a.wsl)

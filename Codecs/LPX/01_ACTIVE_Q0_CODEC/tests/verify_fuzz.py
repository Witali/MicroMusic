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


def run(output,wsl=None,v3_features=0,speech=False,speech_compact=False,compact_only=False,extra_inputs=()):
    if speech_compact and not speech:raise ValueError('Compact speech requires speech')
    if compact_only and not speech_compact:raise ValueError('Compact-only requires compact speech')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    def source_inventory():
        return {p.relative_to(ROOT/'src').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((ROOT/'src').rglob('*')) if p.is_file()}
    source_before=source_inventory()
    harness_before=hashlib.sha256((ROOT/'tests/fuzz_decoder.cpp').read_bytes()).hexdigest()
    driver_before=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    inputs=[];seeds=list(range(20261101,20261113))
    for seed in seeds:
        p=output/(str(seed)+'.l4hy');p.write_bytes(encode(unpack(gen(seed)),fast=True)[0]);inputs.append(p)
        if v3_features:
            from compact_format import pack
            for mask in range(4,125,4):
                if mask&~v3_features:continue
                compact=output/f'{seed}-v3-{mask}.l4hy'
                compact.write_bytes(pack(p.read_bytes(),mask)[0]);inputs.append(compact)
    if speech:
        from test_speech_v4 import fixture
        for profile in (4,6):
            for n in (1,19,20,39,40,159,160,180,200,220,240,260,280,300,319,320,321,500,641,1024):
                p=output/f'speech-{profile}-{n}.l4hy'
                p.write_bytes(fixture(profile,n));inputs.append(p)
                if speech_compact:
                    from speech_compact import repack
                    for enhanced in (False,True):
                        q=output/f'compact-{profile}-{n}-{int(enhanced)}.l4hy'
                        extras=[(i%40,-8 if i&1 else 7) for i in range(((n+319)//320)*8)] if enhanced else None
                        q.write_bytes(repack(p.read_bytes(),extras=extras)[0]);inputs.append(q)
    for index,source in enumerate(extra_inputs):
        p=output/f'extra-{index}.l4hy';p.write_bytes(Path(source).read_bytes());inputs.append(p)
    def path(p):
        p=Path(p).resolve()
        return '/mnt/'+p.drive[0].lower()+'/'+'/'.join(p.parts[1:]) if wsl else str(p)
    prefix=['wsl','-d',wsl,'--'] if wsl else []
    options=['-O1','-g','-std=c++11','-fno-omit-frame-pointer',
             '-fsanitize=address,undefined','-fno-sanitize-recover=all']
    if v3_features:options.append('-DLPX4_V3_FEATURES='+str(v3_features))
    if speech:options.append('-DLPX4_ENABLE_SPEECH=1')
    if speech_compact:options.append('-DLPX4_ENABLE_SPEECH_COMPACT=1')
    if compact_only:options.append('-DLPX4_COMPACT_ONLY=1')
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
    if (source_inventory()!=source_before
            or hashlib.sha256((ROOT/'tests/fuzz_decoder.cpp').read_bytes()).hexdigest()!=harness_before
            or hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=driver_before):
        raise ValueError('Mutation-check sources changed during validation')
    report.update(decoder_source_sha256=source_before,driver_sha256=driver_before,
        core_header_sha256=source_before['Lpx4HybridCore.h'],compiler=subprocess.check_output(prefix+['g++','--version'],text=True).splitlines()[0],
        compiler_options=options,seeds=seeds,input_streams=len(inputs),v3_features=v3_features,speech_enabled=bool(speech),speech_compact_enabled=bool(speech_compact),compact_only=bool(compact_only),extra_inputs=len(extra_inputs),max_samples_per_decode=4096,
        core_sha256=source_before['Lpx4HybridCore.cpp'],
        math_header_sha256=source_before['Lpx4Math.h'],
        harness_sha256=harness_before)
    (output/'verification.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps(report,indent=2));return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('output',type=Path);ap.add_argument('--wsl')
    ap.add_argument('--v3-features',type=int,default=0)
    ap.add_argument('--speech',action='store_true')
    ap.add_argument('--speech-compact',action='store_true')
    ap.add_argument('--compact-only',action='store_true')
    ap.add_argument('--inputs',type=Path,nargs='*',default=())
    a=ap.parse_args();run(a.output,a.wsl,a.v3_features,a.speech,a.speech_compact,a.compact_only,a.inputs)

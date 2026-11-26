"""Build/cache the one-process Long benchmark; never encode corpus audio."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
ACTIVE=ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC'


def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()


def encoded(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')


def linux(path):
    path=Path(path).resolve()
    return '/mnt/'+path.drive[0].lower()+'/'+('/'.join(path.parts[1:])) if os.name=='nt' else str(path)


def launch(distro):return ['wsl','-d',distro,'--'] if os.name=='nt' else []


def build(output,distro='Ubuntu'):
    output=Path(output).resolve();output.relative_to((ROOT/'build').resolve())
    config=ROOT/'web-player/scripts/lib/lpx-build.mjs';text=config.read_text(encoding='utf-8')
    names=re.findall(r"'([^']+\.cpp)'",text.split('export const hostSources=host([')[1].split(']);')[0])
    defines=re.findall(r"'([^']+)'",text.split('export const portableDefines=[')[1].split('];')[0])
    defines+=['LPX_ENCODER_COMPACT_ENSEMBLE=1','LPX_ENCODER_QUALITY_SEARCH=1','LPX_ENCODER_JOINT_REFINEMENT=1']
    production=[ACTIVE/'src/Lpx4HybridCore.cpp',ACTIVE/'host/LpxEncoder.cpp',*(ACTIVE/'host'/n for n in names)]
    inputs=sorted(set(production+[HERE/'benchmark.cpp',config]
        +list((ACTIVE/'host').glob('*.h'))+list((ACTIVE/'host').glob('*.inc'))
        +list((ACTIVE/'src').glob('*.h'))+list((ACTIVE/'src').glob('*.inc'))))
    sources={p.relative_to(ROOT).as_posix():sha(p) for p in inputs}
    options=['-O3','-std=c++11','-ffp-contract=off','-DNDEBUG',*('-D'+d for d in defines)]
    identity=hashlib.sha256(encoded(dict(sources=sources,options=options))).hexdigest()
    folder=output/identity[:20];folder.mkdir(parents=True,exist_ok=True)
    binary=folder/'benchmark';receipt_path=folder/'build-private.json'
    if receipt_path.exists():
        receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
        if receipt['sources']!=sources or receipt['options']!=options or not binary.exists() or sha(binary)!=receipt['binary_sha256']:
            raise RuntimeError('Immutable build cache is inconsistent')
        return receipt_path,receipt,True
    prefix=launch(distro)
    compiler=subprocess.check_output(prefix+['g++','--version'],text=True).splitlines()[0]
    command=['g++',*options,'-include',linux(ACTIVE/'host/LpxHostWorkspace.h'),
        '-I'+linux(ACTIVE/'src'),'-I'+linux(ACTIVE/'host'),
        *(linux(p) for p in production),linux(HERE/'benchmark.cpp'),'-o',linux(binary)]
    completed=subprocess.run(prefix+command,capture_output=True,text=True)
    (folder/'compiler-private.log').write_text(completed.stdout+completed.stderr,encoding='utf-8')
    if completed.returncode:raise RuntimeError('Benchmark compilation failed; see private build log')
    if sources!={p.relative_to(ROOT).as_posix():sha(p) for p in inputs}:
        raise RuntimeError('Compiler inputs changed during build')
    receipt=dict(schema='lpx-audiobook-build-v1',sources=sources,options=options,command=command,
        compiler=compiler,binary=str(binary),binary_sha256=sha(binary),binary_bytes=binary.stat().st_size,
        builder_source_sha256=sha(Path(__file__)),environment=dict(system=platform.system(),machine=platform.machine(),
            logical_cpus=os.cpu_count()),distro=distro)
    receipt_path.write_bytes(encoded(receipt))
    return receipt_path,receipt,False


def verify(receipt):
    if receipt['schema']!='lpx-audiobook-build-v1':raise ValueError('Unknown benchmark build receipt')
    if any(sha(ROOT/name)!=value for name,value in receipt['sources'].items()) or sha(receipt['binary'])!=receipt['binary_sha256']:
        raise ValueError('Frozen benchmark sources/binary changed')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--distro',default='Ubuntu');args=parser.parse_args()
    receipt_path,receipt,reused=build(args.output,args.distro)
    print(json.dumps(dict(status='REUSED' if reused else 'BUILT',receipt=str(receipt_path),binary=receipt['binary'])))

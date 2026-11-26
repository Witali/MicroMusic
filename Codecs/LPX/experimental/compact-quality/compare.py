"""Paired original/fixed P3 at8kHz. No search tuning; media stay below build/."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
ACTIVE=REPO/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
BUILD=REPO/'build/compact-quality'
SOURCE=REPO/'build/local-noise/sources'
LEGACY=BUILD/'LpxLpcRefine.legacy.cpp'
ORIGINAL='c38d113e1c39a5dc0701b5cec87237c9a1611f207f2864e68772eaba684bbfcc'
FIXED='cba09bfaab7092612befeab2e2f5af9304787ad7131efa88740bcb58abb1f8a7'
CLIPS=('chego','otvechaesh','vinni','bread')


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def rel(path): return Path(path).resolve().relative_to(REPO).as_posix()
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    os.replace(temporary,path)


def git(*args):
    try: return subprocess.check_output(['git',*args],cwd=REPO,stderr=subprocess.DEVNULL)
    except (OSError,subprocess.CalledProcessError):
        if str(REPO).startswith('/mnt/'):
            windows=str(REPO)[5].upper()+':/'+str(REPO)[7:]
            return subprocess.check_output(['git.exe','-C',windows,*args],stderr=subprocess.DEVNULL)
        raise


def build(variant):
    fixed=ACTIVE/'host/LpxLpcRefine.cpp'
    if sha(LEGACY)!=ORIGINAL or sha(fixed)!=FIXED:
        raise RuntimeError('Original/fixed source does not match the predeclared hashes')
    revision=git('rev-parse','e467dc9e').decode().strip()
    old=git('show',revision+':Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxLpcRefine.cpp')
    if LEGACY.read_bytes().replace(b'\r\n',b'\n')!=old.replace(b'\r\n',b'\n'):
        raise RuntimeError('Legacy override differs from the original task revision')
    config=REPO/'web-player/scripts/lib/lpx-build.mjs';text=config.read_text()
    names=re.findall(r"'([^']+\.cpp)'",text.split('export const hostSources=host([')[1].split(']);')[0])
    defines=re.findall(r"'([^']+)'",text.split('export const portableDefines=[')[1].split('];')[0])
    production=[ACTIVE/'src/Lpx4HybridCore.cpp',ACTIVE/'host/LpxEncoder.cpp',*(ACTIVE/'host'/name for name in names)]
    inputs=sorted(set(production+list((ACTIVE/'host').glob('*.h'))+list((ACTIVE/'host').glob('*.inc'))+list((ACTIVE/'src').glob('*.h'))+list((ACTIVE/'src').glob('*.inc'))+[config]))
    pinned={}
    for path in inputs:
        if path==fixed: continue
        original=git('show',revision+':'+rel(path)).replace(b'\r\n',b'\n')
        current=path.read_bytes().replace(b'\r\n',b'\n')
        if current!=original: raise RuntimeError('Unrelated production input changed: '+rel(path))
        pinned[rel(path)]=hashlib.sha256(current).hexdigest()
    sources=[LEGACY if variant=='original' and p==fixed else p for p in production]+[HERE/'benchmark.cpp']
    inputs=[p for p in inputs if p!=fixed]+[LEGACY if variant=='original' else fixed,HERE/'benchmark.cpp',Path(__file__).resolve(),HERE/'PROTOCOL.md',REPO/'Codecs/LPX/research/lbg1-2026-11-26/probe.cpp']
    hashes={rel(path):sha(path) for path in inputs}
    binary=BUILD/'bin'/variant;binary.parent.mkdir(parents=True,exist_ok=True)
    command=['g++','-O3','-std=c++11','-ffp-contract=off','-DNDEBUG',*('-D'+d for d in defines),'-include',rel(ACTIVE/'host/LpxHostWorkspace.h'),'-I'+rel(ACTIVE/'src'),'-I'+rel(ACTIVE/'host'),*(rel(p) for p in sources),'-o',rel(binary)]
    receipt=BUILD/f'build-{variant}.json'
    if receipt.exists():
        prior=json.loads(receipt.read_text())
        if prior.get('sources')==hashes and binary.exists() and prior.get('binary_sha256')==sha(binary): return prior
    subprocess.run(command,cwd=REPO,check=True)
    if hashes!={rel(path):sha(path) for path in inputs}: raise RuntimeError('Input changed while building')
    result=dict(variant=variant,baseline_revision=revision,active_reference='644e19d0',experiment_head=git('rev-parse','HEAD').decode().strip(),compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0],command=command,sources=hashes,unchanged_production_inputs_normalized_sha256=pinned,legacy_cpp_sha256=ORIGINAL,fixed_cpp_sha256=FIXED,binary_sha256=sha(binary))
    write(receipt,result);return result


def run(command):
    done=subprocess.run([str(x) for x in command],cwd=REPO,capture_output=True,text=True)
    if done.returncode: raise RuntimeError('Benchmark failed: '+done.stderr.strip())
    return json.loads(done.stdout)


def artifacts(prefix):
    return {ext:dict(path=rel(Path(str(prefix)+'.'+ext)),sha256=sha(Path(str(prefix)+'.'+ext))) for ext in ('lpx','pcm','model')}


def summary(rows):
    result={}
    for target in ('pcm','pwm'):
        selected=[r for r in rows if r['target']==target]
        if not selected: continue
        totals={}
        for label in ('baseline','raw-fixed'):
            data=[r[label] for r in selected]
            totals[label]=dict(bytes=sum(x['bytes'] for x in data),pcm_sse=sum(x['quality']['pcm_sse'] for x in data),pwm_sse=sum(x['quality']['pwm_sse'] for x in data),mean_stoi=[sum(x['quality']['stoi'][p] for x in data)/len(data) for p in (0,1)],spectral_bits=sum(x['bits']['spectral_total'] for x in data),encode_seconds=sum(x['encode_seconds'] for x in data))
        totals['protected']=dict(bytes=sum(r['protection']['protected_bits']['total']//8 for r in selected),pcm_sse=sum(r['protection']['protected_quality']['pcm_sse'] for r in selected),pwm_sse=sum(r['protection']['protected_quality']['pwm_sse'] for r in selected),mean_stoi=[sum(r['protection']['protected_quality']['stoi'][p] for r in selected)/len(selected) for p in (0,1)])
        result[target]=dict(cases=len(selected),raw_changed=sum(r['protection']['raw_changed'] for r in selected),protected_changed=sum(r['protection']['protected_fix_selected'] for r in selected),outputs=totals)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=('pilot','matrix'),default='pilot')
    parser.add_argument('--build-only',action='store_true')
    args=parser.parse_args()
    builds={version:build(version) for version in ('original','fixed')}
    if args.build_only: print('Built original/fixed P3 executables');return
    manifest_path=SOURCE/'sources.json';manifest=json.loads(manifest_path.read_text());manifest_sha=sha(manifest_path)
    sources={r['clip']:r for r in manifest['sources']}
    for clip in CLIPS:
        path=SOURCE/f'{clip}.source.pcm';row=sources[clip]
        if row['rate']!=8000 or row['pcm_sha256']!=sha(path) or path.stat().st_size!=row['samples']*2: raise RuntimeError('Prepared public source mismatch')
    rows=[];output=HERE/f'results-{args.phase}.json'
    for clip in (CLIPS[:1] if args.phase=='pilot' else CLIPS):
        for target in ('pcm','pwm'):
            name=f'{clip}-p3-{target}';directory=BUILD/'runs'/'frozen-v1'/args.phase/name;directory.mkdir(parents=True,exist_ok=True)
            source=SOURCE/f'{clip}.source.pcm';row=dict(name=name,target=target,source=rel(source),source_sha256=sha(source),artifacts={})
            for version,label in (('original','baseline'),('fixed','raw-fixed')):
                prefix=directory/label
                row[label]=run([BUILD/'bin'/version,'encode',source,prefix,target]);row['artifacts'][label]=artifacts(prefix)
            prefix=directory/'protected'
            row['protection']=run([BUILD/'bin/fixed','compare',source,directory/'baseline.lpx',directory/'raw-fixed.lpx',prefix,target]);row['artifacts']['protected']=artifacts(prefix)
            for receipt in builds.values():
                if receipt['sources']!={p:sha(REPO/p) for p in receipt['sources']}: raise RuntimeError('Build input changed during measurement')
            if sha(manifest_path)!=manifest_sha or sha(source)!=row['source_sha256']: raise RuntimeError('Source/provenance changed during measurement')
            if row['baseline']['policy_budget_C']!=row['raw-fixed']['policy_budget_C'] or row['baseline']['seed_bytes']!=row['raw-fixed']['seed_bytes']: raise RuntimeError('The local scoring fix changed the initial seed/budget')
            rows.append(row)
            result=dict(schema='lpx-p3-canonical-scoring-paired-v1',phase=args.phase,complete=False,builds=builds,source_manifest=manifest,source_manifest_sha256=manifest_sha,protocol_sha256=sha(HERE/'PROTOCOL.md'),method='Fresh P3 calls4 original/fixed at8kHz and preserved level. Only local canonical predictor scoring differs. Raw fixed output is reported even if larger or regressed. Protected output is an additional experimental strict same-B0 admission, not production behavior. Both paths are diagnostics; PWM is inactive for PCM admission. Encode timing excludes the separate initial-seed budget probe and posthoc metrics.',rejection_bits={'size_above_B0':1,'active_SSE_STOI':2,'old_noise':4,'FullBand':8,'pitch':16,'clipping':32,'level':64,'spectrum':128,'stability':256,'complete_selector':512},cases=rows,summary=summary(rows))
            write(output,result)
            print(f"{name}: {row['baseline']['bytes']} -> {row['raw-fixed']['bytes']} bytes; raw_changed={row['protection']['raw_changed']}; protected={row['protection']['protected_fix_selected']}",flush=True)
    result['complete']=True;write(output,result);print(rel(output),flush=True)


if __name__=='__main__':main()

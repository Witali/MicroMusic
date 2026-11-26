"""Distinct P3 grid-neighbor arm; phase1 files and production remain untouched.

Build first, freeze override/tests, then the protocol's Chego pilot and8-case
matrix. Baselines are the SAME stored original outputs from results-matrix.json.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import argparse

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
BUILD=REPO/'build/compact-quality'
SPEC=importlib.util.spec_from_file_location('frozen_p3_pair',HERE/'compare.py')
PAIR=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(PAIR)
PROTOCOL=HERE/'P3_NEIGHBORS_PROTOCOL.md'
OVERRIDE=BUILD/'LpxLpcRefine.p3-grid.cpp'
EXPECTED='b37f6a8d16b969ad1af97350431ed9630cfdc496146d5fbdc5c30961397ac87b'


def generate():
    base=(PAIR.ACTIVE/'host/LpxLpcRefine.cpp').read_bytes()
    if hashlib.sha256(base).hexdigest()!=PAIR.FIXED:raise RuntimeError('Fidelity-fixed production base changed')
    first=b'        for(int field=0;field<10;++field)for(int delta:{-1,1}) {'
    new_first=b'        for(int field=0;field<10;++field)for(int move=0;move<(input.accuracy==3?4:2);++move) {\n            const int delta=input.accuracy==3?(move==0?-4:move==1?-2:move==2?2:4):(move?1:-1);'
    second=b'        int fields=0;for(int k=0;k<10;++k)if(single.spectra[first][k]!=anchor.spectra[first][k])\n            fields+=std::abs(single.spectra[first][k]-anchor.spectra[first][k])==1?1:100;'
    new_second=b'        int fields=0;for(int k=0;k<10;++k)if(single.spectra[first][k]!=anchor.spectra[first][k]) {\n            const int distance=std::abs(single.spectra[first][k]-anchor.spectra[first][k]);\n            fields+=(anchor.accuracy==3?(distance==2||distance==4):distance==1)?1:100;\n        }'
    if base.count(first)!=1 or base.count(second)!=1:raise RuntimeError('Expected exactly two patch sites')
    output=base.replace(first,new_first,1).replace(second,new_second,1)
    if hashlib.sha256(output).hexdigest()!=EXPECTED:raise RuntimeError('Two-site patch hash differs')
    if OVERRIDE.exists() and OVERRIDE.read_bytes()!=output:raise RuntimeError('Frozen override changed')
    if not OVERRIDE.exists():OVERRIDE.write_bytes(output)
    return dict(base_source_sha256=PAIR.FIXED,override_sha256=EXPECTED,override=PAIR.rel(OVERRIDE),exact_checked_replacement_sites=2,p3_generator_deltas=[-4,-2,2,4],p3_composer_magnitudes=[2,4],non_p3_generator_deltas=[-1,1],non_p3_composer_magnitudes=[1],all_other_source_bytes_preserved=True)


def build():
    patch=generate();base=json.loads((BUILD/'build-fixed.json').read_text())
    for name,digest in base['sources'].items():
        if PAIR.sha(REPO/name)!=digest:raise RuntimeError('Frozen phase1 input changed: '+name)
    if PAIR.sha(BUILD/'bin/fixed')!=base['binary_sha256']:raise RuntimeError('Fixed reference binary changed')
    inputs={**base['sources'],PAIR.rel(OVERRIDE):EXPECTED,PAIR.rel(Path(__file__)):PAIR.sha(Path(__file__)),PAIR.rel(PROTOCOL):PAIR.sha(PROTOCOL)}
    command=base['command'].copy();old=PAIR.rel(PAIR.ACTIVE/'host/LpxLpcRefine.cpp')
    if command.count(old)!=1:raise RuntimeError('Unexpected production source composition')
    command[command.index(old)]=PAIR.rel(OVERRIDE)
    binary=BUILD/'bin/p3-grid';command[command.index('-o')+1]=PAIR.rel(binary)
    receipt=BUILD/'build-neighbors.json'
    if receipt.exists():
        prior=json.loads(receipt.read_text())
        if prior.get('sources')==inputs and binary.exists() and prior.get('binary_sha256')==PAIR.sha(binary):return prior
    subprocess.run(command,cwd=REPO,check=True)
    if inputs!={name:PAIR.sha(REPO/name) for name in inputs}:raise RuntimeError('Build input changed')
    result=dict(schema='lpx-p3-grid-source-override-v1',compiler=base['compiler'],command=command,sources=inputs,binary_sha256=PAIR.sha(binary),patch=patch,baseline_revision=base['baseline_revision'],unchanged_production_inputs_normalized_sha256=base['unchanged_production_inputs_normalized_sha256'],fixed_reference_binary_sha256=base['binary_sha256'])
    PAIR.write(receipt,result);return result


def summary(rows):
    result={}
    for target in ('pcm','pwm'):
        cases=[r for r in rows if r['target']==target]
        if not cases:continue
        outputs={}
        for name in ('baseline','raw-neighbors','protected'):
            data=[r['protection']['protected_quality'] if name=='protected' else r[name]['quality'] for r in cases]
            sizes=[r['protection']['protected_bits']['total']//8 if name=='protected' else r[name]['bytes'] for r in cases]
            outputs[name]=dict(bytes=sum(sizes),pcm_sse=sum(d['pcm_sse'] for d in data),pwm_sse=sum(d['pwm_sse'] for d in data),mean_stoi=[sum(d['stoi'][p] for d in data)/len(data) for p in (0,1)])
        result[target]=dict(cases=len(cases),raw_changed=sum(c['protection']['raw_changed'] for c in cases),protected_changed=sum(c['protection']['protected_fix_selected'] for c in cases),retained_baseline_encode_seconds=sum(c['baseline']['encode_seconds'] for c in cases),neighbor_encode_seconds=sum(c['raw-neighbors']['encode_seconds'] for c in cases),outputs=outputs)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--phase',choices=('pilot','matrix'),default='pilot');parser.add_argument('--build-only',action='store_true');args=parser.parse_args()
    receipt=build()
    if args.build_only:print('Built P3 two-site grid override');return
    original_path=HERE/'results-matrix.json';original_sha=PAIR.sha(original_path);original=json.loads(original_path.read_text())
    if not original['complete'] or len(original['cases'])!=8:raise RuntimeError('Complete frozen original matrix required')
    if PAIR.sha(PAIR.SOURCE/'sources.json')!=original['source_manifest_sha256']:raise RuntimeError('Prepared source manifest changed')
    rows=[];output=HERE/f'results-neighbors-{args.phase}.json'
    for old in original['cases']:
        if args.phase=='pilot' and not old['name'].startswith('chego-'):continue
        source=REPO/old['source']
        if PAIR.sha(source)!=old['source_sha256']:raise RuntimeError('Original source changed')
        for item in old['artifacts']['baseline'].values():
            if PAIR.sha(REPO/item['path'])!=item['sha256']:raise RuntimeError('Stored original baseline changed')
        target=old['target'];directory=BUILD/'runs/p3-grid-v1'/args.phase/old['name'];directory.mkdir(parents=True,exist_ok=True)
        raw_prefix=directory/'raw-neighbors';raw=PAIR.run([BUILD/'bin/p3-grid','encode',source,raw_prefix,target])
        if raw['seed_bytes']!=old['baseline']['seed_bytes'] or raw['policy_budget_C']!=old['baseline']['policy_budget_C']:raise RuntimeError('Neighbor arm changed initial seed/budget')
        protected_prefix=directory/'protected';protection=PAIR.run([BUILD/'bin/p3-grid','compare',source,REPO/old['artifacts']['baseline']['lpx']['path'],Path(str(raw_prefix)+'.lpx'),protected_prefix,target])
        if receipt['sources']!={name:PAIR.sha(REPO/name) for name in receipt['sources']} or PAIR.sha(original_path)!=original_sha or PAIR.sha(source)!=old['source_sha256']:raise RuntimeError('Frozen inputs changed during measurement')
        row=dict(name=old['name'],target=target,source=old['source'],source_sha256=old['source_sha256'],baseline=old['baseline'],protection=protection,artifacts={'baseline':old['artifacts']['baseline'],'raw-neighbors':PAIR.artifacts(raw_prefix),'protected':PAIR.artifacts(protected_prefix)})
        row['raw-neighbors']=raw;rows.append(row)
        result=dict(schema='lpx-p3-grid-neighbors-paired-v1',phase=args.phase,complete=False,build=receipt,protocol_sha256=PAIR.sha(PROTOCOL),original_matrix_sha256=original_sha,source_manifest_sha256=original['source_manifest_sha256'],method='Distinct two-site P3 neighbor/composer arm on the fidelity-fixed helper. Same stored original B0 baseline and prepared sources. Raw encoding retains unchanged native P3 allocation C; protected output adds the frozen strict same-B0 floors. Baseline timing is retained from a previous run, not a fresh paired speed measurement. No source-specific tuning or additional search/acceptance changes.',rejection_bits=original['rejection_bits'],cases=rows,summary=summary(rows))
        PAIR.write(output,result);print(f"{old['name']}: {old['baseline']['bytes']} -> {raw['bytes']} bytes; raw_changed={protection['raw_changed']}; protected={protection['protected_fix_selected']}",flush=True)
    result['complete']=True;PAIR.write(output,result);print(PAIR.rel(output),flush=True)


if __name__=='__main__':main()

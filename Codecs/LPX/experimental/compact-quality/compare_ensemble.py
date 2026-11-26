"""Existing fine-grid P4 search at each finished original P3 file's byte ceiling.

Build and freeze first. Speech runs require the independent validity gate.
The runner never re-encodes or modifies the stored original P3 baseline.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import platform
import subprocess

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
BUILD=REPO/'build/compact-quality'
SPEC=importlib.util.spec_from_file_location('frozen_p3_pair',HERE/'compare.py')
PAIR=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(PAIR)
PROTOCOL=HERE/'P3_ENSEMBLE_PROTOCOL.md'
SOURCE=HERE/'benchmark_ensemble.cpp'
ORIGINAL=HERE/'results-matrix.json'
ORIGINAL_SHA='c9c4d75bdebcb6ca80e376fc053e1a456389bc667f5f67505eb3bd2f796bdcf1'
GATE=BUILD/'p3-ensemble-independent/receipt.json'
BINARY=BUILD/'bin/ensemble'


def build():
    base=json.loads((BUILD/'build-fixed.json').read_text())
    for name,digest in base['sources'].items():
        if PAIR.sha(REPO/name)!=digest:raise RuntimeError('Frozen phase-1 input changed: '+name)
    if PAIR.sha(BUILD/'bin/fixed')!=base['binary_sha256']:raise RuntimeError('Fixed reference binary changed')
    inputs={**base['sources'],PAIR.rel(SOURCE):PAIR.sha(SOURCE),PAIR.rel(Path(__file__)):PAIR.sha(Path(__file__)),PAIR.rel(PROTOCOL):PAIR.sha(PROTOCOL)}
    command=base['command'].copy();old=PAIR.rel(HERE/'benchmark.cpp')
    if command.count(old)!=1:raise RuntimeError('Unexpected build composition')
    command[command.index(old)]=PAIR.rel(SOURCE);command[command.index('-o')+1]=PAIR.rel(BINARY)
    receipt=BUILD/'build-ensemble.json'
    if receipt.exists():
        prior=json.loads(receipt.read_text())
        if prior.get('sources')==inputs and BINARY.exists() and prior.get('binary_sha256')==PAIR.sha(BINARY):return prior
    subprocess.run(command,cwd=REPO,check=True)
    if inputs!={name:PAIR.sha(REPO/name) for name in inputs}:raise RuntimeError('Build input changed')
    cpu_model=next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')), 'unknown')
    environment=dict(system=platform.system(),release=platform.release(),machine=platform.machine(),python=platform.python_version(),logical_cpus=os.cpu_count(),cpu_model=cpu_model)
    result=dict(schema='lpx-p3-existing-encoder-ensemble-build-v1',compiler=base['compiler'],command=command,sources=inputs,binary_sha256=PAIR.sha(BINARY),baseline_revision=base['baseline_revision'],unchanged_production_inputs_normalized_sha256=base['unchanged_production_inputs_normalized_sha256'],fixed_reference_binary_sha256=base['binary_sha256'],environment=environment)
    PAIR.write(receipt,result);return result


def check_gate():
    if not GATE.exists():raise RuntimeError('Independent ensemble validity gate is required before speech')
    gate=json.loads(GATE.read_text())
    if gate.get('passed') is not True:raise RuntimeError('Independent validity gate has not passed')
    if gate.get('benchmark_sha256')!=PAIR.sha(SOURCE):raise RuntimeError('Independent gate tested another adapter')
    return gate


def summary(rows):
    result={}
    for target in ('pcm','pwm'):
        cases=[r for r in rows if r['target']==target]
        if not cases:continue
        outputs={}
        for name in ('baseline','raw-ensemble','protected'):
            data=[r[name]['quality'] for r in cases]
            outputs[name]=dict(bytes=sum(r[name]['bytes'] for r in cases),pcm_sse=sum(d['pcm_sse'] for d in data),pwm_sse=sum(d['pwm_sse'] for d in data),mean_stoi=[sum(d['stoi'][p] for d in data)/len(data) for p in (0,1)],spectral_bits=sum(r[name]['bits']['spectral_total'] for r in cases))
        result[target]=dict(cases=len(cases),raw_changed=sum(c['protection']['raw_changed'] for c in cases),protected_changed=sum(c['protection']['protected_ensemble_selected'] for c in cases),search_fallbacks=sum(c['search_fallback'] for c in cases),retained_baseline_encode_seconds=sum(c['baseline']['encode_seconds'] for c in cases),ensemble_encode_seconds=sum(c['encode_seconds'] for c in cases),ensemble_encode_cpu_seconds=sum(c['encode_cpu_seconds'] for c in cases),parameter_trials=sum(c['search']['parameter_trials'] for c in cases),pulse_trials=sum(c['search']['pulse_trials'] for c in cases),outputs=outputs)
    return result


def verify_inputs(receipt,original_sha,source_sha,source):
    if receipt['sources']!={name:PAIR.sha(REPO/name) for name in receipt['sources']}:raise RuntimeError('Build input changed')
    if PAIR.sha(BINARY)!=receipt['binary_sha256'] or PAIR.sha(ORIGINAL)!=original_sha or PAIR.sha(source)!=source_sha:raise RuntimeError('Frozen binary/baseline/source changed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=('pilot','matrix'),default='pilot')
    parser.add_argument('--build-only',action='store_true')
    args=parser.parse_args();receipt=build()
    if args.build_only:print('Built existing-encoder P3/B0 ensemble adapter');return
    gate=check_gate();gate_sha=PAIR.sha(GATE)
    original_sha=PAIR.sha(ORIGINAL)
    if original_sha!=ORIGINAL_SHA:raise RuntimeError('Stored original matrix changed')
    original=json.loads(ORIGINAL.read_text())
    if not original['complete'] or len(original['cases'])!=8:raise RuntimeError('Complete original matrix required')
    if PAIR.sha(PAIR.SOURCE/'sources.json')!=original['source_manifest_sha256']:raise RuntimeError('Source manifest changed')
    rows=[];output=HERE/f'results-ensemble-{args.phase}.json'
    for old in original['cases']:
        if args.phase=='pilot' and not old['name'].startswith('chego-'):continue
        source=REPO/old['source'];verify_inputs(receipt,original_sha,old['source_sha256'],source)
        for item in old['artifacts']['baseline'].values():
            if PAIR.sha(REPO/item['path'])!=item['sha256']:raise RuntimeError('Original baseline artifact changed')
        directory=BUILD/'runs/ensemble-v1'/args.phase/old['name'];directory.mkdir(parents=True,exist_ok=True)
        prefix=directory/'ensemble'
        row=PAIR.run([BINARY,source,REPO/old['artifacts']['baseline']['lpx']['path'],prefix,old['target'],old['baseline']['policy_budget_C']])
        if row['baseline_byte_ceiling_B0']!=old['baseline']['bytes'] or row['policy_budget_C']!=old['baseline']['policy_budget_C']:raise RuntimeError('Budget changed')
        verify_inputs(receipt,original_sha,old['source_sha256'],source)
        if PAIR.sha(GATE)!=gate_sha:raise RuntimeError('Independent gate changed')
        row.update(name=old['name'],target=old['target'],source=old['source'],source_sha256=old['source_sha256'],baseline=old['baseline'],artifacts={'baseline':old['artifacts']['baseline'],'raw-ensemble':PAIR.artifacts(Path(str(prefix)+'-raw')),'protected':PAIR.artifacts(Path(str(prefix)+'-protected'))})
        rows.append(row)
        result=dict(schema='lpx-p3-existing-encoder-ensemble-paired-v1',phase=args.phase,complete=False,build=receipt,protocol_sha256=PAIR.sha(PROTOCOL),independent_gate_sha256=gate_sha,original_matrix_sha256=original_sha,source_manifest_sha256=original['source_manifest_sha256'],method='One existing encodeThreeK call at bandwidth argument .97 and the SAME original P3 actual B0, with both physical host copies relabelled accuracy4. No additional quality/joint/header passes or source tuning. This is complete fresh spectrum/excitation candidate generation, not a local odd-LSF search. Strict experimental protection uses original active-path floors and B0; raw and protected outputs are separate. Baseline timing is retained from an earlier run and is not a controlled speed comparison. PWM metrics are inactive posthoc diagnostics for PCM admission. Equal bytes do not establish equal AVR cycles.',rejection_bits={**original['rejection_bits'],'geometry':1024,'policy':2048},cases=rows,summary=summary(rows))
        PAIR.write(output,result)
        print(f"{old['name']}: {old['baseline']['bytes']} -> {row['raw-ensemble']['bytes']} bytes; raw_changed={row['protection']['raw_changed']}; protected={row['protection']['protected_ensemble_selected']}; fallback={row['fallback_reason']}",flush=True)
    result['complete']=True;PAIR.write(output,result);print(PAIR.rel(output),flush=True)


if __name__=='__main__':main()

"""Reopen the original two inputs, old comparisons and causal slot references."""
from __future__ import annotations
import argparse
import importlib
import inspect
import json
from pathlib import Path
import subprocess
import time
import traceback

from rollback_policy import ARMS,coverage_targets,validate_contexts
from rollback_runtime import (HERE,PREFIX,SOURCE_COMMIT,Inputs,sha,save,source_snapshot,
    load_original_manifest,bind_production,load_production,check_origins,bridge_native,eligible_groups,
    measurement_bridge,operator_bridge,read_prior,prior_full_pass)


def current_runtime():
    import os,sys,importlib.metadata
    return dict(python=sys.version,packages={name:importlib.metadata.version(name) for name in
        ('numpy','numba','scipy','pystoi','soundfile')},threads={name:os.environ[name] for name in
        ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS')})


def check_owner(C,root,inventory):
    name=PREFIX+'tools/refine_speech_extras.py';path=(root/name).resolve()
    if (Path(C.extras.__file__).resolve()!=path or sha(path.read_bytes())!=inventory[name] or
            C.extras.ExistingExtraPass.__module__!='refine_speech_extras'):
        raise ValueError('The state owner came from another source origin or byte epoch')


def prepare(args):
    started=time.perf_counter(),time.process_time();sources=source_snapshot();inputs=Inputs()
    original=load_original_manifest(args.original_binding,inputs)
    bases=[b for b in original['baselines'] if b['profile']==4 and not b['nonspeech'] and b['source_ordinal'] in (20,42)]
    scope=validate_contexts(bases)
    inventory=bind_production(args.source_root,SOURCE_COMMIT);natives,native=bridge_native(args.source_root,args.native_cases,inputs)
    C=load_production(args.source_root);C.extras=importlib.import_module('refine_speech_extras');check_owner(C,args.source_root,inventory)
    signature=inspect.signature(C.extras.ExistingExtraPass)
    if signature.parameters['causal_positions'].default is not False:raise ValueError('State owner default changed')
    runtime=current_runtime();jobs=[]
    for base in bases:
        plans=[]
        for index,meta in enumerate(base['segments']):
            fields=C.compact.unpack(inputs.stream(meta))
            if fields[:2]!=(meta['samples'],4):raise ValueError('Original reset geometry differs')
            eligible=eligible_groups(fields[0],fields[7])
            plans.append(dict(index=index,eligible_group_indices=eligible,initial_eligible=len(eligible),
                initial_active=sum(a!=0 for p,a in fields[7]),trial_limit=49*len(eligible),coverage_targets=list(coverage_targets(len(eligible)))))
        base['reset_plans']=plans
        target=base['prepared_target'];raw=inputs.read(target['path'],target['pcm16_sha256'])
        if len(raw)!=2*base['samples'] or target['sample_rate']!=8000:raise ValueError('Complete original target differs')
        for arm in ARMS:jobs.append(dict(id=len(jobs),arm=arm,baseline_id=base['id'],source_ordinal=base['source_ordinal'],
            profile=4,nonspeech=False,reset_indices=list(range(len(base['segments']))),horizon=160,causal_positions=True,
            cpu_seconds=None,local_byte_cap=min(base['stream_bytes'],65535),
            whole_caps={str(p):base['stream_bytes']*p//100 for p in (100,95,90)}))
    prior=[];bridges=[]
    for name,path in (('joint-rate-v1',args.rate_export),('anchor-order',args.anchor_export)):
        rows,producers=read_prior(path,name,bases,inputs);prior.extend(rows)
        for old in producers:bridges.append(dict(study=name,**measurement_bridge(old,inventory,runtime,native)))
    rows,producers,controls=prior_full_pass(args.fullpass_export,bases,inputs);prior.extend(rows)
    for old in producers:bridges.append(dict(study='existing-extra-pass',**measurement_bridge(old,inventory,runtime,native)))
    group_bridge=operator_bridge(args.source_root,producers[-1],inputs)
    inputs.verify();check_origins(args.source_root);check_owner(C,args.source_root,inventory)
    if sources!=source_snapshot():raise ValueError('Preparation source changed')
    elapsed=dict(wall_seconds=time.perf_counter()-started[0],cpu_seconds=time.process_time()-started[1])
    binding=dict(schema='lpx-extra-rollback-study-private-v1',status='prepared-no-search',source_commit=SOURCE_COMMIT,
        source_root=str(args.source_root),production_sources=inventory,research_sources=sources,runtime=runtime,
        preparation_commit=subprocess.check_output(['git','-C',str(HERE),'rev-parse','HEAD'],text=True).strip(),
        original_binding_path=str(args.original_binding),input_files_sha256=inputs.pins,baselines=bases,jobs=jobs,
        prior_rows=prior,secondary_bridges=bridges,causal_operator_bridge=group_bridge,old_causal_controls=controls,
        native_bridge=native,native_libraries={k:str(v) for k,v in natives.items()},preparation_cost=elapsed,
        new_pass_instances=0,new_model_decodes=0,new_fits=0,new_native_builds=0,new_target_jobs=0)
    save(args.output/'binding-private.json',binding)
    summary=dict(status='prepared-no-search',**scope,eligible_groups_per_arm=sum(p['initial_eligible'] for b in bases for p in b['reset_plans']),
        trial_allowance_per_arm=sum(p['trial_limit'] for b in bases for p in b['reset_plans']),
        synthetic_preflight_records=6,synthetic_preflight_instances=8,synthetic_warm_records=6,synthetic_warm_instances=8,
        prior_saved_rows=len(prior),measurement_bridges=len(bridges),operator_ast_exact=group_bridge['exact_ast'],
        preparation_cost=elapsed,new_pass_instances=0,new_model_decodes=0,new_fits=0,new_native_builds=0,new_target_jobs=0)
    save(args.output/'summary.json',summary)
    save(args.output/'complete-private.json',dict(status='complete',binding_sha256=sha((args.output/'binding-private.json').read_bytes())))
    return summary


def main():
    import os
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','original-binding','native-cases','rate-export','anchor-export','fullpass-export','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args()
    for name,value in vars(args).items():setattr(args,name,value.resolve())
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):parser.error('Use fresh private ignored output')
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS'):os.environ[name]='1'
    args.output.mkdir(parents=True)
    try:print(json.dumps(prepare(args)),flush=True);return 0
    except Exception as exc:
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True);return 1


if __name__=='__main__':raise SystemExit(main())

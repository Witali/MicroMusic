"""Prepare original P4 seeds and prior-evidence metadata; no helper/PCM decode."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import time
import traceback

from extra_policy import ARMS,eligible_groups
from extra_runtime import (HERE,SOURCE_COMMIT,Inputs,sha,save,source_snapshot,load_original_manifest,
    bind_production,load_production,check_origins,bridge_native,measurement_bridge)
from secondary import read_prior


def current_runtime():
    import os,sys,importlib.metadata
    return dict(python=sys.version,packages={name:importlib.metadata.version(name) for name in
        ('numpy','numba','scipy','pystoi','soundfile')},threads={name:os.environ[name] for name in
        ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS')})


def prepare(args):
    began=time.perf_counter(),time.process_time();inputs=Inputs();sources=source_snapshot()
    original=load_original_manifest(args.original_binding,inputs)
    bases=[b for b in original['baselines'] if b['id'] in original['pilot_baseline_ids'] and b['profile']==4]
    if (len(bases)!=6 or sum(len(b['segments']) for b in bases)!=10 or
            {(b['nonspeech'],b['source_ordinal']) for b in bases}!={(False,3),(False,16),(False,20),(False,42),(True,10),(True,65)}):
        raise ValueError('The six complete original P4 pilot contexts differ')
    inventory=bind_production(args.source_root,SOURCE_COMMIT)
    natives,native=bridge_native(args.source_root,args.native_cases,inputs);C=load_production(args.source_root)
    runtime=current_runtime();jobs=[]
    for base in bases:
        details=[]
        for index,meta in enumerate(base['segments']):
            blob=inputs.stream(meta);fields=C.compact.unpack(blob)
            if fields[:2]!=(meta['samples'],4):raise ValueError('Original P4 reset geometry differs')
            indices=eligible_groups(fields[0],fields[7])
            details.append(dict(index=index,eligible_group_indices=indices,eligible_active_groups=len(indices),
                initial_active_extras=sum(a!=0 for p,a in fields[7]),max_trial_evaluations=49*len(indices)))
        base['existing_extra_plan']=details
        if sum(p['file_bytes'] for p in base['segments'])!=base['stream_bytes']:raise ValueError('Actual original whole B differs')
        target=base['prepared_target'];raw=inputs.read(target['path'],target['pcm16_sha256'])
        if len(raw)!=2*base['samples']:raise ValueError('Original complete declared target differs')
        order=ARMS if not base['source_ordinal']%2 else ARMS[::-1]
        for arm in order:jobs.append(dict(id=len(jobs),baseline_id=base['id'],source_ordinal=base['source_ordinal'],
            nonspeech=base['nonspeech'],profile=4,mode=base['mode'],arm=arm,causal_positions=arm=='causal',
            reset_indices=list(range(len(base['segments']))),local_byte_cap=min(base['stream_bytes'],65535),
            whole_caps={str(p):base['stream_bytes']*p//100 for p in (100,95,90)},
            horizon=160,max_checkpoints=4,cpu_seconds=None))
    prior=[];bridges=[]
    for name,path in (('joint-rate-v1',args.rate_export),('anchor-order',args.anchor_export)):
        rows,bindings=read_prior(path,name,bases,inputs);prior.extend(rows)
        for old in bindings:bridges.append(dict(study=name,**measurement_bridge(old,inventory,runtime,native)))
    if len(jobs)!=12 or sum(len(j['reset_indices']) for j in jobs)!=20:raise ValueError('The fixed twelve/twenty scope differs')
    inputs.verify();check_origins(args.source_root)
    if sources!=source_snapshot():raise ValueError('Preparation source changed')
    cost=dict(wall_seconds=time.perf_counter()-began[0],cpu_seconds=time.process_time()-began[1])
    binding=dict(schema='lpx-existing-extra-study-private-v1',status='prepared-no-search',source_commit=SOURCE_COMMIT,
        source_root=str(args.source_root),production_sources=inventory,preparation_sources=sources,
        preparation_commit=subprocess.check_output(['git','-C',str(HERE),'rev-parse','HEAD'],text=True).strip(),
        original_binding_path=str(args.original_binding),original_binding_sha256=sha(args.original_binding.read_bytes()),
        input_files_sha256=inputs.pins,baselines=bases,jobs=jobs,prior_rows=prior,secondary_bridges=bridges,
        native_bridge=native,native_libraries={k:str(v) for k,v in natives.items()},runtime=runtime,preparation_cost=cost,
        actual_helper_calls=0,initial_fits=0,model_pcm_decodes=0,native_builds=0,target_jobs=0)
    save(args.output/'binding-private.json',binding)
    summary=dict(status='prepared-no-search',contexts=6,arm_records=12,reset_contexts_per_arm=10,helper_calls=20,cap_views=36,
        eligible_groups_per_arm=sum(p['eligible_active_groups'] for b in bases for p in b['existing_extra_plan']),
        max_trials_per_arm=sum(p['max_trial_evaluations'] for b in bases for p in b['existing_extra_plan']),
        cpu_cutoff=None,prior_saved_rows=len(prior),secondary_bridge_records=len(bridges),preparation_cost=cost,
        actual_helper_calls=0,model_pcm_decodes=0,initial_fits=0,native_builds=0,target_jobs=0)
    save(args.output/'summary.json',summary)
    save(args.output/'complete-private.json',dict(status='complete',binding_sha256=sha((args.output/'binding-private.json').read_bytes()),
        no_helper_or_pcm_decode_work=True))
    return summary


def main():
    import os
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','original-binding','native-cases','rate-export','anchor-export','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args()
    for name in ('source_root','original_binding','native_cases','rate_export','anchor_export','output'):
        setattr(args,name,getattr(args,name).resolve())
    if SOURCE_COMMIT is None:parser.error('Await the exact frozen source epoch')
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):parser.error('Use fresh private ignored build output')
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS'):os.environ[key]='1'
    args.output.mkdir(parents=True)
    try:print(json.dumps(prepare(args)),flush=True);return 0
    except Exception as exc:
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True);return 1


if __name__=='__main__':raise SystemExit(main())

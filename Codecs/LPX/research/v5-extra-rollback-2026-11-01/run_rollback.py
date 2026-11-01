"""Frozen synthetic preflight or one prospective whole-record rollback arm."""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import importlib
import json
from pathlib import Path
import sys
import traceback
from unittest.mock import patch

from rollback_policy import ARMS,coverage_targets
from rollback_runtime import (HERE,SOURCE_COMMIT,Inputs,sha,save,source_snapshot,load_manifest,
    bind_production,production_snapshot,load_production,check_origins,bridge_native,no_initial_fits,
    WholeEvaluator,target_for,eligible_groups,verify_preflight)
from prepare_rollback import check_owner,current_runtime
from rollback_coordinator import clock,elapsed,run_record


def synthetic_inputs(C,inputs,out):
    """Three predeclared complete fixtures, without fitting or source audio."""
    def blob(n,moved=False):
        frames=(n+319)//320
        spectra=[[1,2,4,6,8,10,13,17,23,29] for _ in range(frames)]
        params=[[8,40,0] for _ in range(frames*2)]
        pulses=[[5,8 if not i%2 else -8] for i in range(frames*16)];pulses[10][0]=0
        extras=[[-1,0] for _ in range(frames*8)];extras[5]=[0 if moved else 30,-8]
        return C.compact.pack(n,4,spectra,params,pulses,0,0,extras=extras)[0]
    original=blob(640);oracle=blob(640,True);tail=blob(201)
    original_pcm=C.compact.decode_model(original);oracle_pcm=C.compact.decode_model(oracle);tail_pcm=C.compact.decode_model(tail)
    tail_target=C.np.clip(tail_pcm.astype(C.np.int64)+C.np.where(C.np.arange(201)%2,2,-2),-32768,32767).astype(C.np.int16)
    recipes=(('causal-target',(original,),oracle_pcm),
        ('two-resets',(original,original),C.np.concatenate((oracle_pcm,original_pcm))),
        ('unplayed-noop',(tail,),tail_target))
    cases=[]
    for ordinal,(name,parts,target) in enumerate(recipes,1):
        folder=out/'synthetic-inputs'/name;folder.mkdir(parents=True);segments=[];plans=[];at=0
        for index,part in enumerate(parts):
            path=folder/('reset-%02d.l4hy'%index);path.write_bytes(part);fields=C.compact.unpack(part)
            eligible=eligible_groups(fields[0],fields[7])
            segments.append(dict(path=str(path.resolve()),index=index,start=at,samples=fields[0],profile=4,file_bytes=len(part),stream_sha256=sha(part)))
            plans.append(dict(index=index,eligible_group_indices=eligible,initial_eligible=len(eligible),initial_active=sum(a!=0 for p,a in fields[7]),
                trial_limit=49*len(eligible),coverage_targets=list(coverage_targets(len(eligible)))))
            at+=fields[0]
        reference=folder/'reference.pcm16';raw=target.astype('<i2').tobytes();reference.write_bytes(raw);inputs.read(reference,sha(raw))
        base=dict(id=-ordinal,profile=4,nonspeech=False,mode='synthetic',samples=len(target),segments=segments,reset_plans=plans,
            stream_bytes=sum(map(len,parts)),prepared_target=dict(path=str(reference.resolve()),samples=len(target),sample_rate=8000,pcm16_sha256=sha(raw)))
        cases.append((name,base,target))
    return cases,dict(model_decodes=3,model_decoded_samples=1481,initial_fits=0)


def finish_marker(out):
    names=('binding-private.json','summary.json','attempt-private.json','results-private.json',
        'synthetic-results-private.json','metric-cache-provenance-private.json')
    save(out/'complete-private.json',dict(status='complete',output_sha256={name:sha((out/name).read_bytes()) for name in names}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','baselines','native-cases','output'):parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--arm',choices=ARMS);parser.add_argument('--preflight',type=Path);parser.add_argument('--preflight-only',action='store_true')
    args=parser.parse_args()
    if args.preflight_only==bool(args.arm):parser.error('Choose the fixed preflight or one real arm')
    if not args.preflight_only and args.preflight is None:parser.error('A closed identical-context preflight is required')
    for name in ('source_root','baselines','native_cases','output','preflight'):
        value=getattr(args,name)
        if value is not None:setattr(args,name,value.resolve())
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):parser.error('Use fresh private ignored output')
    args.output.mkdir(parents=True);begin=clock();inputs=Inputs()
    attempt=dict(status='started',real_instances=[],synthetic_instances=[],records=[],forbidden_fit_or_build_attempts=0,forbidden_wrapper_calls=0)
    save(args.output/'attempt-private.json',attempt)
    try:
        sources=source_snapshot();manifest=load_manifest(args.baselines,inputs)
        inventory=bind_production(args.source_root,SOURCE_COMMIT);native,native_bridge=bridge_native(args.source_root,args.native_cases,inputs)
        C=load_production(args.source_root);C.extras=importlib.import_module('refine_speech_extras');check_owner(C,args.source_root,inventory)
        runtime=current_runtime()
        if (manifest['production_sources']!=inventory or manifest['runtime']!=runtime or manifest['native_bridge']!=native_bridge or
                manifest['research_sources']!=sources):raise ValueError('Prepared research/source/native/runtime context differs')
        context=sha(json.dumps(dict(production=inventory,native=native_bridge,research=sources,runtime=runtime),sort_keys=True).encode())
        mode='preflight' if args.preflight_only else args.arm
        binding=dict(source_commit=SOURCE_COMMIT,source_root=str(args.source_root),production_sources=inventory,research_sources=sources,
            runtime=runtime,native_bridge=native_bridge,source_context=context,mode=mode,baselines_path=str(args.baselines),input_files_sha256=inputs.pins)
        admission=None
        if args.preflight is not None:admission=verify_preflight(args.preflight,args.baselines,inputs,binding)
        jobs=[] if args.preflight_only else [j for j in manifest['jobs'] if j['arm']==args.arm]
        if jobs and (len(jobs)!=2 or sum(len(j['reset_indices']) for j in jobs)!=6):raise ValueError('Fixed real arm scope differs')
        binding.update(assigned_jobs=[j['id'] for j in jobs],preflight_admission=admission,source_preparation_cost=elapsed(begin))
        save(args.output/'binding-private.json',binding)
        bases={b['id']:b for b in manifest['baselines']};results=[];synthetic=[]
        def forbidden_wrapper(*a,**kw):
            attempt['forbidden_wrapper_calls']+=1
            raise AssertionError('This study must use only the bounded stateful owner')
        native_start=clock()
        with no_initial_fits(attempt,args.output),patch.object(C.extras,'refine_existing_extras',forbidden_wrapper),ExitStack() as stack:
            common=stack.enter_context(C.BatchSession('batch',prebuilt=native['common']))
            only=stack.enter_context(C.BatchSession('batch',prebuilt=native['v5-only']))
            native_setup_cost=elapsed(native_start);evaluator=WholeEvaluator(C,common,only,context)
            warm_start=clock();cases,target_recipe=synthetic_inputs(C,inputs,args.output)
            for name,base,target in cases:
                for arm in ARMS if args.preflight_only else (args.arm,):
                    job=dict(id='synthetic-'+name+'-'+arm,arm=arm,local_byte_cap=min(base['stream_bytes'],65535),
                        whole_caps={str(p):base['stream_bytes']*p//100 for p in (100,95,90)})
                    synthetic.append(run_record(job,base,target,C,evaluator,inputs,args.output,attempt,'synthetic'))
            warm_cost=elapsed(warm_start)
            for job in jobs:
                base=bases[job['baseline_id']];target=target_for(base,C,inputs)
                old=manifest['old_causal_controls'][str(base['id'])] if args.arm=='continue' else None
                results.append(run_record(job,base,target,C,evaluator,inputs,args.output,attempt,'real',old))
        if sources!=source_snapshot() or inventory!=production_snapshot(args.source_root):raise ValueError('Frozen source changed')
        check_origins(args.source_root);check_owner(C,args.source_root,inventory);inputs.verify()
        real_count=0 if args.preflight_only else 6;synthetic_count=8 if args.preflight_only else 4
        if (len(attempt['real_instances'])!=real_count or len(attempt['synthetic_instances'])!=synthetic_count or
                any(r['status']!='complete' for r in attempt['real_instances']+attempt['synthetic_instances']) or
                any(r['status']!='complete' or len(r['stage_events'])!=4 for r in attempt['records']) or
                any([d['percent'] for d in r['decisions']]!=[100,95,90] for r in results+synthetic) or
                attempt['forbidden_fit_or_build_attempts'] or attempt['forbidden_wrapper_calls']):
            raise AssertionError('Fixed actual instance/stage/cap scope or no-fit guard differs')
        save(args.output/'results-private.json',results);save(args.output/'synthetic-results-private.json',synthetic)
        save(args.output/'metric-cache-provenance-private.json',evaluator.provenance)
        summary=dict(status='PASS',mode=mode,real_arm_records=len(results),real_pass_instances=len(attempt['real_instances']),
            real_stage_events=sum(len(r['stage_events']) for r in results),real_cap_views=sum(len(r['decisions']) for r in results),
            synthetic_arm_records=len(synthetic),synthetic_pass_instances=len(attempt['synthetic_instances']),
            synthetic_stage_events=sum(len(r['stage_events']) for r in synthetic),synthetic_cap_views=sum(len(r['decisions']) for r in synthetic),
            real_trial_evaluations=sum(r['progress']['trials'] for r in attempt['real_instances']),
            real_visited_groups=sum(r['progress']['covered'] for r in attempt['real_instances']),
            source_preparation_cost=binding['source_preparation_cost'],native_setup_cost=native_setup_cost,
            synthetic_target_recipe=target_recipe,preflight_or_warm_cost=warm_cost,total_worker_main_cost=elapsed(begin),
            whole_counters=dict(evaluator.counts),initial_fits=0,native_builds=0,target_jobs=0)
        save(args.output/'summary.json',summary);attempt['status']='complete';save(args.output/'attempt-private.json',attempt)
        # Include exact generated inputs/protected tuple pins accumulated during
        # the record, without changing any stream or already completed value.
        save(args.output/'binding-private.json',binding);finish_marker(args.output)
        print(json.dumps(summary),flush=True);return 0
    except Exception as exc:
        attempt.update(status='failed',exception_type=type(exc).__name__,total_worker_main_cost=elapsed(begin))
        save(args.output/'attempt-private.json',attempt)
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True);return 1


if __name__=='__main__':raise SystemExit(main())

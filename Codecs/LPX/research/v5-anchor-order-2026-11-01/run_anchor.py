"""Finite four-arm full-record anchor-order pilot with immutable attempts and exact whole gates."""
from __future__ import annotations
import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from anchor_policy import ARMS,settings,validate_scope,validate_counters,compare_nominated,priority_plan,repeat_savings
from anchor_runtime import (HERE,VALUE_KEYS,WholeEvaluator,Inputs,bind_production,check_origins,
    equal,load_production,no_initial_fits,production_snapshot,save,sha,source_snapshot,
    bridge_native,load_manifest,target_for,frontier_summary,local_frontier,whole_views,distinct_whole)


def timed():return time.perf_counter(),time.process_time()
def elapsed(start):return dict(wall_seconds=time.perf_counter()-start[0],cpu_seconds=time.process_time()-start[1])


def validate_report(report,requested,captures,quota):
    for key in ('frame_limit','window_frames','beam_width','spectral_candidates','excitation_candidates',
            'excitation_horizon','max_evaluations','screening','screening_horizon','rate_lambda',
            'capacity_policy','objective_name','selection','anchor_order'):
        equal(report[key],requested[key])
    if (report['allocation_evaluation_limit']!=requested['allocation_evaluations'] or
            report['allocation_evaluations']>requested['allocation_evaluations'] or
            report['full_synthesis_evaluations']>requested['max_evaluations'] or
            report['cpu_budget']['limit_seconds']!=quota or
            report['candidate_sink_streams']!=len(captures) or
            bool(report.get('rate_search',False))!=requested['rate_search']):
        raise AssertionError('The returned helper settings or finite bounds differ')
    validate_counters(report)
    if requested['rate_search'] and (report['rate_allocation_limit_per_branch']!=16 or
            report['rate_allocation_children_limit_per_branch']!=3):
        raise AssertionError('The opt-in branch ceilings differ')


def warmup(C,common,only,out,profiles,attempt):
    began=timed();rows=[];checks=0
    smoke=WholeEvaluator(C,common,only,'anchor-order-synthetic-only')
    n=5120
    for profile in profiles:
        blob=C.compact.pack(n,profile,[[1+2*i for i in range(10)] for _ in range(16)],
            [[8,40,6] for _ in range(32)],[[0,8 if profile==4 else 7] for _ in range(256)],
            0,0,extras=[[-1,0] for _ in range(128)])[0]
        pcm=C.compact.decode_model(blob)
        delta=C.np.where(C.np.arange(n)%17<8,5,-5)
        target=C.np.clip(pcm.astype(C.np.int64)+delta,-32768,32767).astype(C.np.int16)
        difference=target.astype(C.np.int64)-pcm.astype(C.np.int64)
        sse=int(C.np.sum(difference*difference))
        base=dict(profile=profile,samples=n,segments=[dict(samples=n)])
        for i,arm in enumerate(ARMS):
            job=dict(arm=arm,new_generation=i>=2,anchor_order='priority' if i%2 else 'time')
            requested=settings(job,synthetic=True)
            captures=[];at=timed()
            event=dict(profile=profile,arm=arm,status='started',settings=requested)
            attempt['synthetic_calls'].append(event);save(out/'attempt-private.json',attempt)
            selected,decoded,report,raw=C.trajectory.refine(target,blob,common,len(blob),speech=True,
                cpu_seconds=None,candidate_sink=lambda b,s:captures.append((bytes(b),float(s))),**requested)
            cost=elapsed(at);validate_report(report,requested,captures,None)
            event.update(status='returned',cost=cost)
            save(out/'synthetic'/('profile-%d-%s-private.json'%(profile,arm)),dict(report=report,cost=cost,callbacks=len(captures)))
            save(out/'attempt-private.json',attempt)
            for candidate,score in captures:
                actual=C.compact.decode_model(candidate)
                d=target.astype(C.np.int64)-actual.astype(C.np.int64)
                if score!=int(C.np.sum(d*d)):raise AssertionError('Synthetic serialized sink SSE differs')
                checks+=1
            anchor=smoke.measure((blob,),base,target,True,dict(arm=arm,profile=profile,role='baseline'))
            equal(anchor['metrics'],report['baseline'])
            for role,candidate in (('selected',selected),('raw',raw)):
                if candidate is not None:smoke.measure((bytes(candidate),),base,target,True,dict(arm=arm,profile=profile,role=role))
            rows.append(dict(profile=profile,arm=arm,settings=requested,cost=cost,report=report))
            event['status']='complete';save(out/'attempt-private.json',attempt)
    for profile in profiles:
        by_arm={row['arm']:row['report'] for row in rows if row['profile']==profile}
        for a,b in ((0,1),(2,3)):compare_nominated(by_arm[ARMS[a]],by_arm[ARMS[b]])
    result=dict(status='complete',synthetic_only=True,helper_calls=len(rows),cost=elapsed(began),
        serialized_sink_sse_checks=checks,whole_counters=dict(smoke.counts),calls=rows)
    save(out/'warmup-private.json',result)
    return result


def persist_stream(path,blob,index,base):
    if path.exists():
        raise ValueError('An immutable stream destination exists')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(blob)
    meta = base['segments'][index]
    return dict(path=str(path.resolve()),stream_sha256=sha(blob),file_bytes=len(blob),index=index,
        start=meta['start'],samples=meta['samples'],profile=base['profile'])


def local_call(job,index,base,baseline_blob,reference,C,common,folder,attempt,out,counters):
    local = folder/('reset-%03d'%index)
    local.mkdir(parents=True)
    event = dict(job_id=job['id'],arm=job['arm'],baseline_id=base['id'],reset=index,
        cpu_seconds=job['cpu_seconds_per_reset'],status='started')
    attempt['helper_calls'].append(event)
    attempt['active_helper'] = {k:v for k,v in event.items() if k!='status'}
    save(out/'attempt-private.json',attempt)
    save(local/'attempt-private.json',event)
    captures = []
    def sink(blob,score):
        captures.append((bytes(blob),float(score)))
    began = timed()
    call_settings = settings(job)
    helper = C.trajectory.refine
    selected,pcm,report,raw = helper(reference,baseline_blob,common,job['local_byte_cap'],
        speech=not job['nonspeech'],cpu_seconds=job['cpu_seconds_per_reset'],candidate_sink=sink,**call_settings)
    cost = elapsed(began)
    validate_report(report,call_settings,captures,job['cpu_seconds_per_reset'])
    if report['max_file_bytes']!=job['local_byte_cap']:
        raise AssertionError('The helper did not use the actual whole-B local cap')
    # Save the returned report before any endpoint postprocessing or persistence.
    save(local/'helper-return-private.json',dict(status='returned',report=report,cost=cost,
        callbacks=len(captures),selected_present=selected is not None,raw_present=raw is not None))
    counters['actual_helper_calls_completed'] += 1
    phase = timed()
    metas = []
    for order,(blob,score) in enumerate(captures):
        meta = persist_stream(local/'captures'/('callback-%05d.l4hy'%order),blob,index,base)
        metas.append(dict(**meta,callback_order=order,reported_sse=score))
    persistence = elapsed(phase)
    phase = timed()
    unique,seen = [],{}
    selected_model = None
    baseline_model = None
    all_blobs = [(blob,score,'sink') for blob,score in captures]
    all_blobs += [(baseline_blob,None,'baseline')]
    all_blobs += [(bytes(blob),None,label) for label,blob in (('selected',selected),('raw',raw)) if blob is not None]
    for blob,claimed,label in all_blobs:
        if blob in seen:
            point = unique[seen[blob]]
            point['labels'].append(label)
            if claimed is not None and point['sse'] is not None and float(claimed)!=point['sse']:
                raise AssertionError('Duplicate serialized callbacks claim different SSE')
            continue
        n,profile = C.compact.unpack(blob)[:2]
        if (n,profile)!=(len(reference),base['profile']):
            raise AssertionError('Captured endpoint changed reset geometry/profile')
        identifier = len(unique)
        seen[blob] = identifier
        value = None
        if len(blob)<=job['local_byte_cap']:
            decoded = C.compact.decode_model(blob)
            if blob==baseline_blob:baseline_model=decoded
            delta = reference.astype(C.np.int64)-decoded.astype(C.np.int64)
            value = int(C.np.sum(delta*delta))
            if selected is not None and blob==selected:
                selected_model = decoded
            counters['captured_model_reset_checks'] += 1
            counters['captured_model_samples'] += len(decoded)
            if claimed is not None and (isinstance(claimed,bool) or not math.isfinite(claimed) or float(claimed)!=value):
                raise AssertionError('Captured full serialized PCM SSE differs from helper callback')
        unique.append(dict(id=identifier,blob=blob,sse=value,labels=[label]))
    verification = elapsed(phase)
    phase=timed()
    if baseline_model is None:raise AssertionError('The fixed baseline model audit disappeared')
    d=reference.astype(C.np.int64)-baseline_model.astype(C.np.int64)
    errors={f:int(C.np.sum(d[f*320:(f+1)*320]**2)) for f in report['nominated_anchors']}
    savings=repeat_savings(C.compact.unpack(baseline_blob)[2],base['profile'],C.trajectory.spectrum_bits) if job['new_generation'] else None
    expected_plan=report['nominated_anchors'] if job['anchor_order']=='time' else priority_plan(report['nominated_anchors'],errors,savings)
    if expected_plan!=report['planned_anchors']:raise AssertionError('The actual static priority plan differs from its independent baseline-byte recipe')
    anchor_plan_audit=elapsed(phase)
    phase = timed()
    points = local_frontier([row for row in unique if row['sse'] is not None],job['local_byte_cap'])
    pruning = elapsed(phase)
    for blob in (selected,raw):
        if blob is not None and len(blob)>job['local_byte_cap']:
            raise AssertionError('Returned local endpoint violates its actual complete-file cap')
    if selected is not None and (pcm is None or selected_model is None or not C.np.array_equal(pcm,selected_model)):
        raise AssertionError('Returned selected PCM differs from serialized model')
    summary = dict(index=index,helper_cost=cost,cpu_budget=report['cpu_budget'],sink_callbacks=len(captures),
        distinct_captured_and_fallback=len(unique),frontier_count=len(points),
        feasible_pool_rows=sum(row['sse'] is not None for row in unique),
        oversize_pool_rows=sum(row['sse'] is None for row in unique),persistence_cost=persistence,
        independent_raw_pool_model_sse_audit_cost=verification,bounded_endpoint_pruning_cost=pruning,
        independent_anchor_plan_audit_cost=anchor_plan_audit,
        selected_id=None if selected is None else seen[selected],raw_id=None if raw is None else seen[raw],
        frontier_ids=[point['id'] for point in points],captured_streams=metas,
        pool=[dict(id=row['id'],stream_sha256=sha(row['blob']),file_bytes=len(row['blob']),
            sse=row['sse'],labels=row['labels']) for row in unique])
    save(local/'endpoint-private.json',summary)
    event.update(status='complete',cost=cost,sink_callbacks=len(captures))
    attempt['active_helper'] = None
    attempt['counters'] = dict(counters)
    save(local/'attempt-private.json',event)
    save(out/'attempt-private.json',attempt)
    return dict(index=index,selected=None if selected is None else bytes(selected),
        raw=None if raw is None else bytes(raw),frontier=points),summary


def fresh_anchor(base,target,C,evaluator,inputs,event):
    blobs=tuple(inputs.stream(meta) for meta in base['segments'])
    if sum(map(len,blobs))!=base['stream_bytes']:
        raise AssertionError('The strongest complete B differs')
    value=evaluator.measure(blobs,base,target,not base['nonspeech'],event)
    for key in VALUE_KEYS:equal(value[key],base['stored_expected_whole_value'][key])
    flags=C.chain._admission(value,value)
    if not all(flags.values()):raise AssertionError('The current baseline fails its own whole gates')
    base['fresh_baseline_sse']=value['metrics']['pcm16']['error_energy']
    return blobs,value


def run_arm(job,base,target,C,common,evaluator,inputs,out,attempt,counters):
    began=timed();folder=out/'arms'/('job-%03d'%job['id']);folder.mkdir(parents=True)
    baseline,anchor=fresh_anchor(base,target,C,evaluator,inputs,
        dict(job_id=job['id'],baseline_id=base['id'],role='baseline-before-search'))
    requested=settings(job)
    locals,summaries=[],[]
    for index in job['reset_indices']:
        meta=base['segments'][index];at,n=meta['start'],meta['samples']
        counters['actual_helper_calls_started']+=1
        row,summary=local_call(job,index,base,baseline[index],target[at:at+n],C,common,
            folder,attempt,out,counters)
        locals.append(row);summaries.append(summary)
    audit=timed();before=evaluator.counts.copy()
    choices=distinct_whole(whole_views(baseline,locals));measured=[];artifacts=[]
    if len(choices)>5 or choices[0]['blobs']!=baseline:
        raise AssertionError('The fixed whole recipe pool changed')
    for choice in choices:
        value=evaluator.measure(choice['blobs'],base,target,not job['nonspeech'],
            dict(job_id=job['id'],baseline_id=base['id'],chain_id=choice['id']))
        flags=C.chain._admission(value,anchor)
        measured.append(dict(id=choice['id'],labels=choice['labels'],stream_bytes=choice['stream_bytes'],
            full_flash_bytes=None,**value,**flags,automatic_quality_eligible=all(flags.values())))
        parts=[persist_stream(folder/'whole'/('chain-%03d'%choice['id'])/('segment-%03d.l4hy'%i),
            blob,i,base) for i,blob in enumerate(choice['blobs'])]
        artifacts.append(dict(id=choice['id'],segments=parts))
    decisions=[]
    for percent in (100,95,90):
        decision=C.chain.choose_budget(measured,job['whole_caps'][str(percent)])
        chosen=None if decision['selected_id'] is None else measured[decision['selected_id']]
        if percent==100 and (chosen is None or
                (chosen['score'],chosen['stream_bytes'])>(anchor['score'],base['stream_bytes'])):
            raise AssertionError('The retained current baseline regressed')
        decisions.append(dict(percent=percent,**decision,baseline_nonregression=True))
    result=dict(**job,status='complete',baseline_samples=base['samples'],reset_segments=len(baseline),
        fresh_baseline_sse=base['fresh_baseline_sse'],baseline_bytes=base['stream_bytes'],
        zero_sse_price_degenerate=base['fresh_baseline_sse']==0,
        locals=summaries,whole_rows=measured,whole_chains=artifacts,decisions=decisions,
        total_helper_cpu=sum(r['helper_cost']['cpu_seconds'] for r in summaries),
        total_helper_wall=sum(r['helper_cost']['wall_seconds'] for r in summaries),
        whole_audit_cost=elapsed(audit),whole_audit_counters=dict(evaluator.counts-before),
        total_arm_cost=elapsed(began),**frontier_summary(measured))
    save(folder/'result-private.json',result)
    counters['arm_records_completed']+=1
    attempt['arm_records'].append(dict(job_id=job['id'],status='complete',baseline_id=base['id'],arm=job['arm']))
    attempt['counters']=dict(counters);save(out/'attempt-private.json',attempt)
    print(json.dumps(dict(status='arm-complete',job=job['id'],profile=job['profile'],arm=job['arm'],
        whole_rows=len(measured))),flush=True)
    return result


def verify_pair_plans(results,out,inputs):
    by_context={}
    for row in results:
        by_context.setdefault(row['baseline_id'],{})[row['arm']]=row
    pairs=[]
    for baseline_id,arms in by_context.items():
        if set(arms)!=set(ARMS):raise AssertionError('A complete context lacks its four fresh arms')
        for a,b in ((0,1),(2,3)):
            left,right=arms[ARMS[a]],arms[ARMS[b]]
            if left['reset_indices']!=right['reset_indices']:raise AssertionError('A paired reset was omitted')
            for index in left['reset_indices']:
                def returned(row):
                    path=out/'arms'/('job-%03d'%row['id'])/('reset-%03d'%index)/'helper-return-private.json'
                    return inputs.json(path)['report']
                temporal,priority=returned(left),returned(right)
                compare_nominated(temporal,priority)
                pairs.append(dict(baseline_id=baseline_id,new_generation=a==2,reset=index,
                    time_job_id=left['id'],priority_job_id=right['id'],
                    nominated_anchors=temporal['nominated_anchors'],
                    temporal_plan=temporal['planned_anchors'],priority_plan=priority['planned_anchors']))
    save(out/'anchor-pair-postcheck-private.json',dict(status='PASS',pairs=pairs,paired_reset_checks=len(pairs)))
    return len(pairs)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','baselines','native-cases','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--source-commit',required=True)
    parser.add_argument('--preflight',type=Path)
    parser.add_argument('--profile',type=int,choices=(4,6))
    parser.add_argument('--preflight-only',action='store_true')
    args=parser.parse_args()
    if args.source_commit!='55ebc0d94e919fa7aeec4819e3bf83cfaf81fa6a':
        parser.error('This frozen anchor pilot requires its exact declared production epoch')
    for name in ('source_root','baselines','native_cases','output'):
        setattr(args,name,getattr(args,name).resolve())
    if args.preflight_only==bool(args.profile):
        parser.error('Choose either the synthetic preflight or one corpus profile')
    if args.preflight_only and args.preflight is not None or not args.preflight_only and args.preflight is None:
        parser.error('Each corpus shard requires its completed same-source preflight')
    if args.preflight is not None:args.preflight=args.preflight.resolve()
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):
        parser.error('Use fresh ignored private build output in this research worktree')
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS'):os.environ[name]='1'
    args.output.mkdir(parents=True)
    attempt=dict(status='started',profile=args.profile,helper_calls=[],synthetic_calls=[],arm_records=[],active_helper=None,
        forbidden_fit_or_build_attempts=0)
    save(args.output/'attempt-private.json',attempt);started=timed();counters=Counter()
    try:
        sources=source_snapshot();inputs=Inputs();manifest=load_manifest(args.baselines,inputs)
        bases=validate_scope(manifest)
        inventory=bind_production(args.source_root,args.source_commit)
        natives,bridge=bridge_native(args.source_root,args.native_cases,inputs)
        C=load_production(args.source_root)
        import inspect
        parameter=inspect.signature(C.trajectory.refine).parameters.get('anchor_order')
        if parameter is None or parameter.default!='time':
            raise ValueError('The explicitly frozen API must expose anchor_order with default time')
        jobs=[] if args.preflight_only else [j for j in manifest['jobs'] if j['profile']==args.profile]
        if jobs and (len(jobs)!=24 or sum(len(j['reset_indices']) for j in jobs)!=40):
            raise ValueError('A balanced complete-profile shard differs')
        targets={i:target_for(bases[i],C,inputs) for i in {j['baseline_id'] for j in jobs}}
        context=sha(json.dumps(dict(production=inventory,native=bridge),sort_keys=True).encode())
        if args.preflight is not None:
            smoke=inputs.json(args.preflight/'summary.json');smoke_binding=inputs.json(args.preflight/'binding-private.json')
            smoke_attempt=inputs.json(args.preflight/'attempt-private.json')
            if (smoke['status']!='PASS' or not smoke['preflight_only'] or smoke['helper_calls'] or
                    smoke['synthetic_helper_calls']!=8 or smoke_attempt['status']!='complete' or
                    smoke_binding['source_commit']!=args.source_commit or smoke_binding['research_sources']!=sources or
                    smoke_binding['source_context']!=context):
                raise ValueError('The fixed eight-helper same-source preflight is not complete')
        binding=dict(schema='lpx-anchor-order-pilot-private-v1',source_commit=args.source_commit,
            production_sources=inventory,research_sources=sources,source_root=str(args.source_root),
            research_commit=subprocess.check_output(['git','-C',str(HERE),'rev-parse','HEAD'],text=True).strip(),
            module_origins=check_origins(args.source_root),input_files_sha256=inputs.pins,
            baselines_path=str(args.baselines),assigned_jobs=[j['id'] for j in jobs],profile=args.profile,
            source_context=context,native_bridge=bridge,preparation_cost=elapsed(started),
            runtime=dict(python=sys.version,packages={name:__import__('importlib.metadata',fromlist=['version']).version(name)
                for name in ('numpy','numba','scipy','pystoi','soundfile')},
                threads={name:os.environ[name] for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS')}))
        save(args.output/'binding-private.json',binding);loading=timed()
        with no_initial_fits(attempt,args.output),C.BatchSession('batch',prebuilt=natives['common']) as common, C.BatchSession('batch',prebuilt=natives['v5-only']) as only:
            loading_cost=elapsed(loading)
            warm=warmup(C,common,only,args.output,(4,6) if args.preflight_only else (args.profile,),attempt)
            evaluator=WholeEvaluator(C,common,only,context)
            results=[run_arm(j,bases[j['baseline_id']],targets[j['baseline_id']],C,common,evaluator,
                inputs,args.output,attempt,counters) for j in jobs]
            paired_checks=verify_pair_plans(results,args.output,inputs)
        guard=timed()
        if sources!=source_snapshot() or inventory!=production_snapshot(args.source_root) or attempt['forbidden_fit_or_build_attempts']:
            raise ValueError('The frozen source/no-initial-fit contract changed')
        check_origins(args.source_root);inputs.verify()
        if any(r['status']!='complete' for r in attempt['helper_calls']):
            raise AssertionError('An actual corpus helper was interrupted')
        if any(r['status']!='complete' for r in attempt['synthetic_calls']):
            raise AssertionError('A synthetic helper did not complete')
        if paired_checks!=(0 if args.preflight_only else 20):
            raise AssertionError('The exact time/priority nominated-set pair count differs')
        guard_cost=elapsed(guard);persist=timed()
        save(args.output/'results-private.json',results)
        save(args.output/'metric-cache-provenance-private.json',evaluator.provenance)
        summary=dict(status='PASS',profile=args.profile,preflight_only=args.preflight_only,
            arm_records=len(results),helper_calls=len(attempt['helper_calls']),cap_views=3*len(results),
            synthetic_helper_calls=warm['helper_calls'],synthetic_cost=warm['cost'],
            paired_reset_anchor_sets_verified=paired_checks,
            new_initial_fits=0,new_native_builds=0,actual_cost=elapsed(started),
            preparation_cost=binding['preparation_cost'],native_loading_cost=loading_cost,
            final_guard_cost=guard_cost,terminal_artifact_cost=elapsed(persist),counters=dict(counters),
            whole_counters=dict(evaluator.counts),no_old_whole_metric_reuse=True)
        save(args.output/'summary.json',summary);attempt.update(status='complete',summary=summary)
        save(args.output/'attempt-private.json',attempt)
        print(json.dumps(summary),flush=True);return 0
    except Exception as exc:
        attempt.update(status='failed',exception_type=type(exc).__name__,actual_cost=elapsed(started),counters=dict(counters))
        save(args.output/'attempt-private.json',attempt)
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True);return 1


if __name__=='__main__':raise SystemExit(main())

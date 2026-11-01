"""Fresh admission of original V1 recipes plus one fixed-pool DP per arm."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import json
import os
from pathlib import Path
import traceback

from chain_study_policy import PERCENTS,allocate_views,new_outcome,validate_jobs,extends_context_frontier
from chain_study_runtime import (SUPPORT,VALUE_KEYS,sha,save,timed,elapsed,sources,fresh_output,
    open_manifest,load_current,forbid_search_and_build,final_guard,check_integer_sse)


def context_for(manifest):
    return sha(json.dumps(dict(production=manifest['production_sources'],native=manifest['native_bridge'],
        study_sources=manifest['study_sources'],runtime=manifest['runtime'],
        pool_recipe='V1-frontier16-plus-baseline-selected-raw'),sort_keys=True).encode())


def blobs_for(pools,ids):
    return tuple(next(row['stream'] for row in pool if row['id']==identifier) for pool,identifier in zip(pools,ids))


def public_whole(row):
    return {key:row[key] for key in ('id','labels','stream_bytes','score','metrics',
        'clipped_samples','old_pcm_pwm_floors_passed','clipped_sample_floor_passed',
        'pcm_period_coverage_floor_passed','pwm_period_coverage_floor_passed',
        'joint_objective_nonregression','automatic_quality_eligible','additive_pcm_sse')}


def run_job(job,C,evaluator,target,pools,attempt,out):
    began=timed();base=job['base'];baseline=blobs_for(pools,tuple(p['baseline_id'] for p in job['pools']))
    measure_start=timed()
    anchor=evaluator.measure(baseline,base,target,not job['nonspeech'],dict(job_id=job['id'],role='baseline-before-dp'))
    for key in VALUE_KEYS:SUPPORT.equal(anchor[key],job['originals'][0]['old_value'][key])
    baseline_cost=elapsed(measure_start)
    baseline_ids=tuple(p['baseline_id'] for p in job['pools'])
    protected=[tuple(old['ids']) for old in job['originals']]
    capture={};attempt['active_dp']=dict(job_id=job['id'],retained=capture)
    attempt['dp_calls_started']+=1;save(out/'attempt-private.json',attempt)
    dp_start=timed()
    allocation=allocate_views(pools,baseline_ids,protected,job['baseline_bytes'],C.chain_rate.allocate_exact_sse,capture)
    dp_cost=elapsed(dp_start);attempt['dp_calls_returned']+=1
    attempt['active_dp'].update(returned=True,status=allocation['result'].status,work=allocation['result'].work)
    folder=out/'arms'/('job-%03d'%job['id']);folder.mkdir(parents=True)
    save(folder/'allocation-private.json',dict(result=asdict(allocation['result']),cost=dp_cost,
        retained=capture,winners={str(p):None if v is None else asdict(v) for p,v in allocation['winners'].items()}))
    attempt['active_dp']=None
    save(out/'attempt-private.json',attempt)
    views=[dict(ids=tuple(old['ids']),labels=list(old['labels']),old=old) for old in job['originals']]
    original_count=len(views);positions={blobs_for(pools,v['ids']):i for i,v in enumerate(views)}
    for point in allocation['points']:
        parts=blobs_for(pools,point['ids'])
        if parts in positions:views[positions[parts]]['labels'].extend(point['labels'])
        else:positions[parts]=len(views);views.append(dict(ids=point['ids'],labels=list(point['labels']),old=None))
    if len(views)>original_count+3:raise AssertionError('The fixed whole union expanded')
    whole_start=timed();measured=[];integer_checks=0
    for identifier,view in enumerate(views):
        parts=blobs_for(pools,view['ids'])
        value=evaluator.measure(parts,base,target,not job['nonspeech'],dict(job_id=job['id'],chain_id=identifier))
        if view['old'] is not None:
            for key in VALUE_KEYS:SUPPORT.equal(value[key],view['old']['old_value'][key])
        additive=sum(next(row['sse'] for row in pool if row['id']==k) for pool,k in zip(pools,view['ids']))
        check_integer_sse(C,evaluator,parts,base,target,additive);integer_checks+=1
        if value['metrics']['pcm16']['error_energy']!=additive:
            raise AssertionError('Whole metric SSE differs from fresh exact integer sum')
        row=dict(id=identifier,labels=view['labels'],stream_bytes=sum(map(len,parts)),
                 additive_pcm_sse=additive,**value)
        flags=C.chain._admission(row,anchor)
        row.update(flags,automatic_quality_eligible=all(flags.values()));measured.append(row)
        if view['old'] is not None:
            old=view['old']['old_value']
            if any(row[k]!=old[k] for k in (*flags,'automatic_quality_eligible')):
                raise AssertionError('Fresh original whole admission differs')
        save(folder/'whole-progress-private.json',dict(status='running',context=evaluator.context,
            complete_whole_rows=measured,anchor=anchor,whole_counters=dict(evaluator.counts),
            cache_provenance=evaluator.provenance,
            tuples=[dict(ids=list(v['ids']),labels=v['labels']) for v in views[:len(measured)]]))
    whole_cost=elapsed(whole_start);decisions=[]
    original_parts={blobs_for(pools,v['ids']) for v in views[:original_count]}
    for percent in PERCENTS:
        cap=job['caps'][str(percent)]
        old=C.chain.choose_budget(measured[:original_count],cap);new=C.chain.choose_budget(measured,cap)
        a=None if old['selected_id'] is None else measured[old['selected_id']]
        b=None if new['selected_id'] is None else measured[new['selected_id']]
        absent=b is not None and blobs_for(pools,views[b['id']]['ids']) not in original_parts
        if percent==100 and (b is None or (b['score'],b['stream_bytes'])>(anchor['score'],job['baseline_bytes'])):
            raise AssertionError('The independently retained baseline regressed')
        decisions.append(dict(percent=percent,old=old,new=new,
            old_bytes=None if a is None else a['stream_bytes'],new_bytes=None if b is None else b['stream_bytes'],
            old_score=None if a is None else a['score'],new_score=None if b is None else b['score'],
            **new_outcome(a,b,absent,allocation['result'].exact)))
    result=dict(id=job['id'],baseline_id=job['baseline_id'],source_ordinal=job['source_ordinal'],
        arm=job['arm'],profile=job['profile'],nonspeech=job['nonspeech'],mode=job['mode'],
        status='complete' if allocation['result'].exact else 'incomplete-resource-limit',
        exact=allocation['result'].exact,dp_status=allocation['result'].status,
        decision_no_fit_scope='measured whole recipe union; limited DP leaves other pool combinations unknown',
        baseline_bytes=job['baseline_bytes'],reset_segments=len(pools),
        single_reset_identity_checked=len(pools)==1 and allocation['result'].exact,
        mechanism='single-reset-cap-selection' if len(pools)==1 else 'cross-reset-mixing',
        original_recipes=original_count,new_unique_dp_tuples=len(views)-original_count,
        whole_rows=[public_whole(row) for row in measured],decisions=decisions,
        work=allocation['result'].work,callback_completed=allocation['callback_completed'],
        reused_v1_integer_sse_rows=sum(map(len,pools)),fresh_integer_whole_sse_checks=integer_checks,
        new_helpers=0,new_fits=0,new_native_builds=0,
        costs=dict(fresh_before_dp_baseline=baseline_cost,dp=dp_cost,fresh_whole_admission=whole_cost,arm_workflow=elapsed(began)))
    save(folder/'result.json',result)
    save(folder/'result-private.json',dict(public=result,complete_whole_rows=measured,anchor=anchor,
        context=evaluator.context,tuples=[dict(ids=list(v['ids']),labels=v['labels']) for v in views]))
    save(folder/'tuples-private.json',dict(views=[dict(ids=list(v['ids']),labels=v['labels'],
        streams=[sha(blob) for blob in blobs_for(pools,v['ids'])]) for v in views]))
    attempt['arm_records'].append(dict(id=job['id'],status=result['status'],exact=result['exact']))
    save(out/'attempt-private.json',attempt)
    print(json.dumps(dict(status=result['status'],job=job['id'],dp_status=result['dp_status'],whole_rows=len(views))),flush=True)
    return result


def synthetic(C):
    jobs=[]
    for profile in (4,6):
        pools=[];segments=[];starts=0;target_parts=[]
        for index,n in enumerate((641,321)):
            frames=(n+319)//320
            spectra=[[1+3*i if profile==4 else 2+6*i for i in range(10)] for _ in range(frames)]
            params=[(18,60,8)]*(frames*2);pulses=[(0,8 if profile==4 else 2)]*(frames*16)
            added=[(-1,0)]*(frames*8);added[0]=(3,2);added[-1]=(39,3)
            rows=[]
            baseline=None
            for identifier in range(3):
                extra=list(added)
                if identifier:extra[-1]=(-1,0)
                if identifier==2:extra[0]=(-1,0)
                blob=C.compact.pack(n,profile,spectra,params,pulses,0,0,extras=extra)[0]
                pcm=C.compact.decode_model(blob)
                if baseline is None:baseline=pcm;target_parts.append(pcm)
                delta=baseline.astype(C.np.int64)-pcm.astype(C.np.int64)
                rows.append(dict(id=identifier,stream=blob,sse=int(C.np.sum(delta*delta))))
            pools.append(rows);segments.append(dict(index=index,start=starts,samples=n,profile=profile));starts+=n
        jobs.append((dict(profile=profile,samples=starts,segments=segments),C.np.concatenate(target_parts),pools))
    return jobs


def context_secondary(manifest,results,C,inputs,out):
    """No decoding/measurement/allocation: compare only persisted fresh values."""
    began=timed();contexts={};records={};parts_by_job={}
    for job,public in zip(manifest['jobs'],results):
        saved=json.loads((out/'arms'/('job-%03d'%job['id'])/'result-private.json').read_bytes())
        if saved['public']!=public:raise AssertionError('Saved fresh arm row changed before secondary projection')
        pools=[[dict(id=row['id'],stream=inputs.stream(row['stream']),sse=row['sse']) for row in pool['rows']]
               for pool in job['pools']]
        parts=[blobs_for(pools,tuple(view['ids'])) for view in saved['tuples']]
        records[job['id']]=saved;parts_by_job[job['id']]=parts
        context=contexts.setdefault(job['baseline_id'],dict(rows=[],positions={},baseline_bytes=job['baseline_bytes']))
        if context['baseline_bytes']!=job['baseline_bytes']:raise AssertionError('Context arms use different B')
        for value,key in zip(saved['complete_whole_rows'][:public['original_recipes']],parts):
            if key in context['positions']:
                prior=context['rows'][context['positions'][key]]
                for field in VALUE_KEYS:SUPPORT.equal(value[field],prior[field])
            else:
                context['positions'][key]=len(context['rows'])
                context['rows'].append(dict(value,id=len(context['rows'])))
    rows=[];frontier_rows=[];exact_keys=set();nonexact_keys=set()
    for job,public in zip(manifest['jobs'],results):
        context=contexts[job['baseline_id']];saved=records[job['id']];parts=parts_by_job[job['id']]
        for decision in public['decisions']:
            percent=decision['percent'];old=C.chain.choose_budget(context['rows'],job['caps'][str(percent)])
            control=None if old['selected_id'] is None else context['rows'][old['selected_id']]
            identifier=decision['new']['selected_id']
            new=None if identifier is None else saved['complete_whole_rows'][identifier]
            key=None if identifier is None else parts[identifier]
            absent=new is not None and key not in context['positions']
            extension=extends_context_frontier(context['rows'],new,absent)
            outcome=new_outcome(control,new,absent,public['exact'])
            rows.append(dict(id=job['id'],baseline_id=job['baseline_id'],arm=job['arm'],profile=job['profile'],
                percent=percent,exact=public['exact'],context_original_choices=len(context['rows']),
                known_other_arm_point=decision.get('absent_from_original_five',False) and new is not None and not absent,
                absent_from_context_original_union=absent,context_frontier_extension=extension,
                exact_context_frontier_extension=extension and public['exact'],
                nonexact_context_frontier_extension=extension and not public['exact'],
                old_context_bytes=None if control is None else control['stream_bytes'],
                old_context_score=None if control is None else control['score'],
                selected_bytes=None if new is None else new['stream_bytes'],selected_score=None if new is None else new['score'],
                context_rank_comparison=outcome['kind']))
        for identifier in range(public['original_recipes'],len(saved['complete_whole_rows'])):
            new=saved['complete_whole_rows'][identifier];key=parts[identifier]
            absent=key not in context['positions']
            for percent in PERCENTS:
                if new['stream_bytes']>job['caps'][str(percent)]:continue
                extension=extends_context_frontier(context['rows'],new,absent)
                if extension:
                    (exact_keys if public['exact'] else nonexact_keys).add((job['baseline_id'],percent,key))
                frontier_rows.append(dict(id=job['id'],chain_id=identifier,baseline_id=job['baseline_id'],
                    arm=job['arm'],profile=job['profile'],percent=percent,exact=public['exact'],
                    bytes=new['stream_bytes'],score=new['score'],automatic_quality_eligible=new['automatic_quality_eligible'],
                    known_other_arm_point=not absent,absent_from_context_original_union=absent,
                    within_arm_frontier_extension=extends_context_frontier(saved['complete_whole_rows'][:public['original_recipes']],new,True),
                    context_frontier_extension=extension,exact_context_frontier_extension=extension and public['exact'],
                    nonexact_context_frontier_extension=extension and not public['exact']))
    return dict(rows=rows,frontier_rows=frontier_rows,exact_distinct_context_cap_tuples=len(exact_keys),
        nonexact_distinct_context_cap_tuples=len(nonexact_keys),cost=elapsed(began),
        new_dp_decode_metric_native_calls=0)


def execute(args):
    began=timed();inputs,manifest,natives=open_manifest(args.manifest)
    validate_jobs(manifest['jobs']);C=load_current(manifest['producer_root'],manifest['production_sources']);context=context_for(manifest)
    attempt=dict(status='started',action=args.action,dp_calls_started=0,dp_calls_returned=0,
                 forbidden_work_attempts=0,active_dp=None,arm_records=[])
    save(args.output/'attempt-private.json',attempt)
    try:
        if args.action=='run':
            preflight=inputs.json(args.preflight/'summary.json');bound=inputs.json(args.preflight/'binding-private.json')
            terminal=inputs.json(args.preflight/'complete-private.json')
            prior_attempt=inputs.json(args.preflight/'attempt-private.json')
            if (preflight['status']!='PASS' or not preflight['synthetic_only'] or preflight['dp_calls']!=2
                    or bound['manifest_sha256']!=sha(inputs.read(args.manifest)) or bound['context']!=context
                    or bound['study_sources']!=manifest['study_sources'] or terminal['status']!='complete'
                    or prior_attempt['status']!='complete' or prior_attempt['action']!='preflight'
                    or prior_attempt['forbidden_work_attempts'] or prior_attempt['dp_calls_returned']!=2):
                raise ValueError('The exact source-stable synthetic preflight is missing')
            for name,digest in terminal['files_sha256'].items():inputs.read(args.preflight/name,digest)
            for name,digest in bound['input_files_sha256'].items():inputs.read(name,digest)
        fixtures=synthetic(C) if args.action=='preflight' else None
        with forbid_search_and_build(C,attempt,args.output), \
             C.BatchSession('batch',prebuilt=natives['common']) as common, \
             C.BatchSession('batch',prebuilt=natives['v5-only']) as only:
            evaluator=SUPPORT.WholeEvaluator(C,common,only,context)
            if fixtures is not None:
                for base,target,pools in fixtures:
                    attempt['dp_calls_started']+=1
                    selection=allocate_views(pools,(0,0),((0,0),),sum(len(p[0]['stream']) for p in pools),C.chain_rate.allocate_exact_sse)
                    attempt['dp_calls_returned']+=1
                    if not selection['result'].exact:raise AssertionError('Synthetic exact preflight hit a resource limit')
                    baseline=tuple(p[0]['stream'] for p in pools)
                    anchor=evaluator.measure(baseline,base,target,False,dict(profile=base['profile'],role='synthetic-baseline'))
                    for choice in selection['points']:
                        parts=blobs_for(pools,choice['ids'])
                        value=evaluator.measure(parts,base,target,False,dict(profile=base['profile'],role=choice['labels']))
                        check_integer_sse(C,evaluator,parts,base,target,choice['point'].sse)
                        C.chain._admission(value,anchor)
                results=[]
            else:
                results=[]
                for job in manifest['jobs']:
                    target=SUPPORT.target_for(job['base'],C,inputs)
                    pools=[]
                    for local,meta in zip(job['pools'],job['baseline']):
                        rows=[dict(id=row['id'],stream=inputs.stream(row['stream']),sse=row['sse']) for row in local['rows']]
                        if any(C.compact.unpack(row['stream'])[:2]!=(meta['samples'],job['profile']) for row in rows):
                            raise AssertionError('A supplied pool changed reset geometry/profile')
                        pools.append(rows)
                    results.append(run_job(job,C,evaluator,target,pools,attempt,args.output))
            secondary=None if fixtures is not None else context_secondary(manifest,results,C,inputs,args.output)
            if attempt['forbidden_work_attempts']:raise AssertionError('Forbidden work was attempted')
            final_guard(manifest,inputs,C)
        if args.action=='run' and (attempt['dp_calls_started']!=60 or attempt['dp_calls_returned']!=60 or len(results)!=60):
            raise AssertionError('The fixed 60-call saved-pool scope changed')
        summary=dict(status='PASS',synthetic_only=fixtures is not None,dp_calls=attempt['dp_calls_returned'],
            synthetic_fixture_serializations=12 if fixtures is not None else 0,
            synthetic_fixture_model_decodes=12 if fixtures is not None else 0,
            arm_records=len(results),cap_views=3*len(results),new_helpers=0,new_fits=0,new_native_builds=0,
            exact_arms=sum(r['exact'] for r in results),incomplete_arms=sum(not r['exact'] for r in results),
            exact_primary_wins=sum(d['exact_primary_success'] for r in results for d in r['decisions']),
            nonexact_retained_wins=sum(d.get('nonexact_retained_success',False) for r in results for d in r['decisions']),
            single_reset_identity_controls=sum(r['single_reset_identity_checked'] for r in results),
            secondary_exact_context_frontier_views=0 if secondary is None else sum(r['exact_context_frontier_extension'] for r in secondary['frontier_rows']),
            secondary_exact_distinct_context_cap_tuples=0 if secondary is None else secondary['exact_distinct_context_cap_tuples'],
            secondary_nonexact_distinct_context_cap_tuples=0 if secondary is None else secondary['nonexact_distinct_context_cap_tuples'],
            secondary_known_other_arm_views=0 if secondary is None else sum(r['known_other_arm_point'] for r in secondary['rows']),
            reused_v1_integer_sse_rows=sum(r['reused_v1_integer_sse_rows'] for r in results),
            fresh_integer_whole_sse_checks=sum(r['fresh_integer_whole_sse_checks'] for r in results),
            dp_cpu_seconds=sum(r['costs']['dp']['cpu_seconds'] for r in results),
            dp_wall_seconds_sum=sum(r['costs']['dp']['wall_seconds'] for r in results),
            prior_v1_helper_calls=100 if fixtures is None else 0,
            prior_v1_raw_model_audit_cpu_seconds=sum(c['cpu_seconds'] for j in manifest['jobs'] for c in j['v1_raw_audit_cost']) if fixtures is None else 0,
            whole_counters=dict(evaluator.counts),actual_cost=elapsed(began),
            cost_scope='through pre-terminal receipt snapshot; final summary/attempt writes excluded',
            perceptual_adoption=False,target_jobs=0,full_flash_measured=False)
        save(args.output/'rows.json',results)
        save(args.output/'secondary.json',secondary)
        save(args.output/'metric-cache-provenance-private.json',evaluator.provenance)
        save(args.output/'binding-private.json',dict(status='PASS',manifest_sha256=sha(inputs.read(args.manifest)),
            context=context,study_sources=sources(),input_files_sha256=inputs.pins,
            production_sources=manifest['production_sources'],native_bridge=manifest['native_bridge'],
            artifact_files_sha256={p.relative_to(args.output).as_posix():sha(p.read_bytes())
                for p in (args.output/'arms').rglob('*.json')}))
        save(args.output/'summary.json',summary);attempt['status']='complete';save(args.output/'attempt-private.json',attempt)
        save(args.output/'complete-private.json',dict(status='complete',files_sha256={name:sha((args.output/name).read_bytes())
            for name in ('summary.json','rows.json','secondary.json','binding-private.json','attempt-private.json','metric-cache-provenance-private.json')}))
        print(json.dumps(summary),flush=True);return summary
    except Exception:
        attempt['status']='failed';save(args.output/'attempt-private.json',attempt)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('preflight','run'))
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--preflight',type=Path);args=p.parse_args()
    if (args.action=='run')!=(args.preflight is not None):p.error('Only a real run requires its completed synthetic preflight')
    for name in ('manifest','preflight','output'):
        if getattr(args,name) is not None:setattr(args,name,getattr(args,name).resolve())
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS'):os.environ[name]='1'
    args.output=fresh_output(args.output)
    try:execute(args);return 0
    except Exception as exc:
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True);return 1


if __name__=='__main__':raise SystemExit(main())

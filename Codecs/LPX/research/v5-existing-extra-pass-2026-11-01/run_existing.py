"""Frozen two-arm P4 whole-pass pilot; every helper/candidate is journaled."""
from __future__ import annotations
import argparse
from collections import Counter
import importlib
import inspect
import json
from numbers import Integral
from pathlib import Path
import time
import traceback

from extra_policy import ARMS,eligible_groups,slot_views,whole_roles
from extra_runtime import (HERE,PREFIX,SOURCE_COMMIT,Inputs,VALUE_KEYS,sha,save,source_snapshot,load_manifest,
    bind_production,production_snapshot,load_production,check_origins,bridge_native,no_initial_fits,
    target_for,WholeEvaluator,distinct_whole,equal)
from prepare_existing import current_runtime
from secondary import choose_secondary
from run_pilot import persist_stream


def timed():return time.perf_counter(),time.process_time()
def elapsed(t):return dict(wall_seconds=time.perf_counter()-t[0],cpu_seconds=time.process_time()-t[1])


def check_extra_origin(C,root,inventory):
    name=PREFIX+'tools/refine_speech_extras.py';expected=(root/name).resolve()
    if Path(C.extras.__file__).resolve()!=expected or sha(expected.read_bytes())!=inventory[name]:
        raise ValueError('Existing-extra operator origin or bound source bytes differ')


def validate_report(report,planned,causal,baseline_sse):
    indices=planned['eligible_group_indices'];count=len(indices)
    for name,value in (('eligible_group_indices',indices),('eligible_active_groups',count),
            ('initial_active_extras',planned['initial_active_extras']),('max_trial_evaluations',49*count),
            ('atomic_trial_bound',49 if causal else 33),('causal_positions',causal),('horizon',160),('max_checkpoints',4)):
        equal(report[name],value)
    visited=report['visited_group_indices']
    if (visited!=indices[:len(visited)] or report['completed_active_groups']!=len(visited) or
            report['all_eligible_groups_visited']!=(visited==indices) or
            report['preserved_unplayed_extras']!=planned['initial_active_extras']-count or
            not 0<=report['trial_evaluations']<=49*count or report['cpu_budget']['limit_seconds'] is not None):
        raise AssertionError('Actual pass coverage, trials or no-cutoff policy differs')
    if not count:
        if report['stopped_by']!='no_active_played_extras' or visited or report['trial_evaluations']:
            raise AssertionError('A zero-eligibility reset did not honestly no-op')
    elif baseline_sse==0:
        if report['stopped_by']!='zero_error' or visited or report['trial_evaluations']:
            raise AssertionError('Zero-error skip was reported as visited work')
    elif report['stopped_by']!='complete' or visited!=indices:
        raise AssertionError('The full-budget real pass did not cover every eligible group')


def validate_fields(C,base_blob,blob,indices):
    before,after=C.compact.unpack(base_blob),C.compact.unpack(blob)
    if blob[:20]!=base_blob[:20] or after[:7]!=before[:7] or len(blob)>len(base_blob):
        raise AssertionError('An optional-only candidate changed base/header/size invariants')
    allowed=set(indices)
    for index,((pos,amp),(oldpos,oldamp)) in enumerate(zip(after[7],before[7])):
        if index not in allowed and (amp!=oldamp or amp and pos!=oldpos):
            raise AssertionError('An inactive or unplayed pulse changed')
        if index in allowed and amp and index*40+pos>=after[0]:raise AssertionError('A played pulse moved into the unplayed tail')
    if sum(a!=0 for p,a in after[7])>sum(a!=0 for p,a in before[7]):raise AssertionError('An extra was added')


def retaining_sink(base,index,folder,attempt,out,event,captures):
    """Publish exact callback bytes and caller-owned journal before returning."""
    event['captured_streams']=[]
    cost=dict(wall_seconds=0.,cpu_seconds=0.,callback_calls=0,included_in_actual_helper_time=True)
    event['callback_persistence_cost']=cost
    def sink(blob,score):
        began=timed()
        try:
            if isinstance(score,bool) or not isinstance(score,Integral):
                raise AssertionError('Sink score is not exact integer full SSE')
            blob=bytes(blob);identifier=len(captures)
            if any(blob==previous for previous,sse in captures):raise AssertionError('Duplicate callback publication')
            meta=dict(**persist_stream(folder/'catalogue'/('candidate-%04d.l4hy'%identifier),blob,index,base),
                id=identifier,reported_full_sse=int(score),
                verification_status='Producer-verified callback; independent caller audit pending')
            captures.append((blob,int(score)));event['captured_streams'].append(meta)
            # The later helper/native/metric path may fail. This write is part
            # of the callback and completes before the producer can continue.
            save(out/'attempt-private.json',attempt)
        finally:
            measured=elapsed(began)
            for key in ('wall_seconds','cpu_seconds'):cost[key]+=measured[key]
            cost['callback_calls']+=1
    return sink


def local_call(base,index,base_blob,reference,C,decoder,verifier,folder,attempt,out,phase,causal,counters):
    folder.mkdir(parents=True)
    meta=base['segments'][index]
    if sha(base_blob)!=meta['stream_sha256'] or len(base_blob)!=meta['file_bytes']:
        raise AssertionError('The helper input differs from the already pinned original bytes')
    plan=base['existing_extra_plan'][index];captures=[]
    event=dict(phase=phase,baseline_id=base['id'],reset=index,causal_positions=causal,status='started')
    attempt['synthetic_calls' if phase=='synthetic' else 'helper_calls'].append(event)
    sink=retaining_sink(base,index,folder,attempt,out,event,captures)
    save(out/'attempt-private.json',attempt);start=timed()
    try:
        selected,pcm,report,raw=C.extras.refine_existing_extras(reference,base_blob,decoder,
            max_bytes=min(base['stream_bytes'],65535),causal_positions=causal,horizon=160,
            max_trial_evaluations=plan['max_trial_evaluations'],cpu_seconds=None,max_checkpoints=4,
            candidate_sink=sink,speech=not base['nonspeech'])
    except Exception as exc:
        event.update(status='helper-failed',exception_type=type(exc).__name__,helper_cost=elapsed(start))
        save(out/'attempt-private.json',attempt)
        raise
    helper_cost=elapsed(start)
    save(folder/'helper-return-private.json',dict(report=report,helper_cost=helper_cost,callbacks=len(captures),
        callback_persistence_cost=event['callback_persistence_cost']))
    event.update(status='returned',helper_cost=helper_cost);save(out/'attempt-private.json',attempt)
    if not captures or captures[0][0]!=base_blob or len(set(b for b,s in captures))!=len(captures):
        raise AssertionError('The ordered distinct catalogue lost its original baseline')
    if report['candidate_sink_streams']!=len(captures) or len(report['candidates'])!=len(captures):
        raise AssertionError('Sink/catalogue publication counts differ')
    if selected is None or raw is None:raise AssertionError('The original feasible input was lost')
    validate_report(report,plan,causal,captures[0][1])
    for key,value in (('samples',meta['samples']),('profile',4),('baseline_bytes',len(base_blob)),
            ('max_file_bytes',min(base['stream_bytes'],65535)),('file_bytes',len(selected)),('raw_file_bytes',len(raw)),
            ('frozen_base_header_exact',True),('inactive_unplayed_pulses_preserved',True),('native_model_pwm_exact',True)):
        equal(report[key],value)
    began=timed();metas=event['captured_streams']
    for meta,(blob,score) in zip(metas,captures):
        actual=Path(meta['path']).read_bytes()
        if actual!=blob or sha(actual)!=meta['stream_sha256'] or meta['reported_full_sse']!=score:
            raise AssertionError('The callback-persisted catalogue bytes or score changed')
    persistence_audit=elapsed(began);began=timed();catalogue=[];models=[]
    for identifier,((blob,claimed),row) in enumerate(zip(captures,report['candidates'])):
        validate_fields(C,base_blob,blob,plan['eligible_group_indices'])
        decoded=verifier.decode(blob,meta['samples'],4);delta=reference.astype(C.np.int64)-decoded.astype(C.np.int64)
        actual=int(C.np.sum(delta*delta));models.append(decoded)
        if (row['id']!=identifier or row['file_bytes']!=len(blob) or row['full_sse']!=actual or claimed!=actual or
                not 0<=row['completed_active_groups']<=len(plan['eligible_group_indices'])):
            raise AssertionError('Actual serialized catalogue order/bytes/full SSE differs')
        catalogue.append(dict(id=identifier,blob=blob,sse=actual,labels=row['labels']))
        metas[identifier]['verification_status']='Independent caller model/common/v5 PCM/PWM and full SSE passed'
        counters['captured_full_sse_checks']+=1;counters['captured_full_sse_samples']+=len(decoded)
    model_cost=elapsed(began);began=timed();slots,slot_proof=slot_views(catalogue,report['checkpoints'])
    if [r['target_active_groups'] for r in report['checkpoints']]!=[(len(plan['eligible_group_indices'])*k+3)//4 for k in range(1,5)]:
        raise AssertionError('The four initial-active coverage goals changed')
    if selected is None or raw is None or selected!=captures[report['selected_id']][0] or raw!=captures[report['raw_id']][0]:
        raise AssertionError('Returned best completed candidates are not in the catalogue')
    if pcm is None or not C.np.array_equal(pcm,models[report['selected_id']]):raise AssertionError('Returned PCM differs from its serialized candidate')
    policy_cost=elapsed(began)
    details=dict(index=index,helper_cost=helper_cost,report=report,captured_streams=metas,
        slot_provenance=slot_proof,callback_persistence_cost=event['callback_persistence_cost'],
        captured_stream_integrity_audit_cost=persistence_audit,independent_catalogue_sse_and_native_audit_cost=model_cost,
        catalogue_policy_audit_cost=policy_cost)
    save(folder/'local-private.json',details);event['status']='complete';save(out/'attempt-private.json',attempt)
    return dict(index=index,catalogue=catalogue,slot_blobs=slots,selected=bytes(selected),raw=bytes(raw)),details


def synthetic(C,decoder,only,out,attempt,counters,arms,context):
    begin=timed();rows=[];verifier=WholeEvaluator(C,decoder,only,context+'-synthetic')
    for n,kind in ((640,'causal-target'),(640,'zero-error'),(201,'unplayed-noop')):
        frames=(n+319)//320;spectra=[[1,2,4,6,8,10,13,17,23,29] for _ in range(frames)]
        params=[[8,40,0] for _ in range(frames*2)];pulses=[[5,8 if not i%2 else -8] for i in range(frames*16)];pulses[10][0]=0
        extras=[[-1,0] for _ in range(frames*8)];extras[5]=[30,-8]
        blob=C.compact.pack(n,4,spectra,params,pulses,0,0,extras=extras)[0]
        target=C.compact.decode_model(blob)
        if kind=='causal-target':
            extras[5]=[0,-8];target=C.compact.decode_model(C.compact.pack(n,4,spectra,params,pulses,0,0,extras=extras)[0])
        elif kind=='unplayed-noop':target=C.np.clip(target.astype(C.np.int64)+C.np.where(C.np.arange(n)%2,2,-2),-32768,32767).astype(C.np.int16)
        path=out/'synthetic-inputs'/(kind+'.l4hy');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(blob)
        eligible=eligible_groups(n,C.compact.unpack(blob)[7])
        base=dict(id=-1,profile=4,nonspeech=False,samples=n,stream_bytes=len(blob),
            segments=[dict(path=str(path.resolve()),stream_sha256=sha(blob),file_bytes=len(blob),index=0,start=0,samples=n,profile=4)],
            existing_extra_plan=[dict(index=0,eligible_group_indices=eligible,eligible_active_groups=len(eligible),
                initial_active_extras=1,max_trial_evaluations=49*len(eligible))])
        for arm in arms:
            local,detail=local_call(base,0,blob,target,C,decoder,verifier,out/'synthetic'/kind/arm,attempt,out,'synthetic',arm=='causal',counters)
            if kind!='causal-target' and local['selected']!=blob:raise AssertionError('Synthetic no-work control changed bytes')
            if kind=='causal-target' and arm=='causal' and detail['report']['candidates'][detail['report']['selected_id']]['full_sse']!=0:
                raise AssertionError('The known causal regression did not reach its exact target')
            rows.append(dict(kind=kind,arm=arm,helper_cost=detail['helper_cost'],report=detail['report']))
    result=dict(status='PASS',helper_calls=len(rows),cost=elapsed(begin),calls=rows,native_model_counters=dict(verifier.counts))
    save(out/'synthetic-private.json',result);return result


def run_record(job,base,target,C,decoder,evaluator,inputs,out,attempt,counters,prior):
    begin=timed();folder=out/'records'/('job-%02d'%job['id']);folder.mkdir(parents=True)
    record_event=dict(id=job['id'],status='started',completed_whole_ids=[])
    attempt['records'].append(record_event);save(out/'attempt-private.json',attempt)
    baseline=tuple(inputs.stream(meta) for meta in base['segments'])
    anchor=evaluator.measure(baseline,base,target,not base['nonspeech'],dict(job_id=job['id'],role='baseline-before-helper'))
    for key in VALUE_KEYS:equal(anchor[key],base['stored_expected_whole_value'][key])
    save(folder/'baseline-anchor-private.json',dict(status='complete',value=anchor,segments=base['segments']))
    record_event['baseline_anchor_path']=str((folder/'baseline-anchor-private.json').resolve())
    save(out/'attempt-private.json',attempt)
    locals=[];details=[]
    for index in job['reset_indices']:
        meta=base['segments'][index];at,n=meta['start'],meta['samples']
        local,detail=local_call(base,index,baseline[index],target[at:at+n],C,decoder,evaluator,folder/('reset-%02d'%index),attempt,out,'corpus',job['causal_positions'],counters)
        locals.append(local);details.append(detail)
    audit=timed();choices=distinct_whole(whole_roles(baseline,locals));values=[];artifacts=[]
    if len(choices)>9 or choices[0]['blobs']!=baseline:raise AssertionError('The nine-role fixed whole pool changed')
    for choice in choices:
        value=evaluator.measure(choice['blobs'],base,target,not base['nonspeech'],dict(job_id=job['id'],chain_id=choice['id']))
        flags=C.chain._admission(value,anchor)
        values.append(dict(id=choice['id'],labels=choice['labels'],stream_bytes=choice['stream_bytes'],full_flash_bytes=None,
            **value,**flags,automatic_quality_eligible=all(flags.values())))
        artifacts.append(dict(id=choice['id'],segments=[persist_stream(folder/'whole'/('chain-%02d'%choice['id'])/('reset-%02d.l4hy'%i),b,i,base)
            for i,b in enumerate(choice['blobs'])]))
        # Preserve every completed admission, even if the next measurement or
        # final decision fails. No later metric must run before this is durable.
        save(folder/'whole'/('chain-%02d'%choice['id'])/'admission-private.json',
            dict(status='complete',whole_row=values[-1],whole_chain=artifacts[-1]))
        save(folder/'whole-progress-private.json',dict(status='in-progress',whole_rows=values,whole_chains=artifacts))
        record_event['completed_whole_ids'].append(choice['id']);save(out/'attempt-private.json',attempt)
    decisions=[]
    for percent in (100,95,90):
        decision=C.chain.choose_budget(values,job['whole_caps'][str(percent)])
        old=choose_secondary([r for r in prior if r['baseline_id']==base['id']],decision['cap'],C.chain._admission,anchor)
        chosen=None if decision['selected_id'] is None else values[decision['selected_id']]
        if percent==100 and (chosen is None or (chosen['score'],chosen['stream_bytes'])>(anchor['score'],base['stream_bytes'])):
            raise AssertionError('The original full-budget baseline regressed')
        secondary=None if old is None else dict(study=old['study'],arm=old['arm'],job_id=old['job_id'],candidate_id=old['candidate_id'],
            stream_bytes=old['stream_bytes'],score=old['value']['score'],provenance='Prior saved bridged measurement, not fresh and not seeded')
        decisions.append(dict(percent=percent,**decision,secondary_prior_best=secondary))
    result=dict(**job,status='complete',baseline_bytes=base['stream_bytes'],baseline_samples=base['samples'],locals=details,
        whole_rows=values,whole_chains=artifacts,decisions=decisions,whole_audit_cost=elapsed(audit),
        helper_cpu=sum(r['helper_cost']['cpu_seconds'] for r in details),record_workflow_cost=elapsed(begin))
    save(folder/'result-private.json',result);record_event['status']='complete'
    save(out/'attempt-private.json',attempt);print(json.dumps(dict(status='record-complete',id=job['id'],arm=job['arm'])),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','baselines','native-cases','output'):parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--arm',choices=ARMS);parser.add_argument('--preflight',type=Path);parser.add_argument('--preflight-only',action='store_true')
    args=parser.parse_args()
    if SOURCE_COMMIT is None:parser.error('Await exact frozen integration source')
    if args.preflight_only==bool(args.arm):parser.error('Choose synthetic preflight or one actual arm')
    if not args.preflight_only and args.preflight is None:parser.error('A same-source preflight is required')
    for name in ('source_root','baselines','native_cases','output'):setattr(args,name,getattr(args,name).resolve())
    if args.preflight is not None:args.preflight=args.preflight.resolve()
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):parser.error('Use fresh private ignored build output')
    args.output.mkdir(parents=True);begin=timed();inputs=Inputs();counters=Counter()
    attempt=dict(status='started',helper_calls=[],synthetic_calls=[],records=[],forbidden_fit_or_build_attempts=0)
    save(args.output/'attempt-private.json',attempt)
    try:
        sources=source_snapshot();manifest=load_manifest(args.baselines,inputs)
        inventory=bind_production(args.source_root,SOURCE_COMMIT);native,bridge=bridge_native(args.source_root,args.native_cases,inputs)
        C=load_production(args.source_root);C.extras=importlib.import_module('refine_speech_extras');check_origins(args.source_root)
        check_extra_origin(C,args.source_root,inventory)
        runtime=current_runtime()
        if runtime!=manifest['runtime'] or inventory!=manifest['production_sources'] or bridge!=manifest['native_bridge']:
            raise ValueError('Prepared source/native/runtime context changed')
        signature=inspect.signature(C.extras.refine_existing_extras)
        if signature.parameters['causal_positions'].default is not False:raise ValueError('The frozen optional-pass default changed')
        context=sha(json.dumps(dict(source=inventory,native=bridge),sort_keys=True).encode())
        if args.preflight is not None:
            smoke=inputs.json(args.preflight/'summary.json');proof=inputs.json(args.preflight/'binding-private.json')
            if smoke['status']!='PASS' or smoke['corpus_helper_calls'] or smoke['synthetic_helper_calls']!=6 or proof['research_sources']!=sources or proof['source_context']!=context:
                raise ValueError('The six-call same-source preflight is not complete')
        jobs=[] if args.preflight_only else [j for j in manifest['jobs'] if j['arm']==args.arm]
        if jobs and (len(jobs)!=6 or sum(len(j['reset_indices']) for j in jobs)!=10):raise ValueError('The fixed arm shard differs')
        bases={b['id']:b for b in manifest['baselines']};targets={i:target_for(bases[i],C,inputs) for i in {j['baseline_id'] for j in jobs}}
        binding=dict(source_commit=SOURCE_COMMIT,source_root=str(args.source_root),production_sources=inventory,research_sources=sources,
            source_context=context,runtime=runtime,native_bridge=bridge,input_files_sha256=inputs.pins,baselines_path=str(args.baselines),
            assigned_jobs=[j['id'] for j in jobs],arm=args.arm,preparation_cost=elapsed(begin))
        save(args.output/'binding-private.json',binding)
        with no_initial_fits(attempt,args.output),C.BatchSession('batch',prebuilt=native['common']) as common,C.BatchSession('batch',prebuilt=native['v5-only']) as only:
            warm=synthetic(C,common,only,args.output,attempt,counters,ARMS if args.preflight_only else (args.arm,),context)
            evaluator=WholeEvaluator(C,common,only,context)
            results=[run_record(j,bases[j['baseline_id']],targets[j['baseline_id']],C,common,evaluator,inputs,args.output,attempt,counters,manifest['prior_rows']) for j in jobs]
        if sources!=source_snapshot() or inventory!=production_snapshot(args.source_root) or attempt['forbidden_fit_or_build_attempts']:
            raise ValueError('Frozen study or no-initial-fit/build guard changed')
        check_origins(args.source_root);check_extra_origin(C,args.source_root,inventory);inputs.verify()
        if any(r['status']!='complete' for r in attempt['helper_calls']+attempt['synthetic_calls']):raise AssertionError('A planned helper did not complete')
        if (len(attempt['helper_calls'])!=(0 if args.preflight_only else 10) or
                len(attempt['synthetic_calls'])!=(6 if args.preflight_only else 3) or
                len(results)!=(0 if args.preflight_only else 6) or
                any([d['percent'] for d in r['decisions']]!=[100,95,90] for r in results)):
            raise AssertionError('Actual terminal helper/record/cap scope differs')
        save(args.output/'results-private.json',results);save(args.output/'metric-cache-provenance-private.json',evaluator.provenance)
        summary=dict(status='PASS',arm=args.arm,preflight_only=args.preflight_only,arm_records=len(results),
            corpus_helper_calls=len(attempt['helper_calls']),synthetic_helper_calls=len(attempt['synthetic_calls']),actual_cap_views=sum(len(r['decisions']) for r in results),
            synthetic_cost=warm['cost'],total_cost=elapsed(begin),counters=dict(counters),whole_counters=dict(evaluator.counts),
            historical_preflight_shared_cost_reference=manifest['historical_preflight']['preflight_path'],
            shared_historical_synthetic_calls=6,final_paid_campaign_synthetic_calls_planned=18,
            initial_fits=0,native_builds=0,target_jobs=0,prior_measurements_not_seeded=True)
        save(args.output/'summary.json',summary);attempt.update(status='complete');save(args.output/'attempt-private.json',attempt)
        print(json.dumps(summary),flush=True);return 0
    except Exception as exc:
        attempt.update(status='failed',exception_type=type(exc).__name__,total_cost=elapsed(begin));save(args.output/'attempt-private.json',attempt)
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True);return 1


if __name__=='__main__':raise SystemExit(main())

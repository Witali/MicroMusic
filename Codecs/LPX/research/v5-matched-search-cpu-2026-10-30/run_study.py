"""Fixed matched-CPU corpus arms, finite whole assembly and honest journals."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback

from prepare_baselines import load_helper
from study_policy import SINGLE,TRAJECTORY,distinct_whole,local_frontier,whole_views
from study_runtime import (HERE,VALUE_KEYS,WholeEvaluator,bind_production,check_origins,
    equal,load_production,no_initial_fits,production_snapshot,save,sha,source_snapshot)


def timed():
    return time.perf_counter(),time.process_time()


def elapsed(start):
    return dict(wall_seconds=time.perf_counter()-start[0],cpu_seconds=time.process_time()-start[1])


def source_context(inventory,natives):
    return sha(json.dumps(dict(source=inventory,native=natives),sort_keys=True).encode())


def target_for(base,C,inputs):
    descriptor = base['reference']
    raw = inputs.read(descriptor['path'],descriptor['file_sha256'])
    if len(raw)!=descriptor['file_bytes']:
        raise ValueError('Reference file cost differs')
    pcm,rate = C.sf.read(descriptor['path'],dtype='int16')
    if rate!=8000 or pcm.ndim!=1 or len(pcm)!=base['samples'] or sha(pcm.astype('<i2').tobytes())!=descriptor['pcm16_sha256']:
        raise ValueError('Original reference geometry or PCM differs')
    plan = C.plan_level(pcm,base['mode'])
    target,clips = C.quantize_target(pcm,plan)
    if clips or sha(target.astype('<i2').tobytes())!=base['target_reference_pcm16_sha256']:
        raise ValueError('Declared whole target differs')
    for name in ('policy','gain','gain_db','output_level_matches_original'):
        equal(plan[name],base['level'][name])
    return target


def warmup(C,common,only,out):
    start = timed()
    rows = []
    smoke = WholeEvaluator(C,common,only,'synthetic-warmup-only')
    sse_checks = 0
    n = 5120
    for profile in (4,6):
        blob = C.compact.pack(n,profile,[[1+2*i for i in range(10)] for _ in range(16)],
            [[8,40,6] for _ in range(32)],[[0,8 if profile==4 else 7] for _ in range(256)],
            0,0,extras=[[-1,0] for _ in range(128)])[0]
        decoded = C.compact.decode_model(blob)
        delta = C.np.where(C.np.arange(n)%17<8,5,-5)
        reference = C.np.clip(decoded.astype(C.np.int64)+delta,-32768,32767).astype(C.np.int16)
        for arm in ('single-path','trajectory'):
            captures = []
            began = timed()
            if arm=='single-path':
                selected,_,report,raw = C.single.refine(reference,blob,common,len(blob),frame_limit=1,
                    spectral_candidates=1,lookahead=320,excitation_horizon=160,passes=1,
                    refit=True,speech=True,cpu_seconds=None,candidate_sink=lambda b,s:captures.append((bytes(b),s)))
            else:
                selected,_,report,raw = C.trajectory.refine(reference,blob,common,len(blob),frame_limit=1,
                    window_frames=2,beam_width=1,spectral_candidates=1,excitation_candidates=1,
                    excitation_horizon=160,max_evaluations=32,selection='conservative',
                    capacity_policy='amplitude',allocation_evaluations=0,rate_lambda=0.,
                    screening='local',screening_horizon=320,speech=True,cpu_seconds=None,
                    candidate_sink=lambda b,s:captures.append((bytes(b),s)))
            helper_cost = elapsed(began)
            for candidate,score in captures:
                actual = C.compact.decode_model(candidate)
                delta = reference.astype(C.np.int64)-actual.astype(C.np.int64)
                if float(score)!=int(C.np.sum(delta*delta)):
                    raise AssertionError('Synthetic callback SSE differs from serialized model')
                sse_checks += 1
            base = dict(profile=profile,samples=n,segments=[dict(samples=n)])
            anchor = smoke.measure((blob,),base,reference,True,dict(arm=arm,profile=profile,role='baseline'))
            equal(anchor['metrics'],report['baseline'])
            for name,candidate in (('selected',selected),('raw',raw)):
                if candidate is not None:
                    smoke.measure((bytes(candidate),),base,reference,True,dict(arm=arm,profile=profile,role=name))
            rows.append(dict(arm=arm,profile=profile,cost=helper_cost,sink_callbacks=len(captures),
                cpu_budget=report['cpu_budget']))
    receipt = dict(status='complete',fixture_samples=n,synthetic_only=True,helper_calls=4,
        new_initial_fits=0,cost=elapsed(start),calls=rows,serialized_sse_checks=sse_checks,
        whole_smoke_counters=dict(smoke.counts))
    save(out/'warmup.json',receipt)
    return receipt


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
    settings = SINGLE if job['arm']=='single-path' else TRAJECTORY
    helper = C.single.refine if job['arm']=='single-path' else C.trajectory.refine
    selected,pcm,report,raw = helper(reference,baseline_blob,common,job['local_byte_cap'],
        speech=job['speech'],cpu_seconds=job['cpu_seconds_per_reset'],candidate_sink=sink,**settings)
    cost = elapsed(began)
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


def run_arm(job,base,target,C,common,evaluator,inputs,out,attempt,counters,prior):
    folder = out/'arms'/('job-%03d'%job['id'])
    folder.mkdir(parents=True)
    whole_start = timed()
    baseline = tuple(inputs.stream(meta) for meta in base['segments'])
    local_rows,local_summaries = [],[]
    for index in job['edited_segments']:
        geometry = base['segments'][index]
        at,n = geometry['start'],geometry['samples']
        counters['actual_helper_calls_started'] += 1
        row,summary = local_call(job,index,base,baseline[index],target[at:at+n],C,common,folder,attempt,out,counters)
        local_rows.append(row)
        local_summaries.append(summary)
    audit_start = timed()
    previous = () if prior is None else prior['blobs']
    views = whole_views(baseline,local_rows)
    choices = distinct_whole(views,previous)
    measured,artifacts = [],[]
    before = evaluator.counts.copy()
    for choice in choices:
        event = dict(job_id=job['id'],chain_id=choice['id'],baseline_id=base['id'])
        value = evaluator.measure(choice['blobs'],base,target,job['speech'],event)
        if not measured:
            if choice['blobs']!=baseline:
                raise AssertionError('The fixed current baseline disappeared')
            for name in VALUE_KEYS:
                equal(value[name],base['canonical_whole_value'][name])
            anchor = value
        flags = C.chain._admission(value,anchor)
        measured.append(dict(id=choice['id'],labels=choice['labels'],stream_bytes=choice['stream_bytes'],
            full_flash_bytes=None,**value,**flags,automatic_quality_eligible=all(flags.values())))
        parts = [persist_stream(folder/'whole'/('chain-%03d'%choice['id'])/('segment-%03d.l4hy'%i),blob,i,base)
            for i,blob in enumerate(choice['blobs'])]
        artifacts.append(dict(id=choice['id'],segments=parts))
    decisions = []
    for percent in (100,95,90):
        decision = C.chain.choose_budget(measured,job['whole_byte_caps'][str(percent)])
        chosen = None if decision['selected_id'] is None else measured[decision['selected_id']]
        if percent==100 and (chosen is None or (chosen['score'],chosen['stream_bytes'])>(anchor['score'],sum(map(len,baseline)))):
            raise AssertionError('A full-budget current baseline regressed')
        if prior is not None:
            for old in prior['rows']:
                if old['automatic_quality_eligible'] and old['stream_bytes']<=decision['cap']:
                    if chosen is None or (chosen['score'],chosen['stream_bytes'])>(old['score'],old['stream_bytes']):
                        raise AssertionError('A cumulative 2+8 incumbent regressed')
        decisions.append(dict(percent=percent,**decision,incumbent_nonregression=True))
    audit_cost = elapsed(audit_start)
    standalone_cpu = sum(row['helper_cost']['cpu_seconds'] for row in local_summaries)
    prior_cpu = 0. if prior is None else prior['result']['total_helper_cpu']
    result = dict(**job,status='complete',baseline_samples=base['samples'],reset_segments=len(baseline),
        tier_label='2' if prior is None else 'cumulative-2+8',locals=local_summaries,
        whole_rows=measured,whole_chains=artifacts,decisions=decisions,
        total_helper_cpu=standalone_cpu,total_helper_wall=sum(row['helper_cost']['wall_seconds'] for row in local_summaries),
        cumulative_total_helper_cpu=standalone_cpu+prior_cpu,prior2_helper_cpu=prior_cpu,
        new_whole_view_count=sum(blobs is not None for _,blobs in views),prior2_whole_views=len(previous),
        whole_audit_cost=audit_cost,whole_audit_counters=dict(evaluator.counts-before),total_arm_cost=elapsed(whole_start))
    save(folder/'result-private.json',result)
    counters['arm_records_completed'] += 1
    attempt['arm_records'].append(dict(job_id=job['id'],status='complete',baseline_id=base['id'],arm=job['arm'],
        cpu_seconds_per_reset=job['cpu_seconds_per_reset']))
    attempt['counters'] = dict(counters)
    save(out/'attempt-private.json',attempt)
    print(json.dumps(dict(status='arm-complete',job=job['id'],phase=job['phase'],source_ordinal=job['source_ordinal'],
        profile=job['profile'],arm=job['arm'],tier=job['cpu_seconds_per_reset'],whole_rows=len(measured))),flush=True)
    return dict(result=result,rows=measured,blobs=[choice['blobs'] for choice in choices])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','baselines','original-study','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--source-commit',required=True)
    parser.add_argument('--shard',required=True,type=int,choices=(0,1))
    parser.add_argument('--warmup-only',action='store_true')
    args = parser.parse_args()
    for name in ('source_root','baselines','original_study','output'):
        setattr(args,name,getattr(args,name).resolve())
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):
        parser.error('Use fresh ignored private build output in this research worktree')
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS'):
        os.environ[name] = '1'
    args.output.mkdir(parents=True)
    attempt = dict(status='started',shard=args.shard,helper_calls=[],arm_records=[],active_helper=None,
        forbidden_fit_or_build_attempts=0)
    save(args.output/'attempt-private.json',attempt)
    started = timed()
    counters = Counter()
    try:
        sources = source_snapshot()
        helper = load_helper()
        inputs = helper.Inputs()
        manifest = json.loads(inputs.read(args.baselines))
        if manifest['status']!='prepared-not-launched' or len(manifest['jobs'])!=248 or len(manifest['baselines'])!=104:
            raise ValueError('The predeclared preparatory baseline scope differs')
        for path,digest in manifest['inputs_sha256'].items():
            inputs.read(path,digest)
        original = json.loads(inputs.read(args.original_study/'binding-private.json'))
        for path,digest in original['input_files_sha256'].items():
            inputs.read(path,digest)
        inventory = bind_production(args.source_root,args.source_commit)
        expected_src = {k:v for k,v in original['source']['core'].items() if k.startswith('Codecs/LPX/01_ACTIVE_Q0_CODEC/src/')}
        actual_src = {k:v for k,v in inventory.items() if k.startswith('Codecs/LPX/01_ACTIVE_Q0_CODEC/src/')}
        if expected_src!=actual_src:
            raise ValueError('Prebuilt native libraries require exact unchanged original C source')
        native = {}
        for name,digest in original['native_libraries_sha256'].items():
            inputs.read(args.original_study/'native'/name,digest)
            native[name] = digest
        C = load_production(args.source_root)
        assigned = [job for job in manifest['jobs'] if job['source_ordinal']%2==args.shard]
        bases = {base['id']:base for base in manifest['baselines']}
        targets = {identifier:target_for(bases[identifier],C,inputs) for identifier in {job['baseline_id'] for job in assigned}}
        prep_cost = elapsed(started)
        binding = dict(source_commit=args.source_commit,production_sources=inventory,research_sources=sources,
            module_origins=check_origins(args.source_root),inputs_sha256=inputs.pins,source_root=str(args.source_root),
            baselines_path=str(args.baselines),assigned_jobs=[job['id'] for job in assigned],shard=args.shard,
            settings=dict(single=SINGLE,trajectory=TRAJECTORY),preparation_cost=prep_cost,
            source_context=source_context(inventory,native),runtime=dict(python=sys.version,
                packages={name:__import__('importlib.metadata',fromlist=['version']).version(name) for name in ('numpy','numba','scipy','pystoi','soundfile')},
                threads={name:os.environ[name] for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS')}))
        save(args.output/'binding-private.json',binding)
        with no_initial_fits(attempt,args.output), C.BatchSession('batch',prebuilt=args.original_study/'native/common.so') as common, C.BatchSession('batch',prebuilt=args.original_study/'native/v5-only.so') as only:
            warming = warmup(C,common,only,args.output)
            if args.warmup_only:
                assigned = []
            evaluator = WholeEvaluator(C,common,only,binding['source_context'])
            prior,results = {},[]
            for job in assigned:
                base = bases[job['baseline_id']]
                old = prior.get((base['id'],job['arm'])) if job['cpu_seconds_per_reset']==8 else None
                if job['cpu_seconds_per_reset']==8 and old is None:
                    raise AssertionError('Cumulative 2+8 requires a completed same-arm 2-second whole pool')
                value = run_arm(job,base,targets[base['id']],C,common,evaluator,inputs,args.output,attempt,counters,old)
                if job['cpu_seconds_per_reset']==2:
                    prior[(base['id'],job['arm'])] = value
                results.append(value['result'])
        guard_start = timed()
        if sources!=source_snapshot() or inventory!=production_snapshot(args.source_root) or attempt['forbidden_fit_or_build_attempts']:
            raise ValueError('Executing source or no-initial-fit contract changed')
        check_origins(args.source_root)
        inputs.verify()
        if any(row['status']!='complete' for row in attempt['helper_calls']):
            raise AssertionError('An actual helper call did not complete')
        summary = dict(status='PASS',shard=args.shard,warmup_only=args.warmup_only,
            arm_records=len(results),helper_calls=len(attempt['helper_calls']),new_initial_fits=0,
            actual_cost=elapsed(started),preparation_cost=prep_cost,warmup_cost=warming['cost'],
            final_guard_cost=elapsed(guard_start),counters=dict(counters),whole_counters=dict(evaluator.counts),
            no_old_whole_metric_reuse=True)
        save(args.output/'results-private.json',results)
        save(args.output/'metric-cache-provenance-private.json',evaluator.provenance)
        save(args.output/'summary.json',summary)
        attempt.update(status='complete',summary=summary)
        save(args.output/'attempt-private.json',attempt)
        print(json.dumps(summary),flush=True)
        return 0
    except Exception as exc:
        attempt.update(status='failed',exception_type=type(exc).__name__,actual_cost=elapsed(started),counters=dict(counters))
        save(args.output/'attempt-private.json',attempt)
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True)
        return 1


if __name__=='__main__':
    raise SystemExit(main())

"""Audit saved complete pools/decisions/frontiers; forbid new numerical work."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from contextlib import ExitStack
import importlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
TOP=HERE.parents[1]
sys.path.insert(0,str(TOP))
import run_existing as producer
from extra_policy import slot_views,whole_roles,validate_caps
from extra_runtime import (Inputs,SOURCE_COMMIT,VALUE_KEYS,bind_production,check_origins,distinct_whole,
    equal,load_manifest,load_production,no_initial_fits,production_snapshot,save,sha,source_snapshot)
from secondary import PRIOR_ARMS,choose_secondary
from frontier_policy import classify,failed,frontier,numeric,outcome


def own_sources():
    names=('project_existing.py','frontier_policy.py','test_frontier_policy.py','PROTOCOL.md')
    return {name:sha((HERE/name).read_bytes()) for name in names}


def origin(row):return {k:row[k] for k in ('study','arm','job_id','candidate_id')}
def prior_order(row):return (0 if row['study']=='joint-rate-v1' else 1,PRIOR_ARMS[row['study']].index(row['arm']),row['job_id'],row['candidate_id'])
def key(parts):return tuple(parts)
def values_equal(left,right):
    for name in VALUE_KEYS:equal(left[name],right[name])


def audit_local(detail,event,base,C,inputs,folder):
    index=detail['index'];report=detail['report'];plan=base['existing_extra_plan'][index]
    if detail!=inputs.json(folder/'local-private.json'):raise ValueError('Local terminal receipt differs')
    returned=inputs.json(folder/'helper-return-private.json')
    if (returned['report']!=report or returned['helper_cost']!=detail['helper_cost'] or event['status']!='complete' or
            event['captured_streams']!=detail['captured_streams'] or event['helper_cost']!=detail['helper_cost'] or
            returned['callback_persistence_cost']!=detail['callback_persistence_cost'] or
            event['callback_persistence_cost']!=detail['callback_persistence_cost'] or
            not detail['callback_persistence_cost']['included_in_actual_helper_time']):
        raise ValueError('Completed callback/helper/persistence receipts differ')
    parts=[inputs.stream(meta) for meta in detail['captured_streams']]
    if (not parts or parts[0]!=inputs.stream(base['segments'][index]) or len(set(parts))!=len(parts) or
            len(parts)!=len(report['candidates']) or len(parts)!=report['candidate_sink_streams']):
        raise ValueError('Actual ordered distinct local catalogue differs')
    producer.validate_report(report,plan,report['causal_positions'],report['candidates'][0]['full_sse'])
    catalogue=[]
    for identifier,(blob,meta,row) in enumerate(zip(parts,detail['captured_streams'],report['candidates'])):
        producer.validate_fields(C,parts[0],blob,plan['eligible_group_indices'])
        if (row['id']!=identifier or meta['id']!=identifier or row['file_bytes']!=len(blob) or
                row['full_sse']!=meta['reported_full_sse'] or
                meta['verification_status']!='Independent caller model/common/v5 PCM/PWM and full SSE passed'):
            raise ValueError('Saved native/model-verified catalogue publication differs')
        catalogue.append(dict(id=identifier,blob=blob,sse=row['full_sse'],labels=row['labels']))
    slots,proof=slot_views(catalogue,report['checkpoints'])
    if proof!=detail['slot_provenance']:raise ValueError('Saved common coverage slot reconstruction differs')
    return dict(index=index,catalogue=catalogue,slot_blobs=slots,
        selected=parts[report['selected_id']],raw=parts[report['raw_id']])


def costs(records,summary,terminal):
    local=[d for r in records for d in r['locals']]
    return dict(eligible_groups=sum(d['report']['eligible_active_groups'] for d in local),
        visited_groups=sum(d['report']['completed_active_groups'] for d in local),
        actual_trials=sum(d['report']['trial_evaluations'] for d in local),
        trial_bound=sum(d['report']['max_trial_evaluations'] for d in local),
        changed_active_groups=sum(d['report']['changed_active_groups'] for d in local),
        helper_cpu=sum(d['helper_cost']['cpu_seconds'] for d in local),
        helper_wall_sum=sum(d['helper_cost']['wall_seconds'] for d in local),
        callback_persistence_cpu_included_in_helper=sum(d['callback_persistence_cost']['cpu_seconds'] for d in local),
        source_setup_search_cpu=sum(d['report']['cpu_budget']['search_cpu_seconds'] for d in local),
        source_finalization_cpu=sum(d['report']['cpu_budget']['finalization_cpu_seconds'] for d in local),
        catalogue_sse_native_audit_cpu=sum(d['independent_catalogue_sse_and_native_audit_cost']['cpu_seconds'] for d in local),
        whole_admission_and_persistence_cpu=sum(r['whole_audit_cost']['cpu_seconds'] for r in records),
        record_workflow_cpu=sum(r['record_workflow_cost']['cpu_seconds'] for r in records),
        worker_process_body_cost=summary['total_cost'],wrapper_entry_total_cost=terminal['entry_total_cost'],
        wrapper_admission_cost=terminal['admission_preparation_cost'],wrapper_terminal_guard_cost=terminal['post_admission_guard_cost'])


def audit_worker(shard,admission,arm,manifest,manifest_path,C,inputs,inventory,sources):
    binding=inputs.json(shard/'binding-private.json');attempt=inputs.json(shard/'attempt-private.json')
    summary=inputs.json(shard/'summary.json');records=inputs.json(shard/'results-private.json')
    receipt_raw=inputs.read(admission/'admission-private.json');receipt=json.loads(receipt_raw)
    marker=inputs.json(admission/'complete-private.json');terminal=inputs.json(admission/'worker-terminal-private.json')
    admitted=inputs.json(admission/'attempt-private.json')
    if (receipt['status']!='PASS' or marker['status']!='complete' or marker['admission_sha256']!=sha(receipt_raw) or
            terminal['status']!='complete' or terminal['exit_code'] or admitted['worker_exit_code'] or admitted['worker_status']!='complete' or
            terminal['initial_admission_sha256']!=sha(receipt_raw) or receipt['worker_arm']!=arm or
            Path(receipt['worker_output']).resolve()!=shard or receipt['admission_only'] or
            receipt['production_sources']!=inventory or receipt['producer_research_sources']!=sources or
            binding['production_sources']!=inventory or binding['research_sources']!=sources or
            binding['source_commit']!=SOURCE_COMMIT or binding['runtime']!=manifest['runtime'] or
            binding['native_bridge']!=manifest['native_bridge'] or receipt['runtime']!=binding['runtime'] or
            receipt['native_bridge']!=binding['native_bridge'] or
            Path(binding['baselines_path']).resolve()!=manifest_path or
            Path(receipt['preflight_admission']['prepared_manifest_path']).resolve()!=manifest_path or
            receipt['preflight_admission']['prepared_manifest_sha256']!=sha(inputs.read(binding['baselines_path']))):
        raise ValueError('Terminal worker/admission/source/native/runtime closure differs')
    for name,digest in receipt['admission_sources'].items():inputs.read(HERE.parent/name,digest)
    for value in (binding,receipt):
        for path,digest in value['input_files_sha256'].items():inputs.read(path,digest)
    if (summary['status']!='PASS' or summary['arm']!=arm or summary['arm_records']!=6 or
            summary['corpus_helper_calls']!=10 or summary['synthetic_helper_calls']!=3 or summary['actual_cap_views']!=18 or
            attempt['status']!='complete' or attempt['forbidden_fit_or_build_attempts'] or
            len(attempt['helper_calls'])!=10 or len(attempt['synthetic_calls'])!=3 or
            any(e['status']!='complete' for e in attempt['helper_calls']+attempt['synthetic_calls'])):
        raise ValueError('Fixed terminal six/ten/three/eighteen scope differs')
    jobs=[j for j in manifest['jobs'] if j['arm']==arm];bases={b['id']:b for b in manifest['baselines']}
    if [r['id'] for r in records]!=[j['id'] for j in jobs] or binding['assigned_jobs']!=[j['id'] for j in jobs]:
        raise ValueError('The exact assigned real arm records differ')
    measured={};events={}
    for record,job in zip(records,jobs):
        if any(record[name]!=value for name,value in job.items()):raise ValueError('A fixed job setting differs')
        base=bases[record['baseline_id']];folder=shard/'records'/('job-%02d'%record['id'])
        if record!=inputs.json(folder/'result-private.json'):raise ValueError('Per-record terminal receipt differs')
        baseline=tuple(inputs.stream(m) for m in base['segments']);anchor=record['whole_rows'][0]
        values_equal(anchor,base['stored_expected_whole_value'])
        saved_anchor=inputs.json(folder/'baseline-anchor-private.json');values_equal(saved_anchor['value'],anchor)
        local=[]
        for detail in record['locals']:
            matches=[e for e in attempt['helper_calls'] if e['baseline_id']==base['id'] and e['reset']==detail['index']]
            if len(matches)!=1 or matches[0]['causal_positions']!=job['causal_positions']:raise ValueError('Local attempt identity differs')
            local.append(audit_local(detail,matches[0],base,C,inputs,folder/('reset-%02d'%detail['index'])))
        choices=distinct_whole(whole_roles(baseline,local))
        if len(choices)!=len(record['whole_rows']) or len(choices)!=len(record['whole_chains']):raise ValueError('Whole role count differs')
        events[json.dumps(dict(job_id=record['id'],role='baseline-before-helper'),sort_keys=True)]=(base,baseline,anchor)
        for choice,value,artifact in zip(choices,record['whole_rows'],record['whole_chains']):
            parts=tuple(inputs.stream(meta) for meta in artifact['segments'])
            for meta,original in zip(artifact['segments'],base['segments']):
                if any(meta[k]!=original[k] for k in ('index','start','samples','profile')):raise ValueError('Whole reset metadata geometry differs')
            if (choice['blobs']!=parts or choice['id']!=value['id'] or artifact['id']!=value['id'] or
                    choice['labels']!=value['labels'] or choice['stream_bytes']!=value['stream_bytes'] or value['full_flash_bytes'] is not None):
                raise ValueError('Actual complete whole recipe/bytes differs')
            flags=C.chain._admission(value,anchor)
            if any(value[k]!=v for k,v in flags.items()) or value['automatic_quality_eligible']!=all(flags.values()):
                raise ValueError('Fresh-anchor whole admission flags differ')
            eager=inputs.json(folder/'whole'/('chain-%02d'%value['id'])/'admission-private.json')
            if eager!=dict(status='complete',whole_row=value,whole_chain=artifact):raise ValueError('Eager complete whole admission differs')
            events[json.dumps(dict(job_id=record['id'],chain_id=value['id']),sort_keys=True)]=(base,parts,value)
        progress=inputs.json(folder/'whole-progress-private.json')
        if progress['whole_rows']!=record['whole_rows'] or progress['whole_chains']!=record['whole_chains']:
            raise ValueError('Incrementally retained whole values differ')
        for decision in record['decisions']:
            chosen=C.chain.choose_budget(record['whole_rows'],job['whole_caps'][str(decision['percent'])])
            if any(decision[k]!=v for k,v in chosen.items()):raise ValueError('Actual cap decision differs')
    provenance=inputs.json(shard/'metric-cache-provenance-private.json');seen={};hits=fresh=0
    if len(provenance)!=len(events):raise ValueError('Whole measurement event catalogue differs')
    for event in provenance:
        base,parts,value=events.pop(json.dumps(event['event'],sort_keys=True))
        actual=(base['prepared_target']['pcm16_sha256'],not base['nonspeech'],binding['source_context'],parts)
        digest=sha(repr(actual).encode())
        if digest!=event['key_sha256']:raise ValueError('Exact target/context/ordered-byte metric cache key differs')
        if digest in seen:
            prior_event,prior_value=seen[digest];values_equal(value,prior_value)
            if event['reused_from']!=prior_event:raise ValueError('Metric cache provenance origin differs')
            hits+=1
        else:
            if event['reused_from'] is not None:raise ValueError('A whole metric has no fresh study origin')
            seen[digest]=(event['event'],value);fresh+=1
    if (hits!=summary['whole_counters']['whole_metric_cache_hits'] or fresh!=summary['whole_counters']['fresh_whole_metric_rows_completed'] or
            fresh!=summary['whole_counters']['fresh_whole_metric_rows_started']):raise ValueError('Whole metric audit counters differ')
    return records,summary,terminal


def project(args):
    begin=time.perf_counter(),time.process_time();inputs=Inputs();own=own_sources();sources=source_snapshot()
    manifest=load_manifest(args.baselines,inputs);inventory=bind_production(args.source_root,SOURCE_COMMIT)
    C=load_production(args.source_root);C.extras=importlib.import_module('refine_speech_extras')
    producer.check_extra_origin(C,args.source_root,inventory);check_origins(args.source_root)
    attempt=dict(forbidden_fit_or_build_attempts=0,forbidden_numerical_calls=0)
    def forbidden(*a,**k):
        attempt['forbidden_numerical_calls']+=1
        raise AssertionError('This saved-only projection forbids numerical work')
    records=[];summaries={};terminals={}
    with no_initial_fits(attempt,args.output),ExitStack() as stack:
        for obj,name in ((C.chain,'_measure'),(C.compact,'decode_model'),(C.BatchSession,'__init__'),
                (C.single,'refine'),(C.trajectory,'refine'),(C.extras,'refine_existing_extras')):
            stack.enter_context(patch.object(obj,name,forbidden))
        for arm in ('legacy','causal'):
            rows,summary,terminal=audit_worker(getattr(args,arm),getattr(args,arm+'_admission'),arm,manifest,args.baselines,C,inputs,inventory,sources)
            records.extend(rows);summaries[arm]=summary;terminals[arm]=terminal
        if validate_caps(records)!=36:raise ValueError('Exact 12 x 3 cap decisions differ')
        public=[];prior_public=[];unique={};all_classes=Counter();changed_classes=Counter();gate_counts=Counter();patterns=Counter()
        decision_counts=defaultdict(Counter);selected_inventory=[]
        for record in records:
            anchor=record['whole_rows'][0];base=next(b for b in manifest['baselines'] if b['id']==record['baseline_id'])
            prior=[r for r in manifest['prior_rows'] if r['baseline_id']==base['id']]
            prior_unique={}
            for row in sorted(prior,key=prior_order):
                if not all(C.chain._admission(row['value'],anchor).values()):continue
                parts=tuple(inputs.stream(meta) for meta in row['segments']);identity=key(parts)
                if identity in prior_unique:values_equal(row['value'],prior_unique[identity]['value']);continue
                prior_unique[identity]=dict(stream_bytes=row['stream_bytes'],score=row['value']['score'],value=row['value'],origin=origin(row),order=prior_order(row))
            prior_front=frontier(list(prior_unique.values()))
            if record['arm']=='legacy':prior_public.append(dict(source_ordinal=base['source_ordinal'],nonspeech=base['nonspeech'],profile=4,
                prior_saved_rows=len(prior),prior_distinct_admissible_tuples=len(prior_unique),
                prior_frontier=[dict(**p['origin'],stream_bytes=p['stream_bytes'],score=p['score']) for p in prior_front]))
            points=[]
            for row,artifact in zip(record['whole_rows'],record['whole_chains']):
                flags=C.chain._admission(row,anchor);reasons=failed(row,anchor,flags)
                comparison=classify(row,prior_front)
                public_point=dict(id=row['id'],labels=row['labels'],automatic_quality_eligible=row['automatic_quality_eligible'],
                    **numeric(row,anchor),failed_gates_and_subfloors=reasons,prior_frontier_comparison=comparison)
                points.append(public_point)
                identity=(base['id'],key(inputs.stream(meta) for meta in artifact['segments']))
                if identity[1] in prior_unique:values_equal(row,prior_unique[identity[1]]['value'])
                if identity in unique:values_equal(row,unique[identity]['row'])
                else:
                    unique[identity]=dict(row=row,anchor=anchor,point=public_point)
                    all_classes[comparison['status']]+=1
                    if row['id']!=0:
                        changed_classes[comparison['status']]+=1;gate_counts.update(reasons);patterns[' + '.join(reasons) or 'admitted']+=1
            decisions=[]
            for decision in record['decisions']:
                old=choose_secondary(prior,decision['cap'],C.chain._admission,anchor)
                old_value=None if old is None else dict(**old['value'],stream_bytes=old['stream_bytes'])
                new=None if decision['selected_id'] is None else record['whole_rows'][decision['selected_id']]
                expected=None if old is None else dict(**origin(old),stream_bytes=old['stream_bytes'],score=old['value']['score'],
                    provenance='Prior saved bridged measurement, not fresh and not seeded')
                if expected!=decision['secondary_prior_best']:raise ValueError('Saved secondary all-prior cap choice differs')
                label=outcome(new,old_value);decision_counts[str(decision['percent'])][label]+=1
                decisions.append(dict(percent=decision['percent'],cap=decision['cap'],selected_id=decision['selected_id'],raw_id=decision['raw_id'],
                    no_fit=decision['no_fit'],no_automatic_admission=decision['no_automatic_admission'],
                    chosen=None if new is None else numeric(new,anchor),prior=None if old_value is None else numeric(old_value,anchor),
                    versus_saved_prior=label))
                if new is not None and new['id']!=0:
                    selected_inventory.append(dict(job_id=record['id'],arm=record['arm'],percent=decision['percent'],baseline=base,
                        whole_row=new,segments=record['whole_chains'][new['id']]['segments'],full_flash_cap=None))
            public.append(dict(id=record['id'],source_ordinal=base['source_ordinal'],nonspeech=base['nonspeech'],profile=4,mode=base['mode'],
                arm=record['arm'],baseline_bytes=base['stream_bytes'],samples=base['samples'],points=points,decisions=decisions))
    review_raw=inputs.read(args.review_admission/'admission-private.json');review=json.loads(review_raw)
    review_marker=inputs.json(args.review_admission/'complete-private.json')
    if review['status']!='PASS' or not review['admission_only'] or review_marker['admission_sha256']!=sha(review_raw):
        raise ValueError('Shared read-only admission cost receipt is not closed')
    arm_receipt=inputs.json(args.legacy_admission/'admission-private.json')
    preflight=inputs.json(Path(arm_receipt['preflight_admission']['preflight_path'])/'summary.json')
    historical=manifest['historical_preflight']
    if attempt['forbidden_numerical_calls'] or attempt['forbidden_fit_or_build_attempts']:raise AssertionError('A forbidden operation was attempted')
    inputs.verify();check_origins(args.source_root);producer.check_extra_origin(C,args.source_root,inventory)
    if own!=own_sources() or sources!=source_snapshot() or inventory!=production_snapshot(args.source_root):raise ValueError('Postcheck source changed')
    aggregate=dict(status='PASS',production_source_commit=SOURCE_COMMIT,arm_records=12,corpus_helper_calls=20,actual_cap_views=36,
        historical_synthetic_calls=6,current_preflight_synthetic_calls=6,worker_warm_calls=6,total_paid_synthetic_calls=18,
        stored_whole_rows=sum(len(r['whole_rows']) for r in records),prior_saved_admissible_rows=len(manifest['prior_rows']),distinct_study_context_whole_tuples=len(unique),
        distinct_changed_context_whole_tuples=sum(item['row']['id']!=0 for item in unique.values()),
        all_distinct_point_frontier_classifications=dict(all_classes),changed_distinct_point_frontier_classifications=dict(changed_classes),
        changed_distinct_failed_gate_counts_overlapping=dict(gate_counts),changed_distinct_failed_patterns=dict(patterns),
        decisions_versus_complete_saved_prior={p:dict(v) for p,v in decision_counts.items()},
        costs={arm:costs([r for r in records if r['arm']==arm],summaries[arm],terminals[arm]) for arm in ('legacy','causal')},
        shared_costs=dict(historical_metadata=historical['superseded_metadata_preparation_cost'],current_metadata=manifest['preparation_cost'],
            historical_preflight=historical['preflight_cost'],current_preflight=preflight['total_cost'],admission_review=review['admission_cost']),
        postcheck_cost=dict(wall_seconds=time.perf_counter()-begin[0],cpu_seconds=time.process_time()-begin[1]),
        new_helper_calls=0,new_metric_evaluations=0,new_synthesis=0,new_native_builds=0,new_target_jobs=0,
        metric_provenance='Fresh producer whole values; prior values remain saved bridged evidence',
        wall_accounting='Individual process walls are work costs, not summed campaign elapsed time')
    save(args.output/'summary.json',aggregate);save(args.output/'results.json',public);save(args.output/'prior-frontiers.json',prior_public)
    save(args.output/'selected-chains-private.json',dict(status='PASS',views=selected_inventory))
    save(args.output/'binding-private.json',dict(status='PASS',projection_commit=subprocess.check_output(['git','-C',str(HERE),'rev-parse','HEAD'],text=True).strip(),
        projection_sources=own,producer_research_sources=sources,production_sources=inventory,source_root=str(args.source_root),
        baselines_path=str(args.baselines),input_files_sha256=inputs.pins,arguments={k:str(v) for k,v in vars(args).items()}))
    save(args.output/'complete-private.json',dict(status='complete',binding_sha256=sha((args.output/'binding-private.json').read_bytes())))
    return aggregate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','baselines','legacy','causal','legacy-admission','causal-admission','review-admission','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args()
    for name,value in vars(args).items():setattr(args,name,value.resolve())
    if args.output.exists() or not args.output.is_relative_to((TOP.parents[3]/'build').resolve()):parser.error('Use fresh private ignored output')
    args.output.mkdir(parents=True)
    try:print(json.dumps(project(args)),flush=True);return 0
    except Exception as exc:
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True);return 1


if __name__=='__main__':raise SystemExit(main())

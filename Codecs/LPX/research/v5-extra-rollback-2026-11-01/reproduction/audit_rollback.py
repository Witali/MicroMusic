"""Closed saved-state/frontier audit; all numerical entry points are forbidden."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from contextlib import ExitStack
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

HERE=Path(__file__).resolve().parent;TOP=HERE.parent
sys.path.insert(0,str(TOP))
from rollback_policy import accept_block,coverage_targets,retained_attempts
from rollback_runtime import (Inputs,SOURCE_COMMIT,VALUE_KEYS,bind_production,production_snapshot,load_manifest,
    source_snapshot,load_production,check_origins,no_initial_fits,save,sha,equal,verify_preflight,prior_rank)
from prepare_rollback import check_owner,current_runtime

FRONTIER=TOP.parent/'v5-existing-extra-pass-2026-11-01/reproduction/frontier/frontier_policy.py'
spec=importlib.util.spec_from_file_location('rollback_saved_frontier_policy',FRONTIER)
policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)


def own_sources():
    paths=[p for p in HERE.iterdir() if p.suffix in ('.py','.md')]+[FRONTIER]
    return {p.relative_to(TOP.parent).as_posix():sha(p.read_bytes()) for p in paths}


def same_value(left,right):
    for name in VALUE_KEYS:equal(left[name],right[name])


def measured_with_bytes(point):return {**point['value'],'stream_bytes':point['stream_bytes']}


def movement(value,reference):
    result=dict(byte_delta=value['stream_bytes']-reference['stream_bytes'],joint_delta=value['score']-reference['score'],
        pcm_period_coverage_delta=value['voice']['within_tolerance_frames']-reference['voice']['within_tolerance_frames'],
        pwm_period_coverage_delta=value['pwm_voice']['within_tolerance_frames']-reference['pwm_voice']['within_tolerance_frames'],
        clipped_samples_delta=value['clipped_samples']-reference['clipped_samples'])
    for domain,label in (('pcm16','pcm'),('pwm8','pwm')):
        for key,short in (('error_energy','sse'),('ser_db','ser_db'),('stoi','stoi')):
            new,old=value['metrics'][domain][key],reference['metrics'][domain][key]
            result[label+'_'+short+'_delta']=None if new is None or old is None else new-old
    return result


def closed_worker(path,inputs):
    marker=inputs.json(path/'complete-private.json')
    expected={'binding-private.json','summary.json','attempt-private.json','results-private.json',
        'synthetic-results-private.json','metric-cache-provenance-private.json'}
    if marker['status']!='complete' or set(marker['output_sha256'])!=expected:raise ValueError('Worker marker is incomplete')
    return {name:inputs.json(path/name,digest) for name,digest in marker['output_sha256'].items()}


def audit_record(record,base,C,inputs,folder,old_control=None):
    if record!=inputs.json(folder/'result-private.json') or record['status']!='complete':raise ValueError('Per-record closure differs')
    rows={r['id']:r for r in record['whole_rows']};chains={r['id']:r for r in record['whole_chains']}
    if len(rows)!=len(record['whole_rows']) or set(rows)!=set(chains) or not 1<=len(rows)<=5:raise ValueError('Bounded actual whole pool differs')
    parts={identifier:tuple(inputs.stream(meta) for meta in chains[identifier]['segments']) for identifier in chains}
    baseline=tuple(inputs.stream(meta) for meta in base['segments'])
    if parts[0]!=baseline:raise ValueError('The original full input is missing')
    anchor=rows[0]
    if record['phase']=='real':same_value(anchor,base['stored_expected_whole_value'])
    for identifier,row in rows.items():
        if row['stream_bytes']!=sum(map(len,parts[identifier])) or row['full_flash_bytes'] is not None:raise ValueError('Actual byte/Flash scope differs')
        flags=C.chain._admission(row,anchor)
        if any(row[name]!=v for name,v in flags.items()) or row['automatic_quality_eligible']!=all(flags.values()):raise ValueError('Whole gates differ')
        point=folder/'whole'/('candidate-%02d'%identifier)
        saved=inputs.json(point/'admission-private.json');serialized=inputs.json(point/'tuple-private.json')
        if saved!=dict(status='complete',whole_row=row,whole_chain=chains[identifier]):raise ValueError('Durable complete admission differs')
        if serialized!=dict(status='serialized-unverified',**chains[identifier]):raise ValueError('Immediate pre-metric tuple provenance differs')
        if len(parts[identifier])!=len(base['segments']):raise ValueError('A whole attempt dropped resets')
        for meta,original in zip(chains[identifier]['segments'],base['segments']):
            if any(meta[k]!=original[k] for k in ('index','start','samples','profile')):raise ValueError('Whole geometry changed')
    events=record['stage_events']
    if [e['slot'] for e in events]!=[1,2,3,4] or [d['percent'] for d in record['decisions']]!=[100,95,90]:
        raise ValueError('Exactly four stages and three actual caps are required')
    history=[(0,baseline)]+[(e['slot'],parts[e['candidate_id']]) for e in events]
    catalogue,expected=retained_attempts(history)
    if len(catalogue)!=len(rows):raise ValueError('The pool contains an undeclared whole recipe')
    for point in catalogue:
        if point['parts']!=parts[point['id']]:raise ValueError('Stage exact-byte deduplication differs')
    protected=0;previous=None
    for event,mapping in zip(events,expected[1:]):
        candidate=rows[event['candidate_id']];flags=C.chain._admission(candidate,anchor)
        decision=accept_block(candidate,flags,rows[protected])
        if (event['status']!='complete' or event['candidate_id']!=mapping['candidate_id'] or event['new_tuple']!=mapping['new_tuple'] or
                event['protected_before_id']!=protected or event['original_anchor_gates']!=flags or
                any(event[k]!=(list(v) if isinstance(v,tuple) else v) for k,v in decision.items())):
            raise ValueError('Prospective original-anchor/exact-protected decision differs')
        before,proposed,after=(event[k] for k in ('progress_before','progress_proposed','progress_after'))
        if previous is not None and before!=previous:raise ValueError('Prospective progress did not start from the prior completed stage')
        if len(proposed)!=len(base['segments']) or len(after)!=len(proposed):raise ValueError('Stage reset coverage differs')
        for index,(old,new,done) in enumerate(zip(before,proposed,after)):
            plan=base['reset_plans'][index];goal=coverage_targets(plan['initial_eligible'])[event['slot']-1]
            if (new['covered']!=goal or new['visited']!=plan['eligible_group_indices'][:goal] or new['trials']>plan['trial_limit'] or
                    new['trials']<old['trials'] or new['cursor']<old['cursor'] or new['cumulative_changed']<old['cumulative_changed']):
                raise ValueError('Common coverage/trial/no-revisit bound differs')
            rejecting=record['arm']=='rollback' and not decision['accepted']
            if rejecting:
                for name in ('covered','trials','cursor','visited','cumulative_changed'):
                    if done[name]!=new[name]:raise ValueError('Rollback refunded paid progress')
                for name in ('active','committed_changed_groups'):
                    if done[name]!=old[name]:raise ValueError('Rollback did not restore protected fields/active count')
            elif done!=new:raise ValueError('Uninterrupted working state was changed by admission bookkeeping')
        action='rollback' if record['arm']=='rollback' and not decision['accepted'] else 'continue'
        if event['action']!=action:raise ValueError('Recorded rollback action differs')
        if action=='continue' and decision['accepted']:protected=event['candidate_id']
        if event['protected_after_id']!=protected:raise ValueError('Protected incumbent transition differs')
        if old_control is not None:
            old=[v for v in old_control['slots'] if v['slot']==event['slot']]
            if len(old)!=1 or parts[event['candidate_id']]!=tuple(inputs.stream(m) for m in old[0]['segments']) or event['control_slot_bytes_exact'] is not True:
                raise ValueError('Fresh continue tuple differs from explicit old causal checkpoint mapping')
        elif event['control_slot_bytes_exact'] is not None:raise ValueError('Another arm was incorrectly labelled as old control')
        previous=after
    if protected!=record['protected_final_id']:raise ValueError('Final protected point differs')
    for index,state in enumerate(record['instances']):
        plan=base['reset_plans'][index]
        if state['status']!='complete' or state['progress']!=previous[index] or state['progress']['covered']!=plan['initial_eligible'] or state['progress']['visited']!=plan['eligible_group_indices']:
            raise ValueError('Actual complete initial-eligibility instance differs')
        count=state['work_counts'];expected_rollbacks=sum(e['action']=='rollback' for e in events)
        if count['rollback_calls']!=expected_rollbacks or count['rollback_attempts']!=expected_rollbacks or count['snapshot_calls']!=4:
            raise ValueError('Snapshot/rollback work count differs')
        samples=sum(e['progress_proposed'][index]['cursor']-e['progress_before'][index]['cursor'] for e in events if e['action']=='rollback')
        if count['rollback_synthesized_samples']!=samples or count['prefix_synthesized_samples']<samples:
            raise ValueError('Overlapping rollback-prefix replay counters differ')
    for decision in record['decisions']:
        actual=C.chain.choose_budget(list(rows.values()),record['whole_caps'][str(decision['percent'])])
        if any(decision[k]!=v for k,v in actual.items()):raise ValueError('Final complete fixed-pool cap decision differs')
    return parts


def work(records,summary):
    states=[s for r in records for s in r['instances']];api=defaultdict(float)
    for record in records:
        for name,value in record['api_call_costs'].items():api[name]+=value['cpu_seconds']
    return dict(visited_groups=sum(s['progress']['covered'] for s in states),trials=sum(s['progress']['trials'] for s in states),
        cumulative_attempted_changed_groups=sum(s['progress']['cumulative_changed'] for s in states),
        final_committed_changed_groups=sum(s['progress']['committed_changed_groups'] for s in states),
        rollback_calls=sum(s['work_counts']['rollback_calls'] for s in states),
        rollback_replayed_samples_subset=sum(s['work_counts']['rollback_synthesized_samples'] for s in states),
        prefix_synthesized_samples_including_rollback=sum(s['work_counts']['prefix_synthesized_samples'] for s in states),
        api_cpu_seconds=dict(api),record_workflow_cpu=sum(r['record_workflow_cost']['cpu_seconds'] for r in records),
        worker_main_cost=summary['total_worker_main_cost'],source_preparation_cost=summary['source_preparation_cost'],
        warm_cost=summary['preflight_or_warm_cost'],whole_counters=summary['whole_counters'])


def project(args):
    begin=time.perf_counter(),time.process_time();inputs=Inputs();sources=source_snapshot();own=own_sources()
    manifest=load_manifest(args.baselines,inputs);inventory=bind_production(args.source_root,SOURCE_COMMIT)
    C=load_production(args.source_root);C.extras=importlib.import_module('refine_speech_extras');check_owner(C,args.source_root,inventory)
    if current_runtime()!=manifest['runtime']:raise ValueError('Postcheck recorded runtime changed')
    attempt=dict(forbidden_fit_or_build_attempts=0,forbidden_numerical_calls=0)
    def forbidden(*a,**k):
        attempt['forbidden_numerical_calls']+=1;raise AssertionError('Numerical work is forbidden in this saved-only audit')
    records=[];summaries={};parts_by_record={};bases={b['id']:b for b in manifest['baselines']}
    with no_initial_fits(attempt,args.output),ExitStack() as stack:
        for obj,name in ((C.chain,'_measure'),(C.compact,'decode_model'),(C.BatchSession,'__init__'),
                (C.extras,'ExistingExtraPass'),(C.extras,'refit_extra_group'),(C.extras,'refine_existing_extras')):
            stack.enter_context(patch.object(obj,name,forbidden))
        for arm in ('continue','rollback'):
            path=getattr(args,arm);saved=closed_worker(path,inputs);binding=saved['binding-private.json'];summary=saved['summary.json'];journal=saved['attempt-private.json']
            if (summary['status']!='PASS' or summary['mode']!=arm or summary['real_arm_records']!=2 or summary['real_pass_instances']!=6 or
                    summary['real_stage_events']!=8 or summary['real_cap_views']!=6 or summary['synthetic_arm_records']!=3 or
                    summary['synthetic_pass_instances']!=4 or journal['status']!='complete' or journal['forbidden_fit_or_build_attempts'] or journal['forbidden_wrapper_calls'] or
                    binding['source_commit']!=SOURCE_COMMIT or binding['production_sources']!=inventory or binding['research_sources']!=sources or
                    binding['runtime']!=manifest['runtime'] or binding['native_bridge']!=manifest['native_bridge'] or Path(binding['baselines_path']).resolve()!=args.baselines):
                raise ValueError('Terminal exact source/runtime/native/real scope differs')
            proof=verify_preflight(args.preflight,args.baselines,inputs,binding)
            if proof!=binding['preflight_admission']:raise ValueError('Strict entry preflight admission differs')
            for name,digest in binding['input_files_sha256'].items():inputs.read(name,digest)
            rows=saved['results-private.json'];jobs=[j for j in manifest['jobs'] if j['arm']==arm]
            if [r['id'] for r in rows]!=[j['id'] for j in jobs] or binding['assigned_jobs']!=[j['id'] for j in jobs]:raise ValueError('Assigned jobs differ')
            for record,job in zip(rows,jobs):
                if any(record[k]!=v for k,v in job.items()):raise ValueError('Fixed job setting differs')
                base=bases[record['baseline_id']];old=manifest['old_causal_controls'][str(base['id'])] if arm=='continue' else None
                parts_by_record[record['id']]=audit_record(record,base,C,inputs,path/'real'/('record-'+str(record['id'])),old)
            if len(journal['real_instances'])!=6 or len(journal['synthetic_instances'])!=4 or any(s['status']!='complete' for s in journal['real_instances']+journal['synthetic_instances']):
                raise ValueError('Actual pass-instance construction/closure differs')
            real_states=[s for r in rows for s in r['instances']]
            if real_states!=journal['real_instances']:raise ValueError('Actual instance journal and per-record proof differ')
            # Reconstruct exact cache provenance for real and warm points alike.
            events={}
            for phase,items in (('real',rows),('synthetic',saved['synthetic-results-private.json'])):
                for record in items:
                    for row,chain in zip(record['whole_rows'],record['whole_chains']):
                        point_parts=tuple(inputs.stream(m) for m in chain['segments'])
                        if phase=='real':target_digest=bases[record['baseline_id']]['prepared_target']['pcm16_sha256']
                        else:
                            recipe=record['id'].split('synthetic-',1)[1].rsplit('-'+arm,1)[0]
                            target_digest=sha(inputs.read(path/'synthetic-inputs'/recipe/'reference.pcm16'))
                        event=dict(record_id=record['id'],phase=phase,arm=arm,candidate_id=row['id'],first_slot=chain['first_slot'])
                        digest=sha(repr((target_digest,True,binding['source_context'],point_parts)).encode())
                        events[json.dumps(event,sort_keys=True)]=(digest,row)
            provenance=saved['metric-cache-provenance-private.json'];seen={};fresh=hits=0
            if len(events)!=len(provenance):raise ValueError('Whole evaluation event count differs')
            for p in provenance:
                digest,value=events.pop(json.dumps(p['event'],sort_keys=True))
                if digest!=p['key_sha256']:raise ValueError('Exact ordered-byte/target/context cache key differs')
                if digest in seen:
                    origin,old=seen[digest];same_value(value,old)
                    if p['reused_from']!=origin:raise ValueError('Whole cache reuse origin differs')
                    hits+=1
                else:
                    if p['reused_from'] is not None:raise ValueError('Fresh current-study origin is missing')
                    seen[digest]=(p['event'],value);fresh+=1
            if fresh!=summary['whole_counters']['fresh_whole_metric_rows_completed'] or hits!=summary['whole_counters'].get('whole_metric_cache_hits',0):
                raise ValueError('Whole fresh/cache counters differ')
            summaries[arm]=summary;records.extend(rows)
        if len(records)!=4 or sorted(r['id'] for r in records)!=[0,1,2,3] or sum(len(r['decisions']) for r in records)!=12:raise ValueError('Final four/twelve record-cap scope differs')
        public=[];frontiers=[];useful=[];counts=Counter();reason_counts=Counter();selected_counts=defaultdict(Counter)
        for record in records:
            base=bases[record['baseline_id']];anchor=record['whole_rows'][0];union={}
            prior=[p for p in manifest['prior_rows'] if p['baseline_id']==base['id']]
            for old in sorted(prior,key=prior_rank):
                if not all(C.chain._admission(old['value'],anchor).values()):continue
                key=tuple(inputs.stream(m) for m in old['segments'])
                if key in union:same_value(union[key]['value'],old['value']);continue
                origin={k:old[k] for k in ('study','arm','job_id','candidate_id')}
                union[key]=dict(stream_bytes=old['stream_bytes'],score=old['value']['score'],value=old['value'],origin=origin,order=len(union))
            control=next(r for r in records if r['arm']=='continue' and r['baseline_id']==base['id'])
            for row in control['whole_rows']:
                if not row['automatic_quality_eligible']:continue
                key=parts_by_record[control['id']][row['id']]
                if key in union:same_value(union[key]['value'],row);continue
                union[key]=dict(stream_bytes=row['stream_bytes'],score=row['score'],value=row,
                    origin=dict(study='fresh-continue',arm='continue',job_id=control['id'],candidate_id=row['id']),order=len(union))
            comparison=list(union.values());boundary=policy.frontier(comparison);points=[]
            if record['arm']=='rollback':frontiers.append(dict(source_ordinal=base['source_ordinal'],profile=4,
                saved_rows=len(prior),distinct_comparison_tuples=len(union),frontier=[dict(**p['origin'],stream_bytes=p['stream_bytes'],score=p['score']) for p in boundary]))
            for row in record['whole_rows']:
                key=parts_by_record[record['id']][row['id']]
                if key in union:same_value(row,union[key]['value'])
                flags=C.chain._admission(row,anchor);comparison_result=policy.classify(row,boundary)
                reasons=policy.failed(row,anchor,flags)
                fitting=[p for p in comparison if p['stream_bytes']<=row['stream_bytes']]
                best=None if not fitting else min(fitting,key=lambda p:(p['score'],p['stream_bytes'],p['order']))
                point=dict(id=row['id'],labels=row['labels'],automatic_quality_eligible=row['automatic_quality_eligible'],**policy.numeric(row,anchor),
                    failed_gates_and_subfloors=reasons,versus_input=movement(row,anchor),versus_comparison_best=None if best is None else movement(row,measured_with_bytes(best)),
                    comparison_best=None if best is None else best['origin'],frontier=comparison_result)
                points.append(point)
                if record['arm']=='rollback' and row['id']!=0:
                    counts[comparison_result['status']]+=1;reason_counts.update(reasons)
                    if comparison_result['status']=='extends-prior-frontier':
                        enriched=lambda metas:[{**m,'flags':inputs.stream(m)[5]} for m in metas]
                        useful.append(dict(id='useful-%03d'%(len(useful)+1),record_id=record['id'],candidate_id=row['id'],
                            context=base,segments=enriched(record['whole_chains'][row['id']]['segments']),baseline_segments=enriched(base['segments']),whole_row=row,
                            comparison_best=None if best is None else best['origin'],selected_caps=[d['percent'] for d in record['decisions'] if d['selected_id']==row['id']],
                            full_flash_cap=None,provenance='Conditional fresh numerical frontier point; no target image/adoption yet'))
            decisions=[]
            for decision in record['decisions']:
                new=None if decision['selected_id'] is None else record['whole_rows'][decision['selected_id']]
                fitting=[p for p in comparison if p['stream_bytes']<=decision['cap']]
                best=None if not fitting else min(fitting,key=lambda p:(p['score'],p['stream_bytes'],p['order']))
                prior_value=None if best is None else measured_with_bytes(best)
                label=policy.outcome(new,prior_value)
                selected_counts[str(decision['percent'])][record['arm']+':'+label]+=1
                decisions.append(dict(**decision,chosen=None if new is None else policy.numeric(new,anchor),
                    comparison_best=None if best is None else dict(**best['origin'],stream_bytes=best['stream_bytes'],score=best['score']),outcome=label))
            public.append(dict(id=record['id'],source_ordinal=base['source_ordinal'],profile=4,arm=record['arm'],samples=base['samples'],
                baseline_bytes=base['stream_bytes'],protected_final_id=record['protected_final_id'],
                stages=[{k:e[k] for k in ('slot','candidate_id','new_tuple','original_anchor_gates','protected_before_id','protected_after_id',
                    'accepted','original_anchor_gates_passed','protected_pair_not_worse','candidate_pair','protected_pair','action','control_slot_bytes_exact')} for e in record['stage_events']],
                whole_points=points,decisions=decisions))
    preflight=closed_worker(args.preflight,inputs)['summary.json']
    if attempt['forbidden_fit_or_build_attempts'] or attempt['forbidden_numerical_calls']:raise AssertionError('A numerical operation was attempted')
    inputs.verify();check_origins(args.source_root);check_owner(C,args.source_root,inventory)
    if own!=own_sources() or sources!=source_snapshot() or inventory!=production_snapshot(args.source_root):raise ValueError('Frozen postcheck/source changed')
    summary=dict(status='PASS',source_commit=SOURCE_COMMIT,real_arm_records=4,real_pass_instances=12,real_stage_events=16,real_cap_views=12,
        synthetic_arm_records=12,synthetic_pass_instances=16,synthetic_stage_events=48,
        actual_real_whole_points=sum(len(r['whole_rows']) for r in records),rollback_changed_point_frontier=dict(counts),
        rollback_failed_reasons_overlapping=dict(reason_counts),decisions_versus_prior_plus_fresh_control={p:dict(v) for p,v in selected_counts.items()},
        useful_frontier_tuples=len(useful),costs={arm:work([r for r in records if r['arm']==arm],summaries[arm]) for arm in ('continue','rollback')},
        metadata_preparation_cost=manifest['preparation_cost'],synthetic_preflight_cost=preflight['total_worker_main_cost'],
        postcheck_cost=dict(wall_seconds=time.perf_counter()-begin[0],cpu_seconds=time.process_time()-begin[1]),
        new_pass_instances=0,new_model_decodes=0,new_metrics=0,new_synthesis=0,new_native_builds=0,new_target_jobs=0)
    save(args.output/'summary.json',summary);save(args.output/'rows.json',public);save(args.output/'comparison-frontiers.json',frontiers)
    save(args.output/'useful-tuples-private.json',dict(schema='lpx-extra-rollback-useful-tuples-private-v1',status='PASS',tuples=useful,
        source_commit=SOURCE_COMMIT,source_root=str(args.source_root),baselines_path=str(args.baselines),
        original_baselines_path=manifest['original_binding_path'],original_baselines_sha256=inputs.pins[str(Path(manifest['original_binding_path']).resolve())],
        producer_paths={arm:str(getattr(args,arm)) for arm in ('continue','rollback')},native_bridge=manifest['native_bridge'],
        decoded_outputs=dict(persisted=False,expected_pcm16_path=None,expected_pwm_path=None,
            provenance='Producer freshly verified state-owner/model/common/v5 PCM/PWM; no decoded output files persisted. New target preparation must render finite references under separate authorization.')))
    save(args.output/'binding-private.json',dict(status='PASS',projection_commit=subprocess.check_output(['git','-C',str(HERE),'rev-parse','HEAD'],text=True).strip(),
        projection_sources=own,producer_research_sources=sources,production_sources=inventory,source_root=str(args.source_root),
        baselines_path=str(args.baselines),input_files_sha256=inputs.pins,arguments={k:str(v) for k,v in vars(args).items()}))
    save(args.output/'complete-private.json',dict(status='complete',binding_sha256=sha((args.output/'binding-private.json').read_bytes())))
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','baselines','preflight','continue','rollback','output'):parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args()
    for name,value in vars(args).items():setattr(args,name,value.resolve())
    if args.output.exists() or not args.output.is_relative_to((TOP.parents[3]/'build').resolve()):parser.error('Use fresh private ignored output')
    args.output.mkdir(parents=True)
    try:print(json.dumps(project(args)),flush=True);return 0
    except Exception as exc:
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True);return 1


if __name__=='__main__':raise SystemExit(main())

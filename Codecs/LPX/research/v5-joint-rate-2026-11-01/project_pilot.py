"""Audit saved pilot decisions and export anonymous results without decoding."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import traceback

from pilot_policy import (ARMS,settings,validate_scope,local_frontier,whole_views,distinct_whole,
    frontier_summary,shared as policy_shared)
from pilot_runtime import (HERE,Inputs,VALUE_KEYS,sha,save,load_manifest,load_production,
    check_origins,equal,source_snapshot)
from run_pilot import validate_report

COMPARISONS=(('generation','T-full-0','G-full-0'),('price-.1','G-full-0','G-full-.1'),
    ('price-1','G-full-0','G-full-1'),('practical-0','T-local-0','G-full-0'),
    ('practical-.1','T-local-0','G-full-.1'),('practical-1','T-local-0','G-full-1'),
    ('screening-ablation','T-local-0','T-full-0'))


def outcome(left,right):
    if left is None or right is None:
        return 'neither-admitted' if left is None and right is None else 'left-only' if right is None else 'right-only'
    if abs(left['score']-right['score'])<=1e-12:
        return 'exact-rank-tie' if left['stream_bytes']==right['stream_bytes'] else 'left-smaller-score-tie' if left['stream_bytes']<right['stream_bytes'] else 'right-smaller-score-tie'
    return 'left-lower-score' if left['score']<right['score'] else 'right-lower-score'


def rejected(row,anchor):
    flags={name:row[name] for name in ('old_pcm_pwm_floors_passed','clipped_sample_floor_passed',
        'pcm_period_coverage_floor_passed','pwm_period_coverage_floor_passed','joint_objective_nonregression')}
    result=[name for name,passed in flags.items() if not passed]
    for domain in ('pcm16','pwm8'):
        new,old=row['metrics'][domain],anchor['metrics'][domain]
        if new['error_energy']>old['error_energy']:result.append(domain+'_sse')
        if old['stoi'] is not None and (new['stoi'] is None or new['stoi']<old['stoi']-1e-12):
            result.append(domain+'_stoi')
    return result


def costs(row):
    locals=row['locals']
    return dict(helper_cpu=row['total_helper_cpu'],helper_wall_sum=row['total_helper_wall'],
        source_setup_search_cpu=sum(r['cpu_budget']['search_cpu_seconds'] for r in locals),
        source_finalization_cpu=sum(r['cpu_budget']['finalization_cpu_seconds'] for r in locals),
        observed_quota_exhaustions=sum(r['cpu_budget']['exhausted'] for r in locals),
        search_overshoot_cpu=sum(max(0.,r['cpu_budget']['search_cpu_seconds']-2.) for r in locals),
        helper_total_overshoot_cpu=sum(r['cpu_budget']['cpu_overshoot_seconds'] for r in locals),
        raw_pool_model_audit_cpu=sum(r['independent_raw_pool_model_sse_audit_cost']['cpu_seconds'] for r in locals),
        bounded_frontier_pruning_cpu=sum(r['bounded_endpoint_pruning_cost']['cpu_seconds'] for r in locals),
        capture_persistence_cpu=sum(r['persistence_cost']['cpu_seconds'] for r in locals),
        postsearch_whole_admission_and_persistence_cpu=row['whole_audit_cost']['cpu_seconds'],
        arm_workflow_cpu=row['total_arm_cost']['cpu_seconds'])


def selected(row,decision):
    return None if decision['selected_id'] is None else row['whole_rows'][decision['selected_id']]


def public_row(row):
    base=row['whole_rows'][0]
    output={k:row[k] for k in ('id','baseline_id','source_ordinal','nonspeech','profile','mode','arm',
        'alpha','screening','new_generation','reset_indices','local_byte_cap','whole_caps',
        'baseline_samples','baseline_bytes','fresh_baseline_sse','rate_lambda','zero_sse_price_degenerate',
        'minimum_preserved_quality_id','minimum_preserved_quality_bytes','bounded_preserved_quality_frontier_ids')}
    output['costs']=costs(row);output['decisions']=[]
    for decision in row['decisions']:
        chosen=selected(row,decision)
        raw=None if decision['raw_id'] is None else row['whole_rows'][decision['raw_id']]
        output['decisions'].append(dict(**decision,changed=chosen is not None and chosen['id']!=0,
            bytes=None if chosen is None else chosen['stream_bytes'],
            score=None if chosen is None else chosen['score'],
            pcm_sse=None if chosen is None else chosen['metrics']['pcm16']['error_energy'],
            pwm_sse=None if chosen is None else chosen['metrics']['pwm8']['error_energy'],
            raw_bytes=None if raw is None else raw['stream_bytes'],
            raw_failed_gates=[] if raw is None else rejected(raw,base)))
    output['whole_rows']=[dict(id=r['id'],labels=r['labels'],stream_bytes=r['stream_bytes'],score=r['score'],
        automatic_quality_eligible=r['automatic_quality_eligible'],metrics=r['metrics'],
        clipped_samples=r['clipped_samples'],pcm_period_coverage=r['voice']['within_tolerance_frames'],
        pwm_period_coverage=r['pwm_voice']['within_tolerance_frames'],failed_gates=rejected(r,base)) for r in row['whole_rows']]
    return output


def audit_local(row,local,folder,base,C,inputs,all_parts):
    reset=folder/('reset-%03d'%local['index'])
    returned=inputs.json(reset/'helper-return-private.json')
    endpoint=inputs.json(reset/'endpoint-private.json')
    event=inputs.json(reset/'attempt-private.json')
    if endpoint!=local or returned['cost']!=local['helper_cost'] or event['status']!='complete':
        raise ValueError('A completed local receipt differs')
    requested=settings(row,row['fresh_baseline_sse'],base['stream_bytes'])
    validate_report(returned['report'],requested,local['captured_streams'],2.)
    known={sha(blob):blob for blob in all_parts}
    captures=[]
    for order,meta in enumerate(local['captured_streams']):
        blob=inputs.stream(meta)
        if meta['callback_order']!=order:raise ValueError('Callback order differs')
        known[sha(blob)]=blob;captures.append(blob)
    if len(set(captures))!=len(captures):raise ValueError('A callback stream was duplicated')
    pool=[]
    for position,meta in enumerate(local['pool']):
        blob=known.get(meta['stream_sha256'])
        if blob is None or meta['id']!=position or len(blob)!=meta['file_bytes']:
            raise ValueError('An actual pool endpoint was lost')
        if C.compact.unpack(blob)[:2]!=(base['segments'][local['index']]['samples'],base['profile']):
            raise ValueError('Saved endpoint reset geometry differs')
        pool.append(dict(id=position,blob=blob,sse=meta['sse']))
    points=local_frontier([p for p in pool if p['sse'] is not None],row['local_byte_cap'])
    if [p['id'] for p in points]!=local['frontier_ids']:
        raise ValueError('Saved bounded local frontier differs from the fixed policy')
    by_blob={p['blob']:p for p in pool}
    for meta,blob in zip(local['captured_streams'],captures):
        if meta['reported_sse']!=by_blob[blob]['sse']:
            raise ValueError('Saved callback SSE differs from the completed model audit')
    return dict(index=local['index'],selected=None if local['selected_id'] is None else pool[local['selected_id']]['blob'],
        raw=None if local['raw_id'] is None else pool[local['raw_id']]['blob'],frontier=points),returned['report']


def project(args):
    inputs=Inputs();manifest=load_manifest(args.baselines,inputs);bases=validate_scope(manifest)
    preflight=inputs.json(args.preflight/'summary.json')
    if preflight['status']!='PASS' or not preflight['preflight_only'] or preflight['helper_calls'] or preflight['synthetic_helper_calls']!=10:
        raise ValueError('The fixed synthetic preflight was not completed')
    rows=[];bindings=[];summaries=[];reports=[];inventories={};provenance_all=[]
    C=None
    for shard in args.shards:
        binding=inputs.json(shard/'binding-private.json');attempt=inputs.json(shard/'attempt-private.json')
        summary=inputs.json(shard/'summary.json');results=inputs.json(shard/'results-private.json')
        provenance=inputs.json(shard/'metric-cache-provenance-private.json')
        if (summary['status']!='PASS' or attempt['status']!='complete' or summary['preflight_only'] or
                summary['helper_calls']!=50 or summary['arm_records']!=30 or summary['cap_views']!=90 or
                summary['synthetic_helper_calls']!=5 or summary['new_initial_fits'] or summary['new_native_builds'] or
                attempt['forbidden_fit_or_build_attempts'] or any(e['status']!='complete' for e in attempt['helper_calls'])):
            raise ValueError('Each worker must close its exact finite shard without retry')
        for name,digest in binding['research_sources'].items():inputs.read(HERE.parent/name,digest)
        for name,digest in binding['production_sources'].items():inputs.read(Path(binding['source_root'])/name,digest)
        for path,digest in binding['input_files_sha256'].items():inputs.read(path,digest)
        if C is None:C=load_production(Path(binding['source_root']))
        check_origins(Path(binding['source_root']))
        if len(provenance)!=len(results)+sum(len(r['whole_rows']) for r in results):
            raise ValueError('A baseline or whole row lacks new-study cache provenance')
        seen={};fresh=hits=0
        for item in provenance:
            key=item['key_sha256']
            if item['reused_from'] is None:
                if key in seen:raise ValueError('A fresh metric key was duplicated')
                seen[key]=item['event'];fresh+=1
            else:
                if seen.get(key)!=item['reused_from']:raise ValueError('A cache origin was not a prior exact fresh row')
                hits+=1
        if (fresh!=summary['whole_counters']['fresh_whole_metric_rows_completed'] or
                hits!=summary['whole_counters']['whole_metric_cache_hits']):
            raise ValueError('Fresh/cache counters differ')
        by_event={(r['job_id'],r['reset']):r for r in attempt['helper_calls']}
        if len(by_event)!=50:raise ValueError('A helper call was repeated')
        metric_events={};metric_values={}
        for row in results:
            folder=shard/'arms'/('job-%03d'%row['id']);base=bases[row['baseline_id']]
            if row!=inputs.json(folder/'result-private.json') or row['profile']!=summary['profile']:
                raise ValueError('An individual arm or profile binding differs')
            expected=manifest['pilot_jobs'][row['id']]
            for key,value in expected.items():equal(row[key],value)
            blobs=[];all_parts=[]
            for chain,value in zip(row['whole_chains'],row['whole_rows']):
                parts=tuple(inputs.stream(meta) for meta in chain['segments'])
                if chain['id']!=value['id'] or sum(map(len,parts))!=value['stream_bytes']:
                    raise ValueError('Actual whole bytes differ')
                for i,meta in enumerate(chain['segments']):
                    if any(meta[k]!=base['segments'][i][k] for k in ('index','start','samples','profile')):
                        raise ValueError('The original full reset geometry changed')
                blobs.append(parts);all_parts.extend(parts)
            baseline=tuple(inputs.stream(meta) for meta in base['segments'])
            if blobs[0]!=baseline:raise ValueError('The strongest current baseline changed')
            def metric_event(parts,event,value):
                key=policy_shared.metric_key(base['prepared_target']['pcm16_sha256'],not base['nonspeech'],binding['source_context'],parts)
                digest=sha(repr(key).encode());metric_events[json.dumps(event,sort_keys=True)]=digest
                values={k:value[k] for k in VALUE_KEYS}
                if digest in metric_values and metric_values[digest]!=values:
                    raise ValueError('Exact cached whole bytes/context acquired different metric values')
                metric_values[digest]=values
            metric_event(baseline,dict(job_id=row['id'],baseline_id=base['id'],role='baseline-before-search'),row['whole_rows'][0])
            for i,parts in enumerate(blobs):
                metric_event(parts,dict(job_id=row['id'],baseline_id=base['id'],chain_id=i),row['whole_rows'][i])
            anchor=row['whole_rows'][0]
            for key in VALUE_KEYS:equal(anchor[key],base['stored_expected_whole_value'][key])
            if row['fresh_baseline_sse']!=anchor['metrics']['pcm16']['error_energy']:
                raise ValueError('The fresh whole-record price anchor differs')
            locals=[]
            for local in row['locals']:
                local_row,report=audit_local(row,local,folder,base,C,inputs,all_parts)
                locals.append(local_row);reports.append(report)
                if by_event[row['id'],local['index']]['cost']!=local['helper_cost']:
                    raise ValueError('Helper journal and caller CPU receipt differ')
            expected_whole=distinct_whole(whole_views(baseline,locals))
            if len(expected_whole)!=len(blobs):raise ValueError('The declared whole recipe count differs')
            for choice,value,parts in zip(expected_whole,row['whole_rows'],blobs):
                if choice['blobs']!=parts or choice['labels']!=value['labels'] or choice['id']!=value['id']:
                    raise ValueError('A saved whole chain is not its declared exact byte recipe')
                flags=C.chain._admission(value,anchor)
                if any(value[k]!=v for k,v in flags.items()) or value['automatic_quality_eligible']!=all(flags.values()):
                    raise ValueError('A whole quality gate differs from its current baseline')
            for key,value in frontier_summary(row['whole_rows']).items():equal(row[key],value)
            for decision in row['decisions']:
                reproduced=C.chain.choose_budget(row['whole_rows'],row['whole_caps'][str(decision['percent'])])
                for key,value in reproduced.items():equal(decision[key],value)
                if not decision['baseline_nonregression']:raise ValueError('A retained baseline regressed')
            roles=defaultdict(list)
            for decision in row['decisions']:
                if decision['selected_id'] is not None:roles[decision['selected_id']].append(dict(kind='cap',percent=decision['percent']))
            for identifier in row['bounded_preserved_quality_frontier_ids']:roles[identifier].append(dict(kind='eligible-frontier'))
            roles[row['minimum_preserved_quality_id']].append(dict(kind='minimum-preserved-quality'))
            for identifier,contexts in roles.items():
                if identifier==0:continue
                key=blobs[identifier];value=row['whole_rows'][identifier]
                item=inventories.setdefault(key,dict(profile=base['profile'],samples=base['samples'],
                    stream_bytes=value['stream_bytes'],segments=row['whole_chains'][identifier]['segments'],contexts=[]))
                for context in contexts:item['contexts'].append(dict(**context,job_id=row['id'],baseline_id=base['id'],
                    source_ordinal=base['source_ordinal'],nonspeech=base['nonspeech'],profile=base['profile'],mode=base['mode'],
                    arm=row['arm'],alpha=row['alpha'],chain_id=identifier,quality_eligible=True,full_flash_cap=None,
                    level=base['level'],reference=base['reference'],prepared_target=base['prepared_target'],
                    rollback=base['segments'],target_admission_links=base['target_admission_links']))
            rows.append(row)
        if len(metric_events)!=len(provenance):raise ValueError('A whole event is missing or duplicated')
        for event in provenance:
            if metric_events.get(json.dumps(event['event'],sort_keys=True))!=event['key_sha256']:
                raise ValueError('Cache provenance does not bind the exact ordered bytes, target and source context')
        bindings.append(binding);summaries.append(summary);provenance_all.extend(provenance)
    if ({s['profile'] for s in summaries}!={4,6} or len(rows)!=60 or len({r['id'] for r in rows})!=60 or len(reports)!=100 or
            bindings[0]['source_commit']!=bindings[1]['source_commit'] or bindings[0]['research_sources']!=bindings[1]['research_sources'] or
            bindings[0]['source_context']!=bindings[1]['source_context']):
        raise ValueError('The final 60/100/180 pilot or shared source context differs')
    public=sorted(map(public_row,rows),key=lambda r:r['id']);pairs=[];groups=[]
    by_context=defaultdict(dict)
    for row in rows:by_context[row['baseline_id']][row['arm']]=row
    for name,left_arm,right_arm in COMPARISONS:
        counts=Counter();matched_counts=Counter();matches=0
        for base_id,arms in by_context.items():
            left,right=arms[left_arm],arms[right_arm];a,b=left['total_helper_cpu'],right['total_helper_cpu']
            ratio=max(a,b)/min(a,b);matched=ratio<=1.25;matches+=matched
            views=[]
            for l,r in zip(left['decisions'],right['decisions']):
                result=outcome(selected(left,l),selected(right,r))
                views.append(dict(percent=l['percent'],outcome=result))
                if l['percent']==100:counts[result]+=1;matched_counts.update([result] if matched else [])
            pairs.append(dict(comparison=name,baseline_id=base_id,left=left_arm,right=right_arm,
                profile=left['profile'],nonspeech=left['nonspeech'],source_ordinal=left['source_ordinal'],
                helper_cpu_ratio=ratio,matched_helper_cpu=matched,left_helper_cpu=a,right_helper_cpu=b,decisions=views))
        groups.append(dict(comparison=name,left=left_arm,right=right_arm,contexts=12,matched_helper_contexts=matches,
            outcomes100=dict(counts),matched_outcomes100=dict(matched_counts)))
    arm_groups=[]
    for arm in ARMS:
        group=[r for r in rows if r['arm']==arm];caps={};small_rows=[];unique_small=set();failures=Counter()
        for percent in (100,95,90):
            choices=[r['decisions'][(100,95,90).index(percent)] for r in group]
            caps[str(percent)]=dict(admitted=sum(not d['no_automatic_admission'] for d in choices),
                no_fit=sum(d['no_fit'] for d in choices),raw_only=sum(not d['no_fit'] and d['no_automatic_admission'] for d in choices))
        for row in group:
            for value,chain in zip(row['whole_rows'],row['whole_chains']):
                if value['stream_bytes']<row['baseline_bytes']:
                    small_rows.append(value)
                    key=tuple((p['stream_sha256'],p['file_bytes']) for p in chain['segments'])
                    unique_small.add(key);failures.update(rejected(value,row['whole_rows'][0]))
        arm_groups.append(dict(arm=arm,contexts=12,cap_outcomes=caps,
            contexts_with_any_preserved_quality_byte_reduction=sum(r['minimum_preserved_quality_bytes']<r['baseline_bytes'] for r in group),
            changed_selected100=sum(r['decisions'][0]['selected_id']!=0 for r in group),
            smaller_whole_rows=len(small_rows),distinct_smaller_ordered_chains=len(unique_small),
            smaller_whole_row_failures=dict(failures),costs={k:sum(costs(r)[k] for r in group) for k in costs(group[0])}))
    work=Counter()
    for report in reports:
        for name in ('full_synthesis_evaluations','local_synthesis_evaluations','local_synthesized_samples',
                'serialization_calls','allocation_evaluations','repeat_spectrum_proposals','completed_rate_allocation_calls','rate_allocation_points'):
            work[name]+=report.get(name,0)
    inventory=[dict(id=i,**item) for i,item in enumerate(inventories.values())]
    aggregate=dict(status='PASS',production_source_commit=bindings[0]['source_commit'],baseline_contexts=104,
        pilot_contexts=12,arm_records=60,corpus_helper_calls=100,cap_views=180,nominal_corpus_cpu_seconds=200,
        synthetic_helper_calls=20,initial_fits=0,new_native_builds=0,new_metric_or_decode_calls_in_projector=0,
        preflight_cost=preflight['actual_cost'],baseline_preparation_cost=manifest['preparation_cost'],
        workers=[dict(profile=s['profile'],actual_cost=s['actual_cost'],synthetic_cost=s['synthetic_cost'],
            preparation_cost=s['preparation_cost'],whole_counters=s['whole_counters'],counters=s['counters']) for s in summaries],
        worker_cpu_total=sum(s['actual_cost']['cpu_seconds'] for s in summaries),
        worker_wall_is_not_campaign_elapsed=True,arm_helper_cpu_total=sum(r['total_helper_cpu'] for r in rows),
        arm_workflow_cpu_total=sum(r['total_arm_cost']['cpu_seconds'] for r in rows),work=dict(work),
        whole_fresh_rows=sum(s['whole_counters']['fresh_whole_metric_rows_completed'] for s in summaries),
        whole_cache_hits=sum(s['whole_counters']['whole_metric_cache_hits'] for s in summaries),
        fresh_anchor_measure_body_cpu=sum(p['evaluation_body_cost']['cpu_seconds'] for p in provenance_all if p['event'].get('role')=='baseline-before-search'),
        changed_eligible_inventory_chains=len(inventory),changed_eligible_inventory_contexts=sum(len(i['contexts']) for i in inventory),
        comparison_groups=groups,arm_groups=arm_groups)
    inputs.verify()
    for name,value in (('summary.json',aggregate),('rows.json',public),('comparisons.json',pairs),
            ('new-selected-chains-private.json',inventory)):
        save(args.output/name,value)
    save(args.output/'binding-private.json',dict(status='PASS',input_files_sha256=inputs.pins,
        projection_sources=source_snapshot(),production_source_commit=bindings[0]['source_commit'],
        source_root=bindings[0]['source_root'],baselines_path=str(args.baselines),
        shard_paths=list(map(str,args.shards)),preflight_path=str(args.preflight),
        zero_search_refit_metric_decode_native_build_calls=True))
    return aggregate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baselines',required=True,type=Path);parser.add_argument('--preflight',required=True,type=Path)
    parser.add_argument('--shards',required=True,nargs=2,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();args.shards=[p.resolve() for p in args.shards]
    for name in ('baselines','preflight','output'):setattr(args,name,getattr(args,name).resolve())
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):
        parser.error('Use fresh private ignored build output')
    args.output.mkdir(parents=True)
    try:
        result=project(args);print(json.dumps(result),flush=True);return 0
    except Exception as exc:
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True);return 1


if __name__=='__main__':raise SystemExit(main())

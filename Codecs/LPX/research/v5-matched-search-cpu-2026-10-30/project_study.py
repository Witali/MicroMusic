"""Reopen all exact study artifacts and publish anonymous paired cost/results."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path

from prepare_baselines import load_helper
from study_policy import pair_cpu
from study_runtime import HERE,save,sha


def costs(row):
    return dict(standalone_total_helper_cpu=row['total_helper_cpu'],
        cumulative_total_helper_cpu=row['cumulative_total_helper_cpu'],
        total_helper_wall=row['total_helper_wall'],prior2_helper_cpu=row['prior2_helper_cpu'],
        independent_raw_pool_model_sse_audit_cpu=sum(r['independent_raw_pool_model_sse_audit_cost']['cpu_seconds'] for r in row['locals']),
        bounded_frontier_pruning_cpu=sum(r['bounded_endpoint_pruning_cost']['cpu_seconds'] for r in row['locals']),
        capture_persistence_cpu=sum(r['persistence_cost']['cpu_seconds'] for r in row['locals']),
        required_whole_admission_cpu=row['whole_audit_cost']['cpu_seconds'],
        actual_arm_workflow_cpu=row['total_arm_cost']['cpu_seconds'],
        setup_plus_search_cpu=sum(r['cpu_budget']['search_cpu_seconds'] for r in row['locals']),
        helper_finalization_cpu=sum(r['cpu_budget']['finalization_cpu_seconds'] for r in row['locals']),
        search_overshoot_cpu=sum(max(0.,r['cpu_budget']['search_cpu_seconds']-r['cpu_budget']['limit_seconds']) for r in row['locals']),
        total_helper_overshoot_cpu=sum(r['cpu_budget']['cpu_overshoot_seconds'] for r in row['locals']),
        observed_quota_exhaustions=sum(r['cpu_budget']['exhausted'] for r in row['locals']),
        completed_without_observed_quota_exhaustion=sum(not r['cpu_budget']['exhausted'] for r in row['locals']))


def project(row):
    output = {name:row[name] for name in ('id','phase','source_ordinal','profile','mode','speech','baseline_id','arm',
        'cpu_seconds_per_reset','edited_segments','local_byte_cap','whole_byte_caps','baseline_samples','reset_segments','tier_label')}
    output['costs'] = costs(row)
    output['whole_audit_counters'] = row['whole_audit_counters']
    output['local_work'] = [dict(index=local['index'],sink_callbacks=local['sink_callbacks'],
        distinct_captured_and_fallback=local['distinct_captured_and_fallback'],frontier_count=local['frontier_count'],
        feasible_pool_rows=local['feasible_pool_rows'],oversize_pool_rows=local['oversize_pool_rows'],cpu_budget=local['cpu_budget']) for local in row['locals']]
    output['decisions'] = []
    for decision in row['decisions']:
        chosen = None if decision['selected_id'] is None else row['whole_rows'][decision['selected_id']]
        output['decisions'].append(dict(percent=decision['percent'],cap=decision['cap'],
            selected_id=decision['selected_id'],raw_id=decision['raw_id'],no_fit=decision['no_fit'],
            no_automatic_admission=decision['no_automatic_admission'],incumbent_nonregression=decision['incumbent_nonregression'],
            bytes=None if chosen is None else chosen['stream_bytes'],score=None if chosen is None else chosen['score'],
            pcm_sse=None if chosen is None else chosen['metrics']['pcm16']['error_energy'],
            pwm_sse=None if chosen is None else chosen['metrics']['pwm8']['error_energy'],
            pcm_stoi=None if chosen is None else chosen['metrics']['pcm16']['stoi'],
            pwm_stoi=None if chosen is None else chosen['metrics']['pwm8']['stoi'],
            within_tolerance_pcm=None if chosen is None else chosen['voice']['within_tolerance_frames'],
            within_tolerance_pwm=None if chosen is None else chosen['pwm_voice']['within_tolerance_frames']))
    return output


def outcome(left,right):
    if left['score'] is None or right['score'] is None:
        return 'neither-admitted' if left['score'] is None and right['score'] is None else 'single-only' if right['score'] is None else 'trajectory-only'
    if abs(left['score']-right['score'])<=1e-12:
        return 'equal-score' if left['bytes']==right['bytes'] else 'single-smaller-tied-score' if left['bytes']<right['bytes'] else 'trajectory-smaller-tied-score'
    return 'single-lower-score' if left['score']<right['score'] else 'trajectory-lower-score'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shards',nargs=2,required=True,type=Path)
    parser.add_argument('--preflight',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):
        parser.error('Use fresh private research build output')
    helper = load_helper()
    inputs = helper.Inputs()
    rows,summaries,bindings = [],[],[]
    selected_chains = {}
    for folder in map(Path.resolve,args.shards):
        binding = json.loads(inputs.read(folder/'binding-private.json'))
        attempt = json.loads(inputs.read(folder/'attempt-private.json'))
        summary = json.loads(inputs.read(folder/'summary.json'))
        results = json.loads(inputs.read(folder/'results-private.json'))
        provenance = json.loads(inputs.read(folder/'metric-cache-provenance-private.json'))
        if (attempt['status']!='complete' or summary['status']!='PASS' or summary['warmup_only']
                or attempt['forbidden_fit_or_build_attempts'] or summary['new_initial_fits']
                or len(results)!=summary['arm_records'] or any(e['status']!='complete' for e in attempt['helper_calls'])):
            raise ValueError('Each corpus worker must be complete without initial fits or retry')
        for name,digest in binding['research_sources'].items():
            if sha((HERE/name).read_bytes())!=digest:
                raise ValueError('Executing research source changed')
        for path,digest in binding['inputs_sha256'].items():
            inputs.read(path,digest)
        for name,digest in binding['production_sources'].items():
            inputs.read(Path(binding['source_root'])/name,digest)
        if len(provenance)!=sum(len(row['whole_rows']) for row in results):
            raise ValueError('Every whole view needs exact new-study cache provenance')
        for row in results:
            if row['source_ordinal']%2!=summary['shard']:
                raise ValueError('Source parity changed')
            stored = json.loads(inputs.read(folder/'arms'/('job-%03d'%row['id'])/'result-private.json'))
            if stored!=row:
                raise ValueError('An individual arm result differs')
            for local in row['locals']:
                reset = folder/'arms'/('job-%03d'%row['id'])/('reset-%03d'%local['index'])
                returned = json.loads(inputs.read(reset/'helper-return-private.json'))
                endpoint = json.loads(inputs.read(reset/'endpoint-private.json'))
                if returned['cost']!=local['helper_cost'] or endpoint!=local:
                    raise ValueError('Returned helper/candidate receipt differs')
                for meta in local['captured_streams']:
                    inputs.stream(meta)
            if len(row['whole_chains'])!=len(row['whole_rows']):
                raise ValueError('Whole stream receipts differ from measured rows')
            blobs=[]
            for chain,value in zip(row['whole_chains'],row['whole_rows']):
                parts=tuple(inputs.stream(meta) for meta in chain['segments'])
                if chain['id']!=value['id'] or sum(map(len,parts))!=value['stream_bytes']:
                    raise ValueError('Actual complete-chain cost differs')
                blobs.append(parts)
            for decision in row['decisions']:
                if not decision['incumbent_nonregression']:
                    raise ValueError('A required retained incumbent failed')
                identifier = decision['selected_id']
                if identifier is None:
                    continue
                chosen = row['whole_rows'][identifier]
                if not chosen['automatic_quality_eligible'] or chosen['stream_bytes']>decision['cap']:
                    raise ValueError('An inadmissible whole endpoint was selected')
                if blobs[identifier]!=blobs[0]:
                    item=selected_chains.setdefault(blobs[identifier],dict(profile=row['profile'],samples=row['baseline_samples'],
                        stream_bytes=chosen['stream_bytes'],segments=row['whole_chains'][identifier]['segments'],contexts=[]))
                    item['contexts'].append(dict(job_id=row['id'],baseline_id=row['baseline_id'],phase=row['phase'],
                        source_ordinal=row['source_ordinal'],profile=row['profile'],mode=row['mode'],arm=row['arm'],
                        tier_label=row['tier_label'],percent=decision['percent'],rollback=row['whole_chains'][0]['segments']))
            rows.append(row)
        summaries.append(summary)
        bindings.append(binding)
    if ({summary['shard'] for summary in summaries}!={0,1} or len(rows)!=248
            or len({row['id'] for row in rows})!=248 or sum(s['helper_calls'] for s in summaries)!=312
            or bindings[0]['source_commit']!=bindings[1]['source_commit']
            or bindings[0]['research_sources']!=bindings[1]['research_sources']):
        raise ValueError('The finite 248-arm/312-call study or source epoch changed')
    preflight=json.loads(inputs.read(args.preflight/'summary.json'))
    if preflight['status']!='PASS' or not preflight['warmup_only'] or preflight['helper_calls']:
        raise ValueError('The synthetic preflight must pass without corpus search')
    public = sorted(map(project,rows),key=lambda r:r['id'])
    paired = defaultdict(dict)
    for row in public:
        paired[(row['baseline_id'],row['cpu_seconds_per_reset'])][row['arm']] = row
    comparisons=[]
    categories=defaultdict(Counter)
    for (baseline,tier),arms in paired.items():
        if set(arms)!={'single-path','trajectory'}:
            raise ValueError('A paired arm is missing')
        left,right=arms['single-path'],arms['trajectory']
        lc,rc=left['costs'],right['costs']
        comparison=pair_cpu(lc['standalone_total_helper_cpu'],rc['standalone_total_helper_cpu'],
            prior_a=lc['prior2_helper_cpu'],prior_b=rc['prior2_helper_cpu'])
        decisions=[dict(percent=a['percent'],outcome=outcome(a,b)) for a,b in zip(left['decisions'],right['decisions'])]
        comparisons.append(dict(baseline_id=baseline,tier_label=left['tier_label'],speech=left['speech'],
            source_ordinal=left['source_ordinal'],profile=left['profile'],phase=left['phase'],
            cpu=comparison,decisions=decisions))
        for decision in decisions:
            category=('matched' if comparison['matched_total_cpu'] else 'unmatched')+'/'+str(decision['percent'])
            categories[category][decision['outcome']] += 1
    aggregate_cost=Counter()
    for row in public:
        for name,value in row['costs'].items():
            if name not in ('cumulative_total_helper_cpu','prior2_helper_cpu'):
                aggregate_cost[name] += value
    summary=dict(status='PASS',arm_records=248,helper_calls=312,pair_contexts=124,cap_views=744,
        nominal_search_cpu_seconds=984,new_initial_fits=0,no_old_whole_metric_reuse=True,
        source_commit=bindings[0]['source_commit'],matched_total_helper_cpu_pairs=sum(c['cpu']['matched_total_cpu'] for c in comparisons),
        unmatched_total_helper_cpu_pairs=sum(not c['cpu']['matched_total_cpu'] for c in comparisons),
        standalone_actual_cost_sums=dict(aggregate_cost),outcomes={key:dict(value) for key,value in categories.items()},
        distinct_changed_selected_whole_chains=len(selected_chains),workers=summaries,synthetic_preflight=preflight,
        cache_cost_attribution='Actual creating-event cost; per-arm whole workflow time depends on shared-cache order',
        end_to_end_same_cpu_claim=False,scope='Same-corpus numerical comparison; no audible or new complete-player admission')
    inputs.verify()
    save(args.output/'rows.json',public)
    save(args.output/'pairs.json',comparisons)
    save(args.output/'summary.json',summary)
    save(args.output/'changed-selected-chains-private.json',list(selected_chains.values()))
    save(args.output/'binding-private.json',dict(inputs_sha256=inputs.pins))
    print(json.dumps(dict(status='PASS',arm_records=248,helper_calls=312,matched_pairs=summary['matched_total_helper_cpu_pairs'],
        changed_selected_chains=len(selected_chains))),flush=True)


if __name__=='__main__':
    main()

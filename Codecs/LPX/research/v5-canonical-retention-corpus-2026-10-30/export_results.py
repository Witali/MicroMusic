"""Reopen immutable shard outputs and project anonymous numeric evidence."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from runtime import HERE,save
from saved_corpus import FLAG_KEYS,Inputs,sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shards',nargs=2,required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):
        parser.error('Use a fresh private output under the research worktree build directory')
    inputs = Inputs()
    rows,bindings,summaries = [],[],[]
    artifacts,keys = {},set()
    for folder in map(Path.resolve,args.shards):
        binding = json.loads(inputs.read(folder/'binding-private.json'))
        summary = json.loads(inputs.read(folder/'summary.json'))
        attempt = json.loads(inputs.read(folder/'attempt-private.json'))
        results = json.loads(inputs.read(folder/'results-private.json'))
        if (summary['status']!='PASS' or attempt['status']!='complete'
                or summary['new_fits'] or summary['new_refinements'] or attempt['forbidden_search_attempts']
                or summary['reused_old_whole_metric_rows'] or len(results)!=summary['records']
                or any(event['status']!='complete' for event in attempt['records'])):
            raise ValueError('Every actual shard must be terminal complete with zero new search')
        for name,digest in binding['source_snapshot'].items():
            if sha((HERE/name).read_bytes()) != digest:
                raise ValueError('Executed research source changed')
        for path,digest in binding['inputs_sha256'].items():
            inputs.read(path,digest)
        for row in results:
            key = row['phase'],row['source_ordinal'],row['profile']
            if key in keys or row['source_ordinal']%2!=summary['shard']:
                raise ValueError('Shard records overlap or violate parity')
            keys.add(key)
            path = folder/'records'/row['phase']/('source-%03d'%row['source_ordinal'])/('profile-%d'%row['profile'])/'result-private.json'
            if json.loads(inputs.read(path)) != row:
                raise ValueError('Per-record immutable receipt differs from shard aggregate')
            report = row['report']
            if len(row['chains'])!=len(report['candidates']) or report['validation']['whole_metric_rows']!=len(row['chains']):
                raise ValueError('Canonical whole-chain coverage differs')
            for chain,value in zip(row['chains'],report['candidates']):
                blobs = tuple(inputs.stream(meta) for meta in chain['segments'])
                if chain['id']!=value['id'] or sum(map(len,blobs))!=value['stream_bytes']:
                    raise ValueError('Reopened actual whole-chain cost differs')
                artifacts[key+(chain['id'],)] = blobs
            rows.append(row)
        bindings.append(binding)
        summaries.append(summary)
    if ({s['shard'] for s in summaries}!={0,1} or len(keys)!=118
            or Counter(row['phase'] for row in rows)!=Counter({'speech-screen':98,'speech-default':14,'nonspeech-default':6})
            or bindings[0]['source_snapshot']!=bindings[1]['source_snapshot']
            or bindings[0]['selector_commit']!=bindings[1]['selector_commit']):
        raise ValueError('The complete original population or committed replay epoch differs')
    projection,new_chains = [],{}
    phase_counts = {phase:Counter() for phase in ('speech-screen','speech-default','nonspeech-default')}
    total = Counter()
    for row in rows:
        candidates = row['report']['candidates']
        baseline = candidates[0]
        public = {name:row[name] for name in ('phase','source_ordinal','profile','mode','samples','reset_segments',
            'searched_reset_indices','original_bytes','targeted_not_independent_heldout')}
        public['whole_chains'] = len(candidates)
        public['decisions'] = []
        for decision in row['decisions']:
            if not decision['never_worse_than_known_incumbents']:
                raise ValueError('An incumbent assertion was not completed')
            identifier = decision['selected_id']
            chosen = None if identifier is None else candidates[identifier]
            d = {name:decision[name] for name in ('percent','cap','selected_id','raw_id','fitting_chains',
                'eligible_chains','no_fit','no_automatic_admission','selected_player_status','never_worse_than_known_incumbents')}
            d.update(stream_bytes=None if chosen is None else chosen['stream_bytes'],
                score=None if chosen is None else chosen['score'],rollback_bytes=baseline['stream_bytes'],
                rollback_score=baseline['score'],old_incumbents=decision['old_incumbents'])
            for domain in ('pcm16','pwm8'):
                d[domain+'_sse'] = None if chosen is None else chosen['metrics'][domain]['error_energy']
                d[domain+'_stoi'] = None if chosen is None else chosen['metrics'][domain]['stoi']
            if chosen is not None:
                if (not chosen['automatic_quality_eligible'] or chosen['stream_bytes']>decision['cap']
                        or not all(chosen[name] for name in FLAG_KEYS)):
                    raise ValueError('A final selected row fails an actual whole gate')
                d['within_tolerance_pcm'] = chosen['voice']['within_tolerance_frames']
                d['within_tolerance_pwm'] = chosen['pwm_voice']['within_tolerance_frames']
            status = decision['selected_player_status']
            phase_counts[row['phase']]['cap_views'] += 1
            phase_counts[row['phase']]['admitted'] += chosen is not None
            phase_counts[row['phase']][status or 'no-admission'] += 1
            if status=='requires-new-proof':
                key = row['phase'],row['source_ordinal'],row['profile'],identifier
                blobs = artifacts[key]
                if blobs not in new_chains:
                    new_chains[blobs] = dict(id=len(new_chains),profile=row['profile'],samples=row['samples'],
                        stream_bytes=chosen['stream_bytes'],segments=row['chains'][identifier]['segments'],contexts=[])
                new_chains[blobs]['contexts'].append(dict(phase=row['phase'],source_ordinal=row['source_ordinal'],
                    profile=row['profile'],percent=decision['percent'],mode=row['mode']))
            public['decisions'].append(d)
        projection.append(public)
    for summary in summaries:
        total.update(summary['counters'])
    summary = dict(status='PASS',records=118,cap_views=354,new_fits=0,new_refinements=0,
        reused_old_whole_metric_rows=0,canonical_selector_commit=bindings[0]['selector_commit'],
        counters=dict(total),shards=[dict(shard=s['shard'],records=s['records'],wall_seconds=s['wall_seconds']) for s in summaries],
        by_phase={phase:dict(counts) for phase,counts in phase_counts.items()},
        distinct_new_selected_chains_requiring_player_proof=len(new_chains),
        scope='Saved-corpus regression only; no new full Flash/player or perceptual admission')
    inputs.verify()
    save(args.output/'results.json',sorted(projection,key=lambda r:(r['phase'],r['source_ordinal'],r['profile'])))
    save(args.output/'summary.json',summary)
    save(args.output/'new-player-chains-private.json',list(new_chains.values()))
    save(args.output/'export-binding-private.json',dict(inputs_sha256=inputs.pins,
        source_snapshots=[b['source_snapshot'] for b in bindings],selector_commit=bindings[0]['selector_commit']))
    print(json.dumps(summary),flush=True)


if __name__ == '__main__':
    main()

"""Read-only baseline/scope handoff for a future matched-CPU search experiment."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PRIORITY = {'speech-default':0,'speech-screen':1,'nonspeech-default':0}


def load_helper():
    path = HERE.parent/'v5-canonical-retention-corpus-2026-10-30/saved_corpus.py'
    spec = importlib.util.spec_from_file_location('matched_cpu_saved_inputs',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def context(row):
    return row['phase']=='nonspeech-default',row['source_ordinal'],row['profile'],row['mode']


def selected100(row):
    decision = next(d for d in row['decisions'] if d['percent']==100)
    identifier = decision['selected_id']
    if identifier is None:
        raise ValueError('Every canonical 100 percent baseline must be present')
    value = row['report']['candidates'][identifier]
    if not value['automatic_quality_eligible'] or value['stream_bytes']>decision['cap']:
        raise ValueError('A current canonical baseline is ineligible or oversized')
    return identifier,value


def strongest(rows):
    if not rows or len({context(row) for row in rows})!=1:
        raise ValueError('Only identical source/profile/declared-level contexts may compete')
    return min(rows,key=lambda row:(selected100(row)[1]['score'],selected100(row)[1]['stream_bytes'],PRIORITY[row['phase']]))


def prepare(study,shards,output):
    helper = load_helper()
    inputs = helper.Inputs()
    binding,originals = helper.load_saved(study,inputs)
    indexed = {helper.key(item['saved']):item for item in originals}
    rows,receipts = [],[]
    for folder in map(Path.resolve,shards):
        source = json.loads(inputs.read(folder/'binding-private.json'))
        attempt = json.loads(inputs.read(folder/'attempt-private.json'))
        summary = json.loads(inputs.read(folder/'summary.json'))
        records = json.loads(inputs.read(folder/'results-private.json'))
        if (attempt['status']!='complete' or summary['status']!='PASS' or summary['records']!=len(records)
                or attempt['forbidden_search_attempts'] or summary['new_fits'] or summary['new_refinements']):
            raise ValueError('Only complete guarded zero-fit canonical replay receipts may seed this study')
        for path,digest in source['inputs_sha256'].items():
            inputs.read(path,digest)
        for row in records:
            private = folder/'records'/row['phase']/('source-%03d'%row['source_ordinal'])/('profile-%d'%row['profile'])/'result-private.json'
            if json.loads(inputs.read(private))!=row:
                raise ValueError('A retained canonical result differs from its completed aggregate')
            row = {**row,'receipt_path':str(private)}
            rows.append(row)
        receipts.append(source)
    if (len(rows)!=118 or {helper.key(row) for row in rows}!=set(indexed)
            or receipts[0]['selector_commit']!=receipts[1]['selector_commit']):
        raise ValueError('The complete canonical replay population or selector epoch differs')
    grouped = defaultdict(list)
    for row in rows:
        grouped[context(row)].append(row)
    baselines,baseline_ids = [],{}
    stronger = 0
    for identity,views in grouped.items():
        winner = strongest(views)
        item = indexed[helper.key(winner)]
        identifier,value = selected100(winner)
        metas = winner['chains'][identifier]['segments']
        blobs = tuple(inputs.stream(meta) for meta in metas)
        cost = sum(map(len,blobs))
        if cost!=value['stream_bytes'] or sum(meta['samples'] for meta in metas)!=winner['samples']:
            raise ValueError('Current baseline ordered byte cost or complete length differs')
        targets = {indexed[helper.key(row)]['saved']['target_reference_pcm16_sha256'] for row in views}
        if len(targets)!=1:
            raise ValueError('Paired source targets differ')
        index = len(baselines)
        baseline_ids[identity] = index
        baselines.append(dict(id=index,nonspeech=identity[0],source_ordinal=identity[1],profile=identity[2],mode=identity[3],
            samples=winner['samples'],segments=metas,stream_bytes=cost,canonical_whole_candidate_id=identifier,
            source_phase=winner['phase'],source_result_path=winner['receipt_path'],
            reference=item['record']['reference'],level=item['saved']['level'],
            target_reference_pcm16_sha256=next(iter(targets)),canonical_whole_value=value))
        stronger += sum((value['score'],cost)<(selected100(row)[1]['score'],selected100(row)[1]['stream_bytes']) for row in views)
    jobs = []
    nominal = calls = 0
    for original in binding['jobs']:
        record = (binding['speech_records'] if original['speech'] else binding['nonspeech_records'])[original['record_index']]
        identity = not original['speech'],original['source_ordinal'],record['profile'],original['mode']
        baseline = baselines[baseline_ids[identity]]
        tiers = (2,) if original['phase']=='speech-screen' else (8,) if original['phase']=='speech-default' else (2,8)
        for tier in tiers:
            # Counterbalance fixed arm order using only pre-outcome identifiers.
            arms = ('single-path','trajectory') if (original['source_ordinal']+record['profile']//2+tier//2)%2==0 else ('trajectory','single-path')
            for arm in arms:
                jobs.append(dict(id=len(jobs),phase=original['phase'],source_ordinal=original['source_ordinal'],
                    profile=record['profile'],mode=original['mode'],speech=original['speech'],
                    baseline_id=baseline['id'],arm=arm,cpu_seconds_per_reset=tier,
                    edited_segments=original['edited_segments'],local_byte_cap=min(baseline['stream_bytes'],65535),
                    whole_byte_caps={str(p):baseline['stream_bytes']*p//100 for p in (100,95,90)}))
                calls += len(original['edited_segments'])
                nominal += tier*len(original['edited_segments'])
    if len(baselines)!=104 or len(jobs)!=248 or calls!=312 or nominal!=984:
        raise ValueError('The predeclared baseline/search scope changed')
    inputs.verify()
    private = dict(schema='lpx-matched-search-cpu-baselines-private-v1',status='prepared-not-launched',
        canonical_selector_commit=receipts[0]['selector_commit'],inputs_sha256=inputs.pins,
        baselines=baselines,jobs=jobs,search_outcomes_present=False)
    summary = dict(status='prepared-not-launched',unique_baseline_contexts=104,original_records=118,
        arm_records=248,helper_calls=312,derived_cap_views=744,nominal_search_cpu_seconds=984,
        stronger_baseline_than_original_phase_rows=stronger,
        baselines_by_domain=dict(Counter('nonspeech' if b['nonspeech'] else 'speech' for b in baselines)),
        new_fits=0,new_refinements=0,model_calls=0,native_calls=0,whole_metric_calls=0,
        scope='Read-only preparatory baseline inventory; no matched-CPU outcomes')
    output.mkdir(parents=True)
    for name,value in (('binding-private.json',private),('summary.json',summary)):
        (output/name).write_bytes((json.dumps(value,indent=2,allow_nan=False)+'\n').encode())
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',required=True,type=Path)
    parser.add_argument('--shards',required=True,nargs=2,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):
        parser.error('Use fresh private storage in the owning worktree build directory')
    print(json.dumps(prepare(args.study,args.shards,args.output)),flush=True)


if __name__=='__main__':
    main()

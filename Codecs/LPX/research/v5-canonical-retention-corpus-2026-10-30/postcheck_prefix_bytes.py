"""Independent static-rank/actual-byte postcheck after canonical replay."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from runtime import HERE,load_module,save
from saved_corpus import Inputs,incumbent_views,key,load_saved,old_chains


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',required=True,type=Path)
    parser.add_argument('--shards',required=True,nargs=2,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):
        parser.error('Use fresh private research build output')
    inputs = Inputs()
    _,items = load_saved(args.study,inputs)
    indexed = {key(item['saved']):item for item in items}
    prefix = load_module('independent_prior_prefix',HERE.parent/'v5-prefix-retention-2026-10-30/prefixes.py')
    rows = {}
    for folder in map(Path.resolve,args.shards):
        attempt = json.loads(inputs.read(folder/'attempt-private.json'))
        if attempt['status']!='complete':
            raise ValueError('Both replay workers must be terminal before postcheck')
        for row in json.loads(inputs.read(folder/'results-private.json')):
            identifier = row['phase'],row['source_ordinal'],row['profile']
            if identifier in rows:
                raise ValueError('Overlapping replay records')
            rows[identifier] = row
    if set(rows)!=set(indexed):
        raise ValueError('Postcheck must cover the exact full 118-record population')
    counts = Counter()
    for identifier,item in indexed.items():
        result = rows[identifier]
        baseline = old_chains(item,inputs)['control'][0]
        actual,labels = [],{}
        for chain,value in zip(result['chains'],result['report']['candidates']):
            blobs = tuple(inputs.stream(meta) for meta in chain['segments'])
            if chain['id']!=value['id'] or len(blobs)!=len(baseline) or blobs in actual:
                raise ValueError('Actual sink identity/order/dedup differs')
            actual.append(blobs)
            for label in value['labels']:
                if label in labels:
                    raise ValueError('A canonical role label is repeated')
                labels[label] = blobs
        if labels.get('control')!=baseline:
            raise AssertionError('Actual canonical control differs')
        for index,(_,blobs) in enumerate(incumbent_views(item,indexed,inputs)):
            if labels.get('incumbent-%d'%index)!=blobs:
                raise AssertionError('A canonical incumbent maps to different actual bytes')
            counts['incumbent_label_byte_comparisons'] += 1
        histories = item['saved']['segment_searches']
        max_depth = max(len(h['report']['stages']) for h in histories)
        for depth in range(max_depth+1):
            for name in ('selected','raw'):
                expected = list(baseline)
                for history in histories:
                    chosen = prefix.ranked_prefix_ids(history['report'],depth)[name]
                    if chosen is None:
                        expected = None
                        break
                    expected[history['index']] = inputs.stream(history['pool'][chosen])
                label = 'prefix-%d-%s'%(depth,name)
                if expected is None:
                    if label in labels:
                        raise AssertionError('An absent independent prefix acquired a canonical chain')
                    counts['absent_prefix_views_checked'] += 1
                elif labels.get(label)!=tuple(expected):
                    raise AssertionError('Canonical prefix wiring differs from independent ordered saved bytes')
                else:
                    counts['prefix_label_byte_comparisons'] += 1
                    searched = {h['index'] for h in histories}
                    for index in range(len(baseline)):
                        if index not in searched:
                            if labels[label][index]!=baseline[index]:
                                raise AssertionError('An unsearched reset changed')
                            counts['fixed_unsearched_reset_byte_comparisons'] += 1
        if item['saved']['phase']=='speech-default':
            shallow = indexed[('speech-screen',item['saved']['source_ordinal'],item['saved']['profile'])]
            old = old_chains(shallow,inputs)
            for name in ('selected','raw'):
                original = old.get('concat-'+name)
                if (None if original is None else original[0]) != labels.get('prefix-1-'+name):
                    raise AssertionError('Default prefix1 does not equal actual screen whole selection/raw')
                counts['paired_prefix1_actual_whole_byte_comparisons'] += 1
        counts['records'] += 1
    inputs.verify()
    receipt = dict(status='PASS',scope='Post-replay independent static-rank ordered-byte assertion only',
        counts=dict(counts),new_fits=0,new_refinements=0,model_calls=0,native_calls=0,whole_metric_calls=0)
    save(args.output/'postcheck.json',receipt)
    save(args.output/'binding-private.json',dict(inputs_sha256=inputs.pins))
    print(json.dumps(receipt),flush=True)


if __name__ == '__main__':
    main()

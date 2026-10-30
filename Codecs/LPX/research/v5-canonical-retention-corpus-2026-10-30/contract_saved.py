"""Read-only actual saved-row contract; no model, fitting or whole metrics."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys
import time
import traceback

from runtime import HERE,full_audit_gate,load_module,save,target_for
from saved_corpus import Inputs,histories,key,load_saved,old_chains,player_union


def check(args):
    inputs = Inputs()
    full_audit_gate(args.study,args.audit,args.auditor,inputs)
    binding,items = load_saved(args.study,inputs)
    module = load_module('retention_contract_frozen_auditor',args.auditor)
    auditor = module.Auditor(args.source_root,args.study,args.output)
    auditor.context()
    auditor.workers()
    for phase in ('speech-screen','speech-default','nonspeech-default'):
        for shard in (0,1):
            inputs.read(args.study/'workers'/(phase+'-shard-%d-private.json'%shard))
    prefix = load_module('retention_contract_prior_prefix',HERE.parent/'v5-prefix-retention-2026-10-30/prefixes.py')
    counts = Counter()
    pools = {}
    indexed = {key(item['saved']):item for item in items}
    for item in items:
        target_for(item,auditor,module.equal)
        history = histories(item,inputs,module.rank_pool,module.equal)
        for local in history:
            n = item['record']['segments'][local['index']]['samples']
            for blob in local['pool']:
                module.equal(auditor.C.compact.unpack(blob)[:2],(n,item['record']['profile']),'pool-header')
                counts['actual_pool_bytes_bound'] += len(blob)
            for depth in range(len(local['report']['stages'])+1):
                prefix.ranked_prefix_ids(local['report'],depth)
                counts['prefix_local_ranks'] += 1
            counts['pool_rows'] += len(local['pool'])
        pools[key(item['saved'])] = history
        for blobs,_ in old_chains(item,inputs).values():
            for index,blob in enumerate(blobs):
                module.equal(auditor.C.compact.unpack(blob)[:2],
                    (item['record']['segments'][index]['samples'],item['record']['profile']),'whole-header')
        counts['records'] += 1
        counts['target_records_auto_quiet'] += item['saved']['mode']=='auto-quiet'
        counts['partial_history_records'] += len(history)!=len(item['record']['segments'])
        counts['searched_resets'] += len(history)
    for item in items:
        row = item['saved']
        if row['phase'] != 'speech-default':
            continue
        deep = pools[key(row)]
        shallow = pools[('speech-screen',row['source_ordinal'],row['profile'])]
        module.equal([h['index'] for h in deep],[h['index'] for h in shallow],'paired-history-indices')
        for a,b in zip(deep,shallow):
            rank = prefix.ranked_prefix_ids(a['report'],1)
            for label in ('selected','raw'):
                identifier,old = rank[label],b['report'][label+'_id']
                module.equal(identifier is None,old is None,'paired-prefix-presence')
                if identifier is not None:
                    module.equal(a['pool'][identifier],b['pool'][old],'paired-prefix-bytes')
                counts['paired_prefix1_byte_comparisons'] += 1
    union = player_union(items,inputs)
    inputs.verify()
    auditor.context()
    return dict(status='PASS',counts=dict(counts),old_player_union_chains=len(union),
        model_calls=0,whole_metric_calls=0,new_fits=0,new_refinements=0),inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','study','audit','auditor','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    args = parser.parse_args()
    for name in ('source_root','study','audit','auditor','output'):
        setattr(args,name,getattr(args,name).resolve())
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):
        parser.error('Use a fresh private output under this research worktree build directory')
    args.output.mkdir(parents=True)
    began = time.perf_counter()
    try:
        result,inputs = check(args)
        result['wall_seconds'] = time.perf_counter()-began
        save(args.output/'contract.json',result)
        save(args.output/'binding-private.json',dict(inputs_sha256=inputs.pins))
        print(__import__('json').dumps(result),flush=True)
        return 0
    except Exception as exc:
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(__import__('json').dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

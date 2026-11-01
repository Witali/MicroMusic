"""Invoke canonical whole-chain retention on all saved V2 histories, without fitting."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

from runtime import CORE,HERE,full_audit_gate,load_module,save,source_snapshot,target_for
from saved_corpus import (FLAG_KEYS,VALUE_KEYS,Inputs,assert_incumbent,histories,
    incumbent_views,key,known_rows,load_saved,old_chains,paired_screen,player_status,player_union,sha)


def prohibit_search(attempt,output,selector,counters):
    stack = ExitStack()
    def forbidden(*args,**kwargs):
        attempt['forbidden_search_attempts'] += 1
        save(output/'attempt-private.json',attempt)
        raise AssertionError('Fitting, refinement and native builds are forbidden during replay')
    names = {'adaptive_speech_voice':('encode','refine_candidates','enhance','refine_header','refine'),
        'speech_v4':('encode','search'), 'enhance_speech_compact':('enhance',),
        'refine_speech_compact':('refine',),'refine_speech_lpc':('refine',),
        'encode_speech_voice':('encode',),'batch_decoder':('build_library',)}
    for name,attributes in names.items():
        module = sys.modules.get(name)
        if module is not None:
            for attribute in attributes:
                if hasattr(module,attribute):
                    stack.enter_context(patch.object(module,attribute,forbidden))
    for attribute in ('refine_candidates','encode'):
        stack.enter_context(patch.object(selector,attribute,forbidden))
    measure = selector._measure
    def measured(*args,**kwargs):
        counters['whole_metric_rows_started'] += 1
        value = measure(*args,**kwargs)
        counters['whole_metric_rows_completed'] += 1
        return value
    stack.enter_context(patch.object(selector,'_measure',measured))
    model = selector.compact.decode_model
    def modeled(blob,*args,**kwargs):
        counters['model_reset_calls_started'] += 1
        value = model(blob,*args,**kwargs)
        counters['model_reset_calls_completed'] += 1
        counters['model_samples_completed'] += len(value)
        return value
    stack.enter_context(patch.object(selector.compact,'decode_model',modeled))
    return stack


def bind_selector(root,commit,inputs):
    tools = root/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'
    for name in ('speech_chain_history.py','adaptive_speech_chain.py'):
        raw = inputs.read(tools/name)
        claimed = subprocess.check_output(['git','-C',str(root),'show',commit+':Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/'+name])
        if raw != claimed:
            raise ValueError('Canonical selector source differs from the explicit committed epoch')
    # Frozen primitive modules were loaded first. Only these two promoted modules
    # are explicitly loaded from the integration checkout; no path-wide override.
    load_module('speech_chain_history',tools/'speech_chain_history.py')
    return load_module('adaptive_speech_chain',tools/'adaptive_speech_chain.py')


def bind_union(path,proof,rows,inputs):
    original = player_union(rows,inputs)
    handoff_raw = inputs.read(path)
    handoff = json.loads(handoff_raw)
    receipt = json.loads(inputs.read(proof))
    if (not handoff['image_launch_allowed'] or handoff['missing'] or len(handoff['chains']) != 75
            or receipt['status'] != 'complete' or receipt['handoff_sha256'] != sha(handoff_raw)
            or receipt['summary']['unique_chains'] != 75 or receipt['summary']['passed'] != 150):
        raise ValueError('The prior fixed player union proof is incomplete')
    actual = set()
    for item in handoff['chains']:
        entry = item['entry']
        actual.add(tuple(inputs.stream(part) for part in entry['segments']))
    if actual != original:
        raise ValueError('Reconstructed prior union differs from its actual player handoff')
    return original


def replay(item,indexed,inputs,auditor,module,selector,union,output,attempt,counters):
    row,record = item['saved'],item['record']
    folder = output/'records'/row['phase']/('source-%03d'%row['source_ordinal'])/('profile-%d'%row['profile'])
    target = target_for(item,auditor,module.equal)
    local = histories(item,inputs,module.rank_pool,module.equal)
    own = old_chains(item,inputs)
    baseline = own['control'][0]
    extra = incumbent_views(item,indexed,inputs)
    known = known_rows(item,indexed,inputs)
    captured,artifacts = [],[]
    attempt['active_record'] = dict(phase=row['phase'],source_ordinal=row['source_ordinal'],profile=row['profile'])
    event = dict(**attempt['active_record'],status='started',verified_whole_callbacks=0)
    attempt['records'].append(event)
    save(output/'attempt-private.json',attempt)
    began = time.perf_counter()
    before = dict(counters)
    def sink(identifier,blobs):
        if identifier != len(captured) or not isinstance(blobs,tuple) or blobs in captured:
            raise AssertionError('Canonical sink order or exact ordered-byte deduplication differs')
        captured.append(blobs)
        parts = []
        for index,blob in enumerate(blobs):
            path = folder/('chain-%03d'%identifier)/('segment-%03d.l4hy'%index)
            if path.exists():
                raise ValueError('A replay artifact already exists')
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(blob)
            geometry = record['segments'][index]
            parts.append(dict(path=str(path.resolve()),stream_sha256=sha(blob),file_bytes=len(blob),
                index=index,start=geometry['start'],samples=geometry['samples'],profile=row['profile']))
        artifacts.append(parts)
        event['verified_whole_callbacks'] += 1
        attempt['counters'] = dict(counters)
        save(output/'attempt-private.json',attempt)
        print(json.dumps(dict(status='whole-measured',phase=row['phase'],source_ordinal=row['source_ordinal'],
            profile=row['profile'],chain=identifier)),flush=True)
    selected,pcm,report,raw = selector.select_candidates(target,baseline,local,auditor.common,
        max_bytes=row['original_complete_bytes'],compact_decoder=auditor.only,speech=row['speech'],
        incumbents=[blobs for _,blobs in extra],candidate_sink=sink)
    candidates = report['candidates']
    if (len(captured) != len(candidates) or not captured or captured[0] != baseline
            or report['new_refinement_calls'] != 0
            or report['source_refinement_calls'] != row['actual_refinement_calls']
            or report['validation']['whole_metric_rows'] != len(candidates)
            or report['validation']['native_output_domain_comparisons'] != 4*report['validation']['unique_reset_streams']):
        raise AssertionError('Canonical measured work, anchor or source history differs')
    if counters['whole_metric_rows_completed']-before.get('whole_metric_rows_completed',0) != len(candidates):
        raise AssertionError('Canonical whole measurements were not fresh per ordered chain')
    if counters['model_reset_calls_completed']-before.get('model_reset_calls_completed',0) != report['validation']['unique_reset_streams']:
        raise AssertionError('Canonical reset verification counters differ')
    for index,(blobs,value) in enumerate(zip(captured,candidates)):
        if value['id'] != index or sum(map(len,blobs)) != value['stream_bytes']:
            raise AssertionError('Measured candidate ID or actual cost differs')
        for old in known.get(blobs,[]):
            for name in VALUE_KEYS+FLAG_KEYS+('automatic_quality_eligible',):
                module.equal(value[name],old[name],'fresh-known-'+name)
            counters['reproduced_audited_whole_rows'] += 1
    decisions = []
    sources = [item]
    screen = paired_screen(item,indexed)
    if screen is not None:
        sources.append(screen)
    for percent in (100,95,90):
        decision = selector.choose_budget(candidates,row['original_complete_bytes']*percent//100)
        identifier = decision['selected_id']
        chosen = None if identifier is None else candidates[identifier]
        previous = []
        for source in sources:
            old = next(d for d in source['saved']['budgets'] if d['percent']==percent)
            role = old['selected']
            if role is not None:
                blobs,value = old_chains(source,inputs)[role]
                if blobs not in captured:
                    raise AssertionError('A mandatory previously selected whole chain disappeared')
                assert_incumbent(chosen,value,decision['cap'])
                previous.append(dict(phase=source['saved']['phase'],stream_bytes=value['stream_bytes'],score=value['score']))
        decision.update(percent=percent,never_worse_than_known_incumbents=True,old_incumbents=previous,
            selected_player_status=None if identifier is None else player_status(captured[identifier],baseline,union))
        decisions.append(decision)
    for label,value in (('selected',selected),('raw',raw)):
        identifier = report[label+'_id']
        if (value is None) != (identifier is None) or identifier is not None and value != captured[identifier]:
            raise AssertionError('Canonical returned bytes differ from reported choice')
    if selected is not None and (pcm is None or len(pcm)!=len(target)):
        raise AssertionError('Selected whole PCM does not cover the target')
    result = dict(phase=row['phase'],source_ordinal=row['source_ordinal'],profile=row['profile'],
        mode=row['mode'],samples=len(target),reset_segments=len(baseline),searched_reset_indices=[h['index'] for h in local],
        original_bytes=row['original_complete_bytes'],targeted_not_independent_heldout=row['targeted_not_independent_heldout'],
        report=report,decisions=decisions,incumbent_labels=[name for name,_ in extra],
        chains=[dict(id=i,segments=parts) for i,parts in enumerate(artifacts)])
    save(folder/'result-private.json',result)
    event.update(status='complete',seconds=time.perf_counter()-began,whole_chains=len(candidates))
    counters['records_completed'] += 1
    for name,value in report['validation'].items():
        counters['canonical_'+name] += value
    attempt['counters'] = dict(counters)
    save(output/'attempt-private.json',attempt)
    print(json.dumps(dict(status='record-complete',phase=row['phase'],source_ordinal=row['source_ordinal'],
        profile=row['profile'],whole_chains=len(candidates))),flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','study','audit','auditor','selector-root','contract','union-handoff','union-proof','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--selector-commit',required=True)
    parser.add_argument('--shard',required=True,type=int,choices=(0,1))
    args = parser.parse_args()
    for name in ('source_root','study','audit','auditor','selector_root','contract','union_handoff','union_proof','output'):
        setattr(args,name,getattr(args,name).resolve())
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):
        parser.error('Use a fresh private output under this research worktree build directory')
    args.output.mkdir(parents=True)
    attempt = dict(status='started',shard=args.shard,new_fits=0,new_refinements=0,forbidden_search_attempts=0,records=[])
    save(args.output/'attempt-private.json',attempt)
    began = time.perf_counter()
    counters = Counter()
    try:
        sources = source_snapshot()
        inputs = Inputs()
        full_audit_gate(args.study,args.audit,args.auditor,inputs)
        contract = json.loads(inputs.read(args.contract/'contract.json'))
        if contract['status']!='PASS' or contract['counts']['records']!=118 or contract['new_fits'] or contract['new_refinements']:
            raise ValueError('The complete zero-fit saved-row contract must pass before replay')
        prior = json.loads(inputs.read(args.contract/'binding-private.json'))
        for path,digest in prior['inputs_sha256'].items():
            inputs.read(path,digest)
        binding,items = load_saved(args.study,inputs)
        if binding['core_commit'] != CORE:
            raise ValueError('The frozen source core changed')
        module = load_module('canonical_replay_frozen_auditor',args.auditor)
        auditor = module.Auditor(args.source_root,args.study,args.output)
        auditor.context()
        auditor.workers()
        selector = bind_selector(args.selector_root,args.selector_commit,inputs)
        union = bind_union(args.union_handoff,args.union_proof,items,inputs)
        indexed = {key(item['saved']):item for item in items}
        assigned = [item for item in items if item['saved']['source_ordinal']%2==args.shard]
        save(args.output/'binding-private.json',dict(inputs_sha256=inputs.pins,source_snapshot=sources,
            source_core_commit=CORE,selector_commit=args.selector_commit,selector_root=str(args.selector_root),
            source_root=str(args.source_root),study=str(args.study),shard=args.shard,assigned_records=len(assigned),
            own_commit=subprocess.check_output(['git','-C',str(HERE),'rev-parse','HEAD'],text=True).strip(),
            old_whole_metric_reuse=False))
        with prohibit_search(attempt,args.output,selector,counters), auditor.C.BatchSession('batch',prebuilt=args.study/'native/common.so') as common, auditor.C.BatchSession('batch',prebuilt=args.study/'native/v5-only.so') as only:
            auditor.common,auditor.only = common,only
            results = [replay(item,indexed,inputs,auditor,module,selector,union,args.output,attempt,counters) for item in assigned]
        auditor.context()
        inputs.verify()
        if (sources != source_snapshot() or len(results)!=len(assigned) or attempt['forbidden_search_attempts']
                or any(event['status']!='complete' for event in attempt['records'])):
            raise AssertionError('Replay source, completion or zero-fit contract changed')
        # Artifact descriptors are private. This receipt does not claim any new
        # chain's full Flash or interrupt-active player admission.
        summary = dict(status='PASS',shard=args.shard,records=len(results),new_fits=0,new_refinements=0,
            reused_old_whole_metric_rows=0,counters=dict(counters),wall_seconds=time.perf_counter()-began,
            by_phase=dict(Counter(row['phase'] for row in results)))
        save(args.output/'results-private.json',results)
        save(args.output/'summary.json',summary)
        attempt.update(status='complete',active_record=None,counters=dict(counters),seconds=summary['wall_seconds'])
        save(args.output/'attempt-private.json',attempt)
        print(json.dumps(summary),flush=True)
        return 0
    except Exception as exc:
        attempt.update(status='failed',exception_type=type(exc).__name__,counters=dict(counters),seconds=time.perf_counter()-began)
        save(args.output/'attempt-private.json',attempt)
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Freeze only new canonical automatic selections and their exact rollbacks.

Read-only with respect to every input. No player build/simulation, fitting,
refinement or whole-quality recomputation is reachable from this preparation.
The unchanged, separately pinned prior dispatcher consumes the final handoff.
"""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
import math
from pathlib import Path
import sys
import traceback

THIS = Path(__file__).resolve()
HERE = THIS.parent
PACKAGE = HERE.parent
GENERIC = PACKAGE.parent/'v5-adaptive-player-union-2026-10-30/reproduction'
sys.path.insert(0, str(GENERIC))
from prepare_union import Epoch, Union, FLASH_BYTES, PHASES, sha, canonical

CORE = '5a6cd1ab9593cac6f7e81756a639fa11d6c21276'
SELECTOR = '976c50c8a341d86eeac7600f51057e575ee87a0a'
FLAGS = ('old_pcm_pwm_floors_passed', 'clipped_sample_floor_passed',
         'pcm_period_coverage_floor_passed', 'pwm_period_coverage_floor_passed',
         'joint_objective_nonregression')


def require(value, message):
    if not value:
        raise ValueError(message)


def decision_from_rows(rows, cap):
    """Reproduce the committed selector's cost/quality/ID ordering, no metrics."""
    require([row['id'] for row in rows] == list(range(len(rows))), 'Whole IDs differ')
    require(all(math.isfinite(row['score']) for row in rows), 'Nonfinite whole objective')
    fitting = [row for row in rows if row['stream_bytes'] <= cap]
    eligible = [row for row in fitting if row['automatic_quality_eligible']]
    key = lambda row: (row['score'], row['stream_bytes'], row['id'])
    return dict(cap=cap, full_flash_cap=None,
        selected_id=None if not eligible else min(eligible, key=key)['id'],
        raw_id=None if not fitting else min(fitting, key=key)['id'],
        fitting_chains=len(fitting), eligible_chains=len(eligible),
        no_fit=not fitting, no_automatic_admission=not eligible)


def context_key(value):
    return tuple(value[name] for name in ('phase','source_ordinal','profile','percent','mode'))


def inventory_map(items, chain):
    """Inventory identity is ordered bytes, never a path, cap or byte total."""
    result = {}
    for item in items:
        blobs = chain(item, item['profile'])
        require(blobs not in result, 'Duplicate byte chain in final inventory')
        contexts = [context_key(context) for context in item['contexts']]
        require(len(contexts) == len(set(contexts)), 'Duplicate inventory context')
        result[blobs] = sorted(contexts)
    return result


def loaded_module(path):
    spec = importlib.util.spec_from_file_location('retention_saved_inputs', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(args):
    epoch = Epoch(args.source_root)
    union = Union(epoch.modules['speech_compact'].unpack)
    read = lambda path: json.loads(union.read(path))
    summary = read(args.export/'summary.json')
    exported = read(args.export/'export-binding-private.json')
    manifest = read(args.export/'new-player-chains-private.json')
    require(summary['status']=='PASS' and summary['records']==118 and summary['cap_views']==354,
            'The complete final replay/export is required')
    require(summary['new_fits']==summary['new_refinements']==summary['reused_old_whole_metric_rows']==0,
            'Replay must use fresh whole metrics and zero search')
    require(summary['canonical_selector_commit']==exported['selector_commit']==SELECTOR,
            'Canonical selector epoch changed')
    for path, digest in exported['inputs_sha256'].items():
        union.read(path, digest)

    bindings, rows = [], []
    for shard, folder in enumerate(args.shards):
        binding = read(folder/'binding-private.json')
        terminal = read(folder/'summary.json')
        attempt = read(folder/'attempt-private.json')
        results = read(folder/'results-private.json')
        require(terminal['status']=='PASS' and terminal['shard']==binding['shard']==shard
                and terminal['records']==len(results)==binding['assigned_records']
                and terminal['new_fits']==terminal['new_refinements']==terminal['reused_old_whole_metric_rows']==0
                and attempt['status']=='complete' and not attempt['forbidden_search_attempts']
                and len(attempt['records'])==len(results)
                and all(event['status']=='complete' for event in attempt['records']),
                'A replay shard is not terminal zero-search PASS')
        require(binding['selector_commit']==SELECTOR and binding['source_core_commit']==CORE
                and not binding['old_whole_metric_reuse'], 'Replay epoch or metric scope changed')
        for name, digest in binding['source_snapshot'].items():
            union.read(args.replay_source/name, digest)
        for path, digest in binding['inputs_sha256'].items():
            union.read(path, digest)
        require(binding['source_snapshot'] in exported['source_snapshots'],
                'Final export omitted executing replay source')
        for row, event in zip(results, attempt['records']):
            key = (row['phase'],row['source_ordinal'],row['profile'])
            require(row['source_ordinal']%2==shard and
                    tuple(event[name] for name in ('phase','source_ordinal','profile'))==key,
                    'Replay parity or event identity changed')
            path = folder/'records'/row['phase']/('source-%03d'%row['source_ordinal'])/('profile-%d'%row['profile'])/'result-private.json'
            require(read(path)==row, 'Replay per-record receipt changed')
        bindings.append(binding)
        rows.extend(results)
    require(bindings[0]['source_snapshot']==bindings[1]['source_snapshot'], 'Replay source shards differ')
    require(len(rows)==118 and len({(r['phase'],r['source_ordinal'],r['profile']) for r in rows})==118
            and Counter(r['phase'] for r in rows)==Counter(dict(zip(PHASES,(98,14,6)))),
            'Complete original corpus coverage changed')

    prior_raw = union.read(args.prior_handoff)
    prior = json.loads(prior_raw)
    prior_proof = read(args.prior_proof)
    require(prior['schema']=='lpx-v5-adaptive-player-union-final-private-v1'
            and prior['image_launch_allowed'] and not prior['missing'] and len(prior['chains'])==75
            and prior_proof['status']=='complete' and prior_proof['handoff_sha256']==sha(prior_raw)
            and prior_proof['summary']['unique_chains']==75 and prior_proof['summary']['passed']==150,
            'The completed original player union differs')
    for path, digest in prior['input_files_sha256'].items():
        union.read(path, digest)
    for path, digest in prior['dispatcher_sources_sha256'].items():
        union.read(path, digest)
    require(prior['source_inventory']==epoch.snapshot(), 'Frozen consumer epoch changed')
    audit = read(Path(prior['admission_gate']['private_audit_path']))
    require(audit['status']=='passed' and audit['completed_records']==audit['expected_records']==118
            and not audit['missing_records'] and audit['all_final_worker_receipts_verified']
            and audit['source_core_commit']==CORE
            and audit['binding_sha256']==prior['study_binding_sha256']
            and audit['auditor_sha256']==sha(union.read(prior['admission_gate']['auditor_source'])),
            'The original independent audit gate changed')
    prepared = read(Path(prior['admission_gate']['prepared_path']))
    require(prepared['source_inventory']==epoch.snapshot(), 'Player preparation source changed')
    study = Path(prior['study_root'])
    require(all(Path(binding['study']).resolve()==study.resolve() for binding in bindings),
            'Replays use a different original study')
    saved = loaded_module(args.replay_source/'saved_corpus.py')
    inputs = saved.Inputs()
    original_binding, originals = saved.load_saved(study, inputs)
    inputs.verify()
    for path, digest in inputs.pins.items():
        union.read(path, digest)
    require(original_binding['core_commit']==CORE
            and sha((study/'binding-private.json').read_bytes())==prior['study_binding_sha256'],
            'Original study binding changed')
    consumer = {n:d for n,d in epoch.snapshot().items() if n.startswith('Codecs/LPX/01_ACTIVE_Q0_CODEC/src/')}
    producer = {n:d for n,d in original_binding['source']['core'].items() if n.startswith('Codecs/LPX/01_ACTIVE_Q0_CODEC/src/')}
    require(consumer==producer, 'Native producer and player decoder sources differ')
    indexed = {saved.key(item['saved']):item for item in originals}
    old_bytes = set()
    for item in prior['chains']:
        entry = {**item['entry'], 'stream_bytes':item['entry']['file_bytes']}
        old_bytes.add(union.chain(entry, entry['profile']))
    require(len(old_bytes)==75, 'Prior ordered-byte union changed')
    require(saved.player_union(originals, inputs)==old_bytes, 'Prior union differs from original decisions')

    actual, decisions, comparison_contexts = {}, [], {}
    pcm_cache = {}
    def register(entry, profile, blobs, role):
        import numpy as np
        if blobs not in pcm_cache:
            pcm = np.concatenate([epoch.modules['speech_compact'].decode_model(blob) for blob in blobs])
            pwm = epoch.modules['standard_metrics'].pwm_duties(pcm).tobytes()
            require(len(pcm)==entry['samples'], 'Model whole output length changed')
            pcm_cache[blobs] = (sha(pcm.astype('<i2').tobytes()),sha(pwm))
        pcm_sha, pwm_sha = pcm_cache[blobs]
        enriched = {**entry,'pcm16_sha256':pcm_sha,'pwm_sha256':pwm_sha}
        return union.register(enriched,profile,blobs,role)
    for row in rows:
        key = row['phase'],row['source_ordinal'],row['profile']
        original = indexed[key]
        record, anchor = original['saved'], original['record']
        require(all(row[name]==record[name] for name in ('phase','source_ordinal','profile','mode','samples','targeted_not_independent_heldout')),
                'Replayed source/level scope changed')
        require(row['original_bytes']==record['original_complete_bytes'],
                'Serialized-data budget anchor changed')
        rollback = next(entry for entry in record['chains'] if entry and entry['role']=='control')
        original_bytes = union.chain(rollback,row['profile'])
        candidates, artifacts = row['report']['candidates'], row['chains']
        require(len(candidates)==len(artifacts)==row['report']['validation']['whole_metric_rows']
                and row['reset_segments']==len(rollback['segments'])
                and [d['percent'] for d in row['decisions']]==[100,95,90], 'Whole-chain replay coverage changed')
        def entry_for(identifier):
            value = candidates[identifier]
            artifact = artifacts[identifier]
            require(artifact['id']==value['id']==identifier, 'Replay artifact ID changed')
            entry = dict(samples=row['samples'],stream_bytes=value['stream_bytes'],segments=artifact['segments'])
            return entry,union.chain(entry,row['profile'])
        require(entry_for(0)[1]==original_bytes, 'Canonical anchor is not exact declared-level rollback')
        for decision in row['decisions']:
            cap = row['original_bytes']*decision['percent']//100
            expected = decision_from_rows(candidates,cap)
            require(all(decision[name]==value for name,value in expected.items())
                    and decision['never_worse_than_known_incumbents'], 'Final replay decision changed')
            identifier = decision['selected_id']
            if identifier is None:
                require(decision['selected_player_status'] is None, 'Missing selection gained player status')
                continue
            chosen = candidates[identifier]
            require(chosen['automatic_quality_eligible'] and all(chosen[name] for name in FLAGS),
                    'An automatic selection fails whole quality gates')
            entry, blobs = entry_for(identifier)
            status = 'unchanged-baseline' if blobs==original_bytes else ('old-union' if blobs in old_bytes else 'requires-new-proof')
            require(decision['selected_player_status']==status, 'New-player classification changed')
            if status!='requires-new-proof':
                continue
            context = dict(phase=row['phase'],source_ordinal=row['source_ordinal'],profile=row['profile'],percent=decision['percent'],mode=row['mode'])
            actual.setdefault(blobs,[]).append(context_key(context))
            old = register(rollback,row['profile'],original_bytes,'declared-level-rollback')
            new = register(entry,row['profile'],blobs,'changed-automatic-selection')
            require(union.registry[original_bytes]['entry']['pcm16_sha256']==rollback['pcm16_sha256']
                    and union.registry[original_bytes]['entry']['pwm_sha256']==rollback['pwm_sha256'],
                    'Declared rollback output proof changed')
            ckey = row['source_ordinal'],row['profile'],row['mode'],record['level']['gain'],old,new
            if ckey not in comparison_contexts:
                comparison_contexts[ckey] = dict(id='comparison-%03d'%(len(comparison_contexts)+1),
                    rollback_chain=old,candidate_chain=new,profile=row['profile'],
                    cohort='speech' if record['speech'] else 'nonspeech',source_ordinal=row['source_ordinal'],
                    mode=row['mode'],input_gain=record['level']['gain'],
                    reference_domain='declared-auto-target' if row['mode']=='auto-quiet' else 'original-level',
                    targeted_not_independent_heldout=row['targeted_not_independent_heldout'],perceptual_adoption=False,selections=[])
            comparison_contexts[ckey]['selections'].append(dict(phase=row['phase'],percent=decision['percent'],cap=cap,role='canonical-%03d'%identifier))
            decisions.append(context)
    require(inventory_map(manifest,union.chain)=={blobs:sorted(contexts) for blobs,contexts in actual.items()},
            'Final inventory is not exactly all genuinely new selected chains/contexts')
    require(len(actual)==summary['distinct_new_selected_chains_requiring_player_proof'], 'Export new-chain count differs')
    inputs.verify()
    for path, digest in inputs.pins.items():
        union.read(path, digest)
    for name, digest in original_binding['native_libraries_sha256'].items():
        union.read(study/'native'/name,digest)
    chains = list(union.registry.values())
    prior_paths = list(map(Path,prior['admission_gate']['prior_paths']))+[args.prior_proof.parent]
    for directory in prior_paths:
        require(read(directory/'results-private.json')['status']=='complete', 'A prior proof index is incomplete')
    sources = (THIS,HERE/'test_preparation.py',PACKAGE/'PROTOCOL.md',GENERIC/'measure_union.py',
               GENERIC/'prepare_union.py',GENERIC/'test_protocol.py',GENERIC.parent/'PROTOCOL.md',
               Path(sys.modules['admit'].__file__),Path(sys.modules['admit'].__file__).parent/'player_evidence.py')
    source_pins = {str(path):sha(path.read_bytes()) for path in sources}
    selected = {item['id'] for item in chains if 'changed-automatic-selection' in item['roles']}
    rollbacks = {item['id'] for item in chains if 'declared-level-rollback' in item['roles']}
    stats = dict(schema='lpx-v5-retention-player-scope-v1',preliminary_unaudited=False,
        image_launch_allowed=bool(actual),independent_audit_gate='passed',all_six_workers_complete=True,
        expected_records=118,observed_complete_records=118,missing_records=0,
        replay_shards_complete=2,cap_views=354,automatic_changed_selection_views=len(decisions),
        unchanged_selection_views_skipped=0,no_automatic_selection_views=0,
        distinct_union_chains=len(chains),distinct_candidate_chains=len(selected),distinct_rollback_chains=len(rollbacks),
        candidate_rollback_overlap=len(selected & rollbacks),distinct_comparisons=len(comparison_contexts),
        chains_already_in_prior_union=sum(blobs in old_bytes for blobs in union.registry),
        logical_image_rows=2*len(chains),selected_image_rows=2*len(selected),rollback_image_rows=2*len(rollbacks),
        data_alone_no_fit_rows=2*sum(item['entry']['file_bytes']>FLASH_BYTES for item in chains),
        maximum_new_build_attempts=2*sum(item['entry']['file_bytes']<=FLASH_BYTES for item in chains),
        potential_full_playback_samples=2*sum(item['entry']['samples'] for item in chains if item['entry']['file_bytes']<=FLASH_BYTES),
        maximum_chain_segments=max((len(item['entry']['segments']) for item in chains),default=0),
        by_phase=dict(Counter(context['phase'] for context in decisions)),new_fits=0,new_refinements=0,
        new_images=0,new_simulations=0,perceptual_adoption=False,
        scope='Only canonical automatic selections absent from the completed75-chain union, paired with exact declared-level rollbacks. Finite preparation, no new image or quality adoption.')
    handoff = dict(schema='lpx-v5-adaptive-player-union-final-private-v1',image_launch_allowed=bool(actual),
        study_root=str(study),study_binding_sha256=prior['study_binding_sha256'],producer_core_commit=CORE,
        consumer_root=str(epoch.root),source_inventory=epoch.snapshot(),chains=chains,
        comparisons=list(comparison_contexts.values()),missing=[],summary=stats,
        input_files_sha256=union.inputs,dispatcher_sources_sha256=source_pins,
        admission_gate={**prior['admission_gate'],'prior_paths':list(map(str,prior_paths))},
        configuration=dict(irq_loads=[0,100],queue=256,prefill=192,assembly=True,flash_bytes=FLASH_BYTES),
        retention_gate=dict(selector_commit=SELECTOR,export_root=str(args.export),replay_source=str(args.replay_source),
            replay_shards=list(map(str,args.shards)),new_selected_chains=len(actual),original_union_chains=75))
    require(epoch.snapshot()==prior['source_inventory'], 'Consumer sources changed during preparation')
    for path, digest in union.inputs.items():
        require(sha(Path(path).read_bytes())==digest, 'A prepared input changed')
    for target in (args.output,args.public_output):
        require(not target.exists(), 'Use fresh immutable preparation output names')
    epoch.modules['output_paths'].protect_outputs([*map(Path,union.inputs),*sources],[args.output,args.public_output])
    epoch.save(args.output,handoff)
    args.public_output.parent.mkdir(parents=True,exist_ok=True)
    args.public_output.write_bytes(json.dumps(stats,indent=2,allow_nan=False).encode()+b'\n')
    print(json.dumps(stats),flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','export','replay-source','prior-handoff','prior-proof','output','public-output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--shards',nargs=2,type=Path,required=True)
    args = parser.parse_args()
    for name in ('source_root','export','replay_source','prior_handoff','prior_proof','output','public_output'):
        setattr(args,name,getattr(args,name).resolve())
    args.shards = list(map(Path.resolve,args.shards))
    try:
        prepare(args)
    except Exception as exc:
        failure = args.output.with_name('preparation-failure-private.json')
        failure.parent.mkdir(parents=True,exist_ok=True)
        require(not failure.exists(), 'Preserve the earlier failed preparation')
        failure.write_bytes(json.dumps(dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()),indent=2).encode()+b'\n')
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())

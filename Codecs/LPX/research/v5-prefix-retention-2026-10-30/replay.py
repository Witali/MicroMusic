"""Fresh whole-chain measurement of bounded saved prefix snapshots only."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

from prefixes import (common_prefix_descriptors, retain_distinct, choose_budget,
                      assert_incumbents_retained)
from saved_inputs import sha, stream, actual_saved_contract

HERE = Path(__file__).resolve().parent
CORE = '5a6cd1ab9593cac6f7e81756a639fa11d6c21276'
VALUE_KEYS = ('metrics','voice','pwm_voice','noise','pwm_noise','domain_scores',
              'score','clipped_samples','voice_components','pwm_voice_components')


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink() or path.exists() and path.stat().st_nlink > 1:
        raise ValueError('Output aliases are forbidden')
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def source_snapshot():
    return {p.name:sha(p.read_bytes()) for p in HERE.iterdir() if p.suffix in ('.py','.md')}


def load_auditor(path):
    spec = importlib.util.spec_from_file_location('prefix_frozen_auditor',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pin_record_inputs(study, rows, pin):
    for profile, phases in rows.items():
        for name, row in phases.items():
            folder = study/'records'/row['phase']/'source-042'/('profile-%d'%profile)
            for path in (folder/'record-private.json',folder/'complete-private.json'):
                pin[str(path.resolve())] = sha(path.read_bytes())
            marker = json.loads((folder/'complete-private.json').read_text())
            for relative,digest in marker['artifacts_sha256'].items():
                path = (folder/relative).resolve()
                if not path.is_relative_to(folder.resolve()) or sha(path.read_bytes()) != digest:
                    raise ValueError('A bound saved artifact changed')
                pin[str(path)] = digest
            for chain in row['chains']:
                if chain is not None:
                    for meta in chain['segments']:
                        stream(meta)
                        pin[str(Path(meta['path']).resolve())] = meta['stream_sha256']


def forbidden_search(state, output):
    stack = ExitStack()
    def forbidden(*args,**kwargs):
        state['forbidden_search_attempts'] += 1
        save(output/'attempt-private.json',state)
        raise AssertionError('Encoding/refinement is forbidden during retained-history replay')
    names = {'adaptive_speech_voice':('encode','refine_candidates','enhance','refine_header','refine'),
             'speech_v4':('encode','search'), 'enhance_speech_compact':('enhance',),
             'refine_speech_compact':('refine',), 'refine_speech_lpc':('refine',),
             'batch_decoder':('build_library',)}
    for name,attributes in names.items():
        module = sys.modules.get(name)
        if module is not None:
            for attribute in attributes:
                if hasattr(module,attribute):
                    stack.enter_context(patch.object(module,attribute,forbidden))
    return stack


def measured_chain(blobs, record, target, auditor, counters):
    """Fresh model/common/v5 PCM/PWM over every reset of a new whole chain."""
    c = auditor.C
    modeled, native_pcm, native_pwm = [], [[],[]], [[],[]]
    if len(blobs) != len(record['segments']):
        raise ValueError('Whole reset count differs')
    position = 0
    for index,(blob,segment) in enumerate(zip(blobs,record['segments'])):
        n = segment['samples']
        if (segment['index'] != index or segment['start'] != position
                or c.compact.unpack(blob)[:2] != (n,record['profile'])):
            raise ValueError('Ordered whole-chain geometry differs')
        counters['fresh_model_reset_calls_started'] += 1
        pcm = c.compact.decode_model(blob)
        duties = c.pwm_duties(pcm)
        if len(pcm) != n:
            raise ValueError('The full model output length differs')
        counters['fresh_model_reset_calls'] += 1
        counters['fresh_model_samples'] += n
        modeled.append(pcm)
        for receiver_index,receiver in enumerate((auditor.common,auditor.only)):
            counters['fresh_native_pcm_calls_started'] += 1
            actual = receiver.decode_one_s16(blob,n)
            counters['fresh_native_pwm_calls_started'] += 1
            pwm = receiver.decode_one(blob,n)
            if (actual is None or pwm is None or not c.np.array_equal(actual,pcm)
                    or not c.np.array_equal(pwm,duties)):
                raise AssertionError('Fresh full-chain native/model PCM/PWM differs')
            native_pcm[receiver_index].append(actual)
            native_pwm[receiver_index].append(pwm)
            counters['fresh_native_output_domain_comparisons'] += 2
        position += n
    pcm = c.np.concatenate(modeled)
    if position != len(target) or len(pcm) != record['samples']:
        raise ValueError('The exact full source was not covered')
    for index in range(2):
        if (not c.np.array_equal(c.np.concatenate(native_pcm[index]),pcm)
                or not c.np.array_equal(c.np.concatenate(native_pwm[index]),c.pwm_duties(pcm))):
            raise AssertionError('Concatenated full native output differs')
        counters['fresh_whole_output_domain_comparisons'] += 2
    # Exact ordered-byte chains are deduplicated before this call. Do not reuse
    # whole metrics for another serialization merely because its PCM is equal.
    auditor.measures.clear()
    before = auditor.counts['unique_metric_rows']
    counters['fresh_whole_metric_rows_started'] += 1
    value = auditor.evaluate(target,pcm,True)
    if auditor.counts['unique_metric_rows'] != before + 1:
        raise AssertionError('A new whole-chain metric row was not measured')
    counters['fresh_whole_metric_rows'] += 1
    return value,sha(pcm.astype('<i2').tobytes()),sha(c.pwm_duties(pcm).tobytes())


def replay_profile(profile, pair, binding, auditor, output, attempt, counters):
    default,screen = pair['default'],pair['screen']
    record = binding['speech_records'][default['record_index']]
    if record['profile'] != profile or len(record['segments']) != 5:
        raise ValueError('Fixed diagnostic source/profile changed')
    target = auditor.reference(record)
    if sha(target.astype('<i2').tobytes()) != default['target_reference_pcm16_sha256']:
        raise ValueError('The declared unchanged target differs')
    choices, known_rows = [], {}
    for phase, saved in (('default',default),('screen',screen)):
        for chain in saved['chains']:
            if chain is not None:
                blobs = tuple(stream(meta) for meta in chain['segments'])
                known_rows.setdefault(blobs,[]).append((phase,chain))
    controls = [tuple(stream(meta) for meta in pair[name]['chains'][0]['segments']) for name in ('default','screen')]
    if controls[0] != controls[1]:
        raise ValueError('Screen/default whole admission anchors differ')
    for chain in default['chains']:
        if chain is not None:
            choices.append(('default-'+chain['role'],[stream(meta) for meta in chain['segments']]))
    screen_roles = {chain['role']:chain for chain in screen['chains'] if chain is not None}
    for decision in screen['budgets']:
        for field,label in (('selected','selected'),('raw_tradeoff','raw')):
            role = decision[field]
            if role is not None:
                choices.append(('screen-%d-%s'%(decision['percent'],label),
                    [stream(meta) for meta in screen_roles[role]['segments']]))
    for depth in range(5):
        for label in ('selected','raw'):
            descriptors = common_prefix_descriptors(default,depth,label)
            choices.append(('prefix-%d-%s'%(depth,label),
                None if descriptors is None else [stream(meta) for meta in descriptors]))
    unique = retain_distinct(choices)
    rows,private_rows = [],[]
    label_ids = {label:item['id'] for item in unique for label in item['labels']}
    anchor = None
    for item in unique:
        attempt['active_chain'] = dict(profile=profile,id=item['id'])
        event = dict(profile=profile,id=item['id'],status='started')
        attempt['whole_chain_events'].append(event)
        save(output/'attempt-private.json',attempt)
        began = time.perf_counter()
        value,pcm_sha,pwm_sha = measured_chain(item['blobs'],record,target,auditor,counters)
        if anchor is None:
            if 'default-control' not in item['labels']:
                raise AssertionError('Stable pool order lost the whole admission anchor')
            anchor = value
        # The audited pure floor function is injected by main.
        flags = auditor._prefix_floors(value,anchor)
        for phase,saved in known_rows.get(item['blobs'],[]):
            for name in VALUE_KEYS:
                auditor._prefix_equal(value[name],saved[name],'fresh-known-'+phase+'-'+name)
            auditor._prefix_equal(item['stream_bytes'],saved['stream_bytes'],'fresh-known-size')
            for name,flag in flags.items():
                auditor._prefix_equal(flag,saved[name],'fresh-known-'+name)
            auditor._prefix_equal(all(flags.values()),saved['automatic_quality_eligible'],'fresh-known-eligibility')
        meta = []
        for index,blob in enumerate(item['blobs']):
            destination = output/('profile-%d'%profile)/('chain-%03d'%item['id'])/('segment-%03d.l4hy'%index)
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(blob)
            geometry = record['segments'][index]
            meta.append(dict(path=str(destination.resolve()),stream_sha256=sha(blob),file_bytes=len(blob),
                index=index,start=geometry['start'],samples=geometry['samples'],profile=profile))
        row = dict(id=item['id'],labels=item['labels'],stream_bytes=item['stream_bytes'],
            automatic_quality_eligible=all(flags.values()),**value,**flags)
        rows.append(row)
        private_rows.append(dict(**row,segments=meta,pcm16_sha256=pcm_sha,pwm_sha256=pwm_sha))
        event.update(status='complete',seconds=time.perf_counter()-began)
        attempt['counters'] = dict(counters)
        save(output/'attempt-private.json',attempt)
        print(json.dumps(dict(status='measured',profile=profile,chain=item['id'],chains=len(unique))),flush=True)
    decisions = []
    for percent in (100,95,90):
        result = choose_budget(rows,default['original_complete_bytes'],percent)
        incumbents = []
        for phase,saved in (('default',default),('screen',screen)):
            old = next(row for row in saved['budgets'] if row['percent'] == percent)
            if old['selected'] is not None:
                label = ('default-'+old['selected']) if phase == 'default' else ('screen-%d-selected'%percent)
                identifier = label_ids[label]
                if not rows[identifier]['automatic_quality_eligible'] or rows[identifier]['stream_bytes'] > old['cap']:
                    raise AssertionError('A previously admitted whole incumbent no longer passes')
                incumbents.append(identifier)
        assert_incumbents_retained(rows,result,incumbents)
        result['known_admitted_incumbent_ids'] = incumbents
        result['never_worse_than_known_incumbents'] = True
        decisions.append(result)
    return dict(source_ordinal=42,profile=profile,samples=len(target),reset_segments=5,
        original_bytes=default['original_complete_bytes'],whole_chains=private_rows,
        decisions=decisions,raw_role_views=len(choices),distinct_whole_chains=len(unique),
        absent_role_views=sum(blobs is None for _,blobs in choices),
        duplicate_role_views_not_remeasured=sum(blobs is not None for _,blobs in choices)-len(unique))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','study','audit','auditor','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    for name in ('source_root','study','audit','auditor','output'):
        setattr(args,name,getattr(args,name).resolve())
    owned = HERE.parents[3]/'build'
    if not args.output.is_relative_to(owned.resolve()) or args.output.exists():
        parser.error('Use a fresh private output under this analysis worktree build directory')
    args.output.mkdir(parents=True)
    attempt = dict(status='started',forbidden_search_attempts=0,whole_chain_events=[],new_seed_fits=0,new_refinements=0)
    save(args.output/'attempt-private.json',attempt)
    started = time.perf_counter()
    counters = Counter()
    try:
        source = source_snapshot()
        module = load_auditor(args.auditor)
        receipt = json.loads(args.audit.read_text())
        binding_raw = (args.study/'binding-private.json').read_bytes()
        binding = json.loads(binding_raw)
        if (receipt['status'] != 'passed' or receipt['completed_records'] != 118 or receipt['expected_records'] != 118
                or receipt['missing_records'] != 0 or not receipt['all_final_worker_receipts_verified']
                or receipt['source_core_commit'] != CORE or binding['core_commit'] != CORE
                or receipt['binding_sha256'] != sha(binding_raw)
                or receipt['auditor_sha256'] != sha(args.auditor.read_bytes())):
            raise ValueError('A matching final 118-row independent PASS is required')
        pairs,contract = actual_saved_contract(args.study)
        for pair in pairs.values():
            for saved in pair.values():
                for search in saved['segment_searches']:
                    report = search['report']
                    ranking,allowed = module.rank_pool(report['candidates'],report['complete_byte_cap'])
                    for label in ('selected_id','raw_id','frontier'):
                        module.equal(ranking[label],report[label],'saved-static-'+label)
                    for index,(meta,row,flag) in enumerate(zip(search['pool'],report['candidates'],allowed)):
                        if meta['id'] != index or row['id'] != index or len(stream(meta)) != row['file_bytes']:
                            raise ValueError('Actual pool byte cost differs from static row')
                        module.equal(flag,row['admissible'],'saved-static-admission')
        save(args.output/'saved-row-contract.json',contract)
        auditor = module.Auditor(args.source_root,args.study,args.output)
        auditor._prefix_floors,auditor._prefix_equal = module.floors,module.equal
        auditor.context()
        inputs = {str(path):sha(path.read_bytes()) for path in (args.audit,args.auditor,
            args.audit.parent/'audit.json',args.audit.parent/'groups.json',args.study/'binding-private.json')}
        pin_record_inputs(args.study,pairs,inputs)
        save(args.output/'binding-private.json',dict(protocol=source,inputs_sha256=inputs,
            own_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            source_root=str(args.source_root),study=str(args.study),core_commit=CORE,
            old_whole_metric_reuse=False,ordered_byte_dedup=True))
        with forbidden_search(attempt,args.output), auditor.C.BatchSession('batch',prebuilt=args.study/'native/common.so') as common, auditor.C.BatchSession('batch',prebuilt=args.study/'native/v5-only.so') as only:
            auditor.common,auditor.only = common,only
            results = [replay_profile(profile,pairs[profile],binding,auditor,args.output,attempt,counters) for profile in (4,6)]
        auditor.context()
        if source_snapshot() != source or any(sha(Path(path).read_bytes()) != digest for path,digest in inputs.items()):
            raise ValueError('Replay source or bound inputs changed')
        if attempt['forbidden_search_attempts'] or any(event['status'] != 'complete' for event in attempt['whole_chain_events']):
            raise AssertionError('A forbidden or incomplete operation occurred')
        projection = []
        for result in results:
            rows = []
            for row in result['whole_chains']:
                rows.append({key:row[key] for key in ('id','labels','stream_bytes','score','automatic_quality_eligible',
                    'old_pcm_pwm_floors_passed','clipped_sample_floor_passed','pcm_period_coverage_floor_passed',
                    'pwm_period_coverage_floor_passed','joint_objective_nonregression')})
                rows[-1].update(pcm_sse=row['metrics']['pcm16']['error_energy'],pwm_sse=row['metrics']['pwm8']['error_energy'],
                    within_tolerance_pcm=row['voice']['within_tolerance_frames'],within_tolerance_pwm=row['pwm_voice']['within_tolerance_frames'])
            projection.append({**{key:result[key] for key in ('source_ordinal','profile','samples','reset_segments','original_bytes',
                'raw_role_views','distinct_whole_chains','duplicate_role_views_not_remeasured','decisions')},'whole_chains':rows})
            projection[-1]['absent_role_views'] = result['absent_role_views']
        summary = dict(status='PASS',scope='Targeted post-observation common-prefix replay; no production/player adoption',
            profiles=2,source_ordinals=[42],new_seed_fits=0,new_refinements=0,
            reused_old_whole_metric_rows=0,counters=dict(counters),wall_seconds=time.perf_counter()-started)
        save(args.output/'results-private.json',results)
        save(args.output/'results.json',projection)
        save(args.output/'summary.json',summary)
        attempt.update(status='complete',active_chain=None,seconds=summary['wall_seconds'])
        save(args.output/'attempt-private.json',attempt)
        print(json.dumps(summary),flush=True)
        return 0
    except Exception as exc:
        attempt.update(status='failed',exception_type=type(exc).__name__,seconds=time.perf_counter()-started,counters=dict(counters))
        save(args.output/'attempt-private.json',attempt)
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

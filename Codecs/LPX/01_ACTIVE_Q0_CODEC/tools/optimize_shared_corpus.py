"""Bounded, resumable LPX selection over a validated shared-corpus baseline.

All generated audio stays in ignored build directories. Necessary-trigger
thresholds choose offline work only; complete-case PCM/PWM floors decide
acceptance. Missing baseline jobs are counted for a later resume.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import time

import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
import benchmark_shared_corpus as baseline
from benchmark_standards import save
import optimize_speech_v5 as optimizer
from shared_corpus import _ignored_output
from speech_compact import decode_model
from standard_metrics import pwm_duties

PROFILES = (4, 6)
POLICIES = ('necessary', 'all-speech')
SETTINGS = {
    'proposals': ['pre75', 'lower_scales'],
    'refinement_passes': 2, 'refinement_horizon': 320,
    'necessary_trigger': {
        'condition_contains': ['quiet', 'noisy', 'noise'],
        'pcm_activity_failed': True, 'pwm_activity_failed': True,
        'pcm_sse_worse_than_silence': True,
        'finite_pcm_ser_below_db': 3., 'valid_pcm_stoi_below': .6,
        'absolute_rms_gain_above_db': 3.,
    },
    'exact_zero_reference': 'Repair with lower_scales only regardless of kind; already exact outputs retain baseline.',
    'acceptance': 'Whole-case PCM/PWM SSE and available STOI floors; no newly failed PCM/PWM activity; original segment caps.',
}


def environment(base_env, policy):
    if policy not in POLICIES:
        raise ValueError('Unknown shared-corpus selection policy')
    return {**base_env, 'selection': {
        'driver_sha256': baseline.sha(Path(__file__).read_bytes()),
        'optimizer_sha256': baseline.sha(Path(optimizer.__file__).read_bytes()),
        'policy': policy, 'settings': SETTINGS}}


def _finite(value):
    return value is not None and math.isfinite(value)


def choose_work(case, quality, policy, exact_zero=False):
    """Frozen work triggers, independent of selection acceptance floors."""
    if policy not in POLICIES:
        raise ValueError('Unknown shared-corpus selection policy')
    if exact_zero:
        needed = quality['pcm16']['error_energy'] != 0
        return {'run': needed, 'reason': 'exact_silence_repair' if needed else 'exact_silence_already_exact',
                'triggers': ['exact_zero_reference'], 'proposals': ['lower_scales']}
    if case['kind'] != 'speech':
        return {'run': False, 'reason': 'outside_speech_scope', 'triggers': [], 'proposals': []}
    if not quality['pcm16']['error_energy']:
        return {'run': False, 'reason': 'perfect_baseline', 'triggers': [], 'proposals': []}
    reasons = []
    condition = case['condition'].lower()
    if any(word in condition for word in SETTINGS['necessary_trigger']['condition_contains']):
        reasons.append('quiet_or_noisy_condition')
    if not quality['activity_preserved']:reasons.append('pcm_activity_failed')
    if not quality['pwm_activity_preserved']:reasons.append('pwm_activity_failed')
    metrics = quality['pcm16']
    if metrics['error_energy'] > metrics['reference_energy']:reasons.append('pcm_worse_than_silence')
    if _finite(metrics['ser_db']) and metrics['ser_db'] < 3.:reasons.append('pcm_ser_below_3db')
    if _finite(metrics['stoi']) and metrics['stoi'] < .6:reasons.append('pcm_stoi_below_0_6')
    if _finite(quality['rms_gain_db']) and abs(quality['rms_gain_db']) > 3.:reasons.append('rms_gain_above_3db')
    enabled = policy == 'all-speech' or bool(reasons)
    return {'run': enabled, 'reason': ('all_speech_policy' if policy == 'all-speech' else
            'necessary_trigger_met' if enabled else 'necessary_trigger_not_met'),
            'triggers': reasons, 'proposals': list(SETTINGS['proposals']) if enabled else []}


def whole_case_guard(before, after):
    """Joined STOI and activity must pass even when every segment improved."""
    reasons = []
    for domain in ('pcm16', 'pwm8'):
        old, new = before[domain], after[domain]
        if not _finite(new['error_energy']) or new['error_energy'] > old['error_energy']:
            reasons.append(domain+'_sse')
        a, b = old['stoi'], new['stoi']
        if (a is not None and not _finite(a)) or (b is not None and not _finite(b)):
            reasons.append(domain+'_nonfinite_stoi')
        elif a is not None and (b is None or b < a-1e-12):
            reasons.append(domain+'_stoi')
    for key in ('activity_preserved', 'pwm_activity_preserved'):
        if before[key] and not after[key]:reasons.append(key)
    return {'passed': not reasons, 'reasons': reasons}


def quality_status(quality):
    reasons = []
    for domain in ('pcm16', 'pwm8'):
        q = quality[domain]
        if not _finite(q['error_energy']) or q['error_energy'] > q['reference_energy']:
            reasons.append(domain+'_worse_than_silence')
    if not quality['activity_preserved']:reasons.append('pcm_activity_failed')
    if not quality['pwm_activity_preserved']:reasons.append('pwm_activity_failed')
    return {'status': 'no_fit' if reasons else 'passes_waveform_activity_checks', 'reasons': reasons,
            'meaning': 'Waveform/activity checks, not AVR timing or subjective qualification.'}


def _signed(row):
    row = {k: v for k, v in row.items() if k != 'report_sha256'}
    row['report_sha256'] = baseline.sha(baseline.canonical(row))
    return row


def _snapshot(row):
    return {k: row[k] for k in ('status', 'quality', 'file_bytes', 'payload_bytes',
            'file_bps', 'payload_bps', 'pcm16_sha256', 'seconds') if k in row}


def _path(root, relative):
    root = Path(root).resolve(); part = Path(relative); path = (root/part).resolve()
    if part.is_absolute() or not path.is_relative_to(root):
        raise ValueError('Artifact escapes its result tree')
    return path


def _checked(blob, ref, expected_pcm, profile, cap, common, only):
    n = len(ref)
    if (len(blob) > cap or len(blob) < 22 or blob[:5] != b'L4HY\x05' or
            blob[5] not in (profile, profile|128)):
        raise AssertionError('Selected stream violates its original format/cap')
    pcm = common.decode_one_s16(blob, n)
    narrow = only.decode_one_s16(blob, n)
    model = decode_model(blob)
    pwm = common.decode_one(blob, n)
    if (pcm is None or narrow is None or pwm is None or pcm.shape != ref.shape or
            not np.array_equal(pcm, narrow) or not np.array_equal(pcm, model) or
            expected_pcm is not None and not np.array_equal(pcm, expected_pcm) or
            not np.array_equal(pwm, pwm_duties(pcm))):
        raise AssertionError('Selected native/model/compact-only/PWM mismatch')
    return {'blob': bytes(blob), 'pcm': pcm,
            'stream_sha256': baseline.sha(blob), 'pcm16_sha256': baseline.sha(pcm.astype('<i2').tobytes()),
            'pwm_sha256': baseline.sha(pwm.tobytes())}


def _artifacts(dest, case, profile, env, identity, refs, checked, speech):
    dest.mkdir(parents=True, exist_ok=True)
    records = []
    for geometry, ref, data in zip(case['segments'], refs, checked):
        stem = f'segment-{geometry["index"]:03d}'
        (dest/(stem+'.l4hy')).write_bytes(data['blob'])
        sf.write(dest/(stem+'.wav'), data['pcm'], 8000, subtype='PCM_16')
        records.append({'index': geometry['index'], 'start': geometry['start'], 'samples': len(ref),
            'reference_pcm16_sha256': geometry['pcm16_sha256'], 'stream': stem+'.l4hy', 'decoded': stem+'.wav',
            **{k: data[k] for k in ('stream_sha256', 'pcm16_sha256', 'pwm_sha256')},
            'cap_bytes': data['cap'], 'file_bytes': len(data['blob']), 'header_bytes': 22,
            'payload_bytes': len(data['blob'])-22, 'native_model_pcm16_exact': True,
            'native_compact_only_pcm16_exact': True, 'native_pwm_exact': True,
            'quality': baseline.quality(ref, data['pcm'], speech)})
    pcm = np.concatenate([data['pcm'] for data in checked])
    sf.write(dest/'complete.wav', pcm, 8000, subtype='PCM_16')
    size = sum(r['file_bytes'] for r in records); payload = sum(r['payload_bytes'] for r in records)
    return {'id': case['id'], **{k: case[k] for k in ('cohort', 'kind', 'language', 'condition', 'split', 'samples', 'reference_pcm16_sha256')},
            'profile': profile, 'fingerprint': identity, 'environment': env, 'status': 'complete',
            'segments': records, 'file_bytes': size, 'payload_bytes': payload,
            'file_bps': size*64000/len(pcm), 'payload_bps': payload*64000/len(pcm),
            'pcm16_sha256': baseline.sha(pcm.astype('<i2').tobytes()),
            'pwm_sha256': baseline.sha(pwm_duties(pcm).tobytes()), 'segment_resets': len(records)}


def validate_selected(row, case, profile, env, identity, dest, inputs, source, source_hash):
    baseline.validate_saved(row, case, profile, env, identity, dest, inputs)
    if (row.get('baseline_report_sha256') != source['report_sha256'] or
            row.get('baseline_report_file_sha256') != source_hash or row.get('baseline_status') != source['status']):
        raise ValueError('Selected cache refers to a different baseline report')
    if source['status'] != 'complete':
        if row['status'] != source['status'] or row['segments']:
            raise ValueError('Unavailable baseline was replaced by a fabricated output')
        return row
    if row['status'] != 'complete' or row['baseline'] != _snapshot(source):
        raise ValueError('Selected cache lost its complete baseline metrics')
    if not whole_case_guard(source['quality'], row['quality'])['passed']:
        raise ValueError('Cached selected output fails whole-reference quality floors')
    if row['selected_quality_status'] != quality_status(row['quality']):
        raise ValueError('Cached quality-invalid state changed')
    if row['baseline_quality_status'] != quality_status(source['quality']):
        raise ValueError('Cached baseline quality-invalid state changed')
    if row.get('rejected') is not None:
        rejected = row['rejected']
        baseline.validate_saved(rejected, case, profile, env, baseline.sha((identity+':rejected').encode()), dest/'rejected', inputs)
        if whole_case_guard(source['quality'], rejected['quality'])['passed']:
            raise ValueError('Rejected joined proposal unexpectedly passes its saved guard')
    return row


def _select(case, profile, source, source_hash, source_dir, dest, inputs, env, identity, common, only, policy):
    started = time.perf_counter()
    origin = {'baseline_report_sha256': source['report_sha256'], 'baseline_report_file_sha256': source_hash,
              'baseline_status': source['status'], 'baseline': _snapshot(source)}
    if source['status'] != 'complete':
        return _signed({'id': case['id'], 'profile': profile, 'environment': env, 'fingerprint': identity,
            **{k: case[k] for k in ('cohort', 'kind', 'language', 'condition', 'split', 'samples', 'reference_pcm16_sha256')},
            'status': source['status'], 'segments': [],
            **origin, 'skip_reason': 'baseline_'+source['status'], 'baseline_error': source.get('error'),
            'seconds': time.perf_counter()-started})
    reference, refs = baseline.validated_inputs(inputs, case)
    work = choose_work(case, source['quality'], policy, exact_zero=not np.any(reference))
    speech = case['kind'] == 'speech'
    attempted = []; reports = []; originals = []
    for ref, record in zip(refs, source['segments']):
        original = _path(source_dir, record['stream']).read_bytes()
        originals.append(original)
        blob, pcm = original, None
        if work['run']:
            before = time.perf_counter()
            try:
                blob, pcm, report = optimizer.optimize(ref, original, common, record['cap_bytes'],
                    proposals=tuple(work['proposals']), refinement_passes=SETTINGS['refinement_passes'],
                    refinement_horizon=SETTINGS['refinement_horizon'])
            except ValueError as error:
                if str(error) != 'Exact compact baseline does not fit file cap':raise
                report = {'status': 'no_fit', 'retained_baseline': True,
                    'reason': 'An optimizer proposal could not fit the original complete-file cap.',
                    'seconds': time.perf_counter()-before}
        else:
            report = {'status': 'retained_baseline', 'skip_reason': work['reason'], 'trials': 0,
                      'retained_baseline': True, 'seconds': 0.}
        data = _checked(blob, ref, pcm, profile, record['cap_bytes'], common, only)
        data['cap'] = record['cap_bytes']; attempted.append(data); reports.append(report)
    proposal_pcm = np.concatenate([data['pcm'] for data in attempted])
    candidate_quality = baseline.quality(reference, proposal_pcm, speech)
    guard = whole_case_guard(source['quality'], candidate_quality)
    rejected = None
    chosen = attempted
    if not guard['passed']:
        rejected = _artifacts(dest/'rejected', case, profile, env, baseline.sha((identity+':rejected').encode()), refs, attempted, speech)
        rejected.update(quality=candidate_quality, optimization_reports=reports, whole_case_guard=guard)
        rejected = _signed(rejected)
        chosen = []
        for ref, record, blob in zip(refs, source['segments'], originals):
            data = _checked(blob, ref, None, profile, record['cap_bytes'], common, only)
            data['cap'] = record['cap_bytes']; chosen.append(data)
    result = _artifacts(dest, case, profile, env, identity, refs, chosen, speech)
    for record, old, report in zip(result['segments'], source['segments'], reports):
        record['baseline'] = old; record['optimization'] = report
    final_quality = source['quality'] if not guard['passed'] else candidate_quality
    if not whole_case_guard(source['quality'], final_quality)['passed']:
        raise AssertionError('Whole-case rollback did not preserve baseline floors')
    result.update(**origin, quality=final_quality, policy_decision=work,
        baseline_quality_status=quality_status(source['quality']), selected_quality_status=quality_status(final_quality),
        whole_case_guard=guard, whole_case_rollback=not guard['passed'], rejected=rejected,
        retained_baseline=all(data['blob'] == old for data, old in zip(chosen, originals)),
        proposal_changed=any(data['blob'] != old for data, old in zip(attempted, originals)),
        optimization_seconds=sum(r['seconds'] for r in reports), seconds=time.perf_counter()-started)
    return _signed(result)


def run(inputs, baseline_dir, output, shard=0, shards=1, policy='necessary', profiles=PROFILES):
    if not 0 <= shard < shards or not profiles or len(set(profiles)) != len(profiles) or set(profiles)-set(PROFILES):
        raise ValueError('Invalid shard or profile selection')
    inputs, baseline_dir, output = Path(inputs).resolve(), Path(baseline_dir).resolve(), Path(output).resolve()
    for tree in (inputs, baseline_dir):
        if output == tree or output in tree.parents or tree in output.parents:
            raise ValueError('Selected output must not overlap input or baseline trees')
    _ignored_output(output)
    manifest_path = inputs/'manifest.json'; manifest_hash = baseline.sha(manifest_path.read_bytes())
    manifest = baseline.load(manifest_path)
    if manifest.get('schema') != 'lpx-shared-corpus-v1' or not manifest.get('cases'):
        raise ValueError('Expected nonempty prepared shared corpus manifest')
    ids = [case['id'] for case in manifest['cases']]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r'[a-z][a-z0-9_-]*', value) for value in ids):
        raise ValueError('Expected unique safe anonymous case IDs')
    base_env = baseline.environment(); env = environment(base_env, policy)
    progress = {'schema': 'lpx-shared-corpus-selection-progress-v1', 'environment': env,
        'input_manifest_sha256': manifest_hash, 'shard': shard, 'shards': shards,
        'expected_jobs': 0, 'baseline_missing': 0, 'baseline_pending': 0, 'accounted': 0, 'reused': 0,
        'baseline_no_fit': 0, 'baseline_failed': 0, 'complete': 0, 'selected_quality_no_fit': 0,
        'changed': 0, 'whole_case_rollbacks': 0, 'rows': []}
    output.mkdir(parents=True, exist_ok=True)
    progress_path = output/f'progress-shard-{shard}-of-{shards}.json'
    jobs = [(case, profile) for case in manifest['cases'] for profile in profiles]
    with BatchSession('batch', v3_features=24, speech=True, speech_compact=True) as common, \
         BatchSession('batch', v3_features=24, speech=True, speech_compact=True, compact_only=True) as only:
        for index, (case, profile) in enumerate(jobs):
            if index % shards != shard:continue
            progress['expected_jobs'] += 1
            source_dir = baseline_dir/case['id']/str(profile); source_path = source_dir/'report.json'
            if not source_path.is_file():
                progress['baseline_missing'] += 1
                progress['rows'].append({'id': case['id'], 'profile': profile, 'status': 'baseline_pending'})
                save(progress_path, _signed(progress)); continue
            try:
                raw = source_path.read_bytes(); source = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError, FileNotFoundError):
                progress['baseline_pending'] += 1
                progress['rows'].append({'id': case['id'], 'profile': profile,
                    'status': 'baseline_pending', 'reason': 'incomplete_report_read'})
                save(progress_path, _signed(progress)); continue
            source_hash = baseline.sha(raw)
            if source.get('status') not in ('complete', 'no_fit', 'failed'):
                raise ValueError('Unknown baseline completion status')
            baseline.validate_saved(source, case, profile, base_env,
                baseline.sha(baseline.canonical([base_env, case, profile])), source_dir, inputs)
            identity = baseline.sha(baseline.canonical([env, case, profile, source_hash]))
            dest = output/case['id']/str(profile); cache = dest/'report.json'
            if cache.exists():
                row = validate_selected(baseline.load(cache), case, profile, env, identity, dest, inputs, source, source_hash)
                progress['reused'] += 1
            else:
                row = _select(case, profile, source, source_hash, source_dir, dest, inputs, env, identity, common, only, policy)
                dest.mkdir(parents=True, exist_ok=True)
                validate_selected(row, case, profile, env, identity, dest, inputs, source, source_hash)
                save(cache, row)
            progress['accounted'] += 1
            if source['status'] != 'complete':
                progress['baseline_'+source['status']] += 1
            else:
                progress['complete'] += 1
                progress['selected_quality_no_fit'] += row['selected_quality_status']['status'] == 'no_fit'
                progress['changed'] += not row['retained_baseline']
                progress['whole_case_rollbacks'] += row['whole_case_rollback']
            progress['rows'].append({'id': case['id'], 'profile': profile, 'status': row['status'],
                'report_sha256': row['report_sha256'], 'retained_baseline': row.get('retained_baseline'),
                'selected_quality_status': row.get('selected_quality_status')})
            save(progress_path, _signed(progress))
            print(case['id'], profile, row['status'], 'retained', row.get('retained_baseline'), flush=True)
    if (baseline.environment() != base_env or environment(base_env, policy) != env or
            baseline.sha(manifest_path.read_bytes()) != manifest_hash):
        raise ValueError('Source or input manifest changed during selection')
    final = _signed(progress); save(progress_path, final)
    print(json.dumps({k: v for k, v in final.items() if k not in ('environment', 'rows')}, indent=2), flush=True)
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--shard', type=int, default=0); parser.add_argument('--shards', type=int, default=1)
    parser.add_argument('--policy', choices=POLICIES, default='necessary')
    parser.add_argument('--profiles', type=int, choices=PROFILES, nargs='+', default=PROFILES)
    args = vars(parser.parse_args()); args['baseline_dir'] = args.pop('baseline')
    run(**args)


if __name__ == '__main__':main()

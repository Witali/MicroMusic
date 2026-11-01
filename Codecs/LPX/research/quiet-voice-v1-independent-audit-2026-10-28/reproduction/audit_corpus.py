"""Independent saved-output V1 audit; no driver aggregation/selection helpers.

Only numerical metric, pitch diagnostic, objective and decoder primitives are
reused. No encoding, fitting, search, mutation of V1 assets or AVR run occurs.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import importlib
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from admit import Epoch, canonical, sha


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def equal(actual, expected):
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise AssertionError('Independent report keys differ')
        for key in expected:
            equal(actual[key], expected[key])
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise AssertionError('Independent report lengths differ')
        for a, b in zip(actual, expected):
            equal(a, b)
    elif isinstance(expected, bool):
        assert type(actual) is bool and actual == expected
    elif isinstance(expected, (float, int)):
        assert isinstance(actual, (float, int)) and not isinstance(actual, bool)
        assert math.isfinite(actual) and math.isfinite(expected) and abs(actual - expected) <= 1e-12
    else:
        assert actual == expected


def numerical_gate(new, old):
    for domain in ('pcm16', 'pwm8'):
        a, b = new[domain], old[domain]
        if not math.isfinite(a['error_energy']) or a['error_energy'] > b['error_energy']:
            return False
        if b['stoi'] is not None and (a['stoi'] is None or not math.isfinite(a['stoi']) or a['stoi'] < b['stoi'] - 1e-12):
            return False
    return True


def voice_gate(new, old):
    if new['within_tolerance_frames'] < old['within_tolerance_frames'] or new['decoded_collapsed_active_frames'] > old['decoded_collapsed_active_frames']:
        return False
    for field in ('fixed_decoded_period_error_mean', 'relative_spectral_shape_rms_db_mean'):
        before, after = old[field], new[field]
        if before is not None and (after is None or not math.isfinite(after) or after > before + 1e-12):
            return False
    return True


def independent_level(ref, mode, np):
    values = ref.astype(np.int64)
    rms = float(np.std(values.astype(np.float64)))
    peak = int(np.max(np.abs(values)))
    gain = 1
    if mode == 'auto-quiet' and 0 < rms < 256:
        options = [1]
        for power in range(1, 31):
            proposed = 1 << power
            if peak * proposed > 29490:
                break
            options.append(proposed)
        gain = next((value for value in options if rms * value >= 1024), options[-1])
    target = values * gain
    assert int(target.min()) >= -32768 and int(target.max()) <= 32767
    level = dict(policy=mode, gain=gain, gain_db=float(20 * np.log10(gain)),
                 input_ac_rms_pcm16=rms, input_peak_pcm16=peak,
                 target_ac_rms_pcm16=rms * gain, output_level_matches_original=gain == 1,
                 scope='Exact power-of-two input transform; no fitted output gain, clipping or trimming')
    return target.astype(np.int16), level


def main(args):
    began = time.perf_counter()
    epoch = Epoch(args.source_root)
    study, out = args.study.resolve(), args.output.resolve()
    raw_binding = (study / 'binding-private.json').read_bytes()
    binding = json.loads(raw_binding)
    workers = [read(study / 'workers' / ('shard-%d-private.json' % shard)) for shard in (0, 1)]
    if any(worker['status'] != 'complete' for worker in workers):
        raise ValueError('Wait for both completed worker receipts')
    assert binding['core_commit'] == '5b4800f7' and Path(binding['source_root']).resolve() == epoch.root
    assert binding['identity'] == sha(canonical({k: v for k, v in binding.items() if k != 'identity'}))
    driver = epoch.root / 'Codecs/LPX/research/v5-quiet-voice-encoder-2026-10-28/reproduction/run_corpus.py'
    for name, field in ((driver, 'runner'), (driver.parent.parent / 'PROTOCOL.md', 'protocol'), (driver.parent / 'test_protocol.py', 'tests')):
        assert sha(name.read_bytes()) == binding['source'][field]
    for name, digest in binding['source']['core'].items():
        assert sha((epoch.root / name).read_bytes()) == digest
    for name, digest in binding['input_files_sha256'].items():
        assert sha(Path(name).read_bytes()) == digest
    for name, digest in binding['native_libraries_sha256'].items():
        assert sha((study / 'native' / name).read_bytes()) == digest
    manifest = read(binding['manifest_path'])
    assert sha(Path(binding['manifest_path']).read_bytes()) == binding['manifest_sha256']
    assert manifest['records'] == binding['records']
    records = binding['records']
    assert len(records) == 98 and sum(len(r['segments']) for r in records) == 118
    # Build source ordinals independently from first appearance, not driver jobs.
    source_keys = []
    ordinal = {}
    for record in records:
        key = record['private_case_id']
        if key not in ordinal:
            ordinal[key] = len(source_keys)
            source_keys.append(key)
    assert len(source_keys) == 49
    import numpy as np
    import soundfile as sf
    voice = importlib.import_module('voice_character')
    objective_module = importlib.import_module('speech_voice_objective')
    metric = importlib.import_module('refine_speech_compact')
    epoch.verify_imports()
    sessions = [epoch.modules['batch_decoder'].BatchSession('batch', prebuilt=study / 'native' / name) for name in ('common.so', 'v5-only.so')]
    native = [session.__enter__() for session in sessions]
    decoded = {}
    assessed = {}
    contexts = {}
    counts = Counter()
    selections = []
    audit_rows = []
    limits = Counter()
    def decode(blob, n, profile):
        digest = sha(blob)
        if digest not in decoded:
            fields = epoch.modules['speech_compact'].unpack(blob)
            assert fields[:2] == (n, profile)
            # Includes mandatory unplayed tuples/tails via strict unpack above.
            assert len(fields[3]) == 2 * ((n + 319) // 320)
            pcm = epoch.modules['speech_compact'].decode_model(blob)
            assert len(pcm) == n
            pwm = epoch.modules['standard_metrics'].pwm_duties(pcm)
            for receiver in native:
                np.testing.assert_array_equal(receiver.decode_one_s16(blob, n), pcm)
                np.testing.assert_array_equal(receiver.decode_one(blob, n), pwm)
            decoded[digest] = pcm
            counts['unique_native_model_streams'] += 1
            counts['native_output_domain_comparisons'] += 4
            counts['unique_model_samples'] += n
        return decoded[digest]
    def context(target):
        key = sha(target.astype('<i2').tobytes())
        if key not in contexts:
            track = voice.track_pitch(target)
            contexts[key] = (track, objective_module.VoiceObjective(target, track.period))
        return key, contexts[key]
    def assess(target, pcm):
        refkey, (track, objective) = context(target)
        key = (refkey, sha(pcm.astype('<i2').tobytes()))
        if key not in assessed:
            assessed[key] = {'metrics': metric.quality(target, pcm),
                'voice': voice.compare_voice(target, pcm, reference_track=track),
                'pwm_voice': voice.compare_voice(target, epoch.modules['standard_metrics'].pwm_pcm16(pcm), reference_track=track),
                'voice_score': objective(pcm), 'voice_components': objective.components(pcm)}
            assert math.isfinite(assessed[key]['voice_score'])
            counts['unique_full_metric_voice_pairs'] += 1
        return assessed[key]
    def blobs(entry, geometry):
        result = []
        at = 0
        assert len(entry['segments']) == len(geometry)
        for index, (part, (n, profile)) in enumerate(zip(entry['segments'], geometry)):
            data = Path(part['path']).read_bytes()
            assert sha(data) == part['stream_sha256'] and len(data) == part['file_bytes']
            assert part['index'] == index and part['start'] == at and part['samples'] == n and part['profile'] == profile
            decode(data, n, profile)
            at += n
            result.append(data)
        return result
    def flags(value, baseline):
        return {'old_pcm_pwm_floors_passed': numerical_gate(value['metrics'], baseline['metrics']),
                'pcm_voice_proxy_floors_passed': voice_gate(value['voice'], baseline['voice']),
                'pwm_voice_proxy_floors_passed': voice_gate(value['pwm_voice'], baseline['pwm_voice']),
                'voice_objective_nonregression': value['voice_score'] <= baseline['voice_score'] + 1e-12}
    jobs = []
    quiet = set()
    references = {}
    for index, record in enumerate(records):
        reference = record['reference']
        if reference['pcm16_sha256'] not in references:
            ref, rate = sf.read(reference['path'], dtype='int16')
            assert rate == 8000 and ref.ndim == 1 and len(ref) == record['samples']
            assert sha(ref.astype('<i2').tobytes()) == reference['pcm16_sha256']
            references[reference['pcm16_sha256']] = ref
        ref = references[reference['pcm16_sha256']]
        source = ordinal[record['private_case_id']]
        jobs.append({'record_index': index, 'source_ordinal': source, 'mode': 'preserve'})
        if float(np.std(ref.astype(np.float64))) < 256:
            quiet.add(source)
            jobs.append({'record_index': index, 'source_ordinal': source, 'mode': 'auto-quiet'})
    assert len(jobs) == 106 and len(quiet) == 4 and sorted(quiet) == sorted(binding['quiet_source_ordinals'])
    assert jobs == binding['jobs']
    combined = {}
    for shard, worker in enumerate(workers):
        assert worker['binding_sha256'] == sha(raw_binding) and worker['identity'] == binding['identity'] and worker['source'] == binding['source']
        expected_jobs = [job for job in jobs if job['source_ordinal'] % 2 == shard]
        assert len(worker['records']) == len(expected_jobs)
        assert worker['reused_records'] == 0 and worker['executed_records'] == len(expected_jobs)
        assert worker['fresh_encoder_fits'] == worker['recorded_encoder_fits'] == (216 if shard == 0 else 170)
        for job, row in zip(expected_jobs, worker['records']):
            assert all(row[key] == value for key, value in job.items())
            combined[(job['record_index'], job['mode'])] = row
    try:
        for number, job in enumerate(jobs, 1):
            record = records[job['record_index']]
            row = combined[(job['record_index'], job['mode'])]
            mode = job['mode']
            n, profile = record['samples'], record['profile']
            geometry = []
            at = 0
            for index, part in enumerate(record['segments']):
                assert part['index'] == index and part['start'] == at and part['profile'] == profile and type(part['samples']) is int and 1 <= part['samples'] <= 64000
                geometry.append((part['samples'], profile)); at += part['samples']
            assert at == n
            ref = references[record['reference']['pcm16_sha256']]
            target, level = independent_level(ref, mode, np)
            whole_level = dict(level)
            if mode == 'preserve':
                whole_level.pop('scope')
            equal(row['level'], whole_level)
            assert row['original_reference_pcm16_sha256'] == sha(ref.astype('<i2').tobytes())
            assert row['target_reference_pcm16_sha256'] == sha(target.astype('<i2').tobytes())
            assert row['profile'] == profile and row['samples'] == n and row['split'] == record['split'] and row['cohort'] == record['cohort'] and row['id'] == record['id']
            targeted = record['reference']['pcm16_sha256'] == binding['targeted_reference_pcm16_sha256']
            assert row['targeted_not_independent_heldout'] == targeted
            folder = study / 'records' / ('source-%03d' % job['source_ordinal']) / ('profile-%d' % profile) / mode
            identity = sha(canonical([binding['identity'], job]))
            marker = read(folder / 'complete-private.json')
            assert marker['identity'] == row['identity'] == identity
            assert sha((folder / 'record-private.json').read_bytes()) == marker['report_sha256'] and read(folder / 'record-private.json') == row
            artifacts = {p.relative_to(folder).as_posix(): sha(p.read_bytes()) for p in folder.rglob('*.l4hy')}
            assert artifacts == marker['artifacts_sha256']
            attempts = [read(p) for p in sorted((folder / 'attempts').glob('attempt-*-private.json'))]
            assert len(attempts) == 1 and not row['prior_attempts'] and row['prior_incomplete_attempts'] == 0
            assert attempts[0]['identity'] == identity and attempts[0]['status'] == 'complete' and attempts[0]['active_segment'] is None
            expected_fits = len(geometry) * (4 if mode == 'auto-quiet' else 3)
            assert row['completed_fresh_encoder_fits'] == row['all_attempts_completed_v4_native_fit_calls'] == attempts[0]['completed_v4_native_fit_calls'] == expected_fits
            counts[mode + '_fits'] += expected_fits
            original = blobs({'segments': record['segments']}, geometry)
            original_pcm = np.concatenate([decode(blob, *g) for blob, g in zip(original, geometry)])
            assert sha(original_pcm.astype('<i2').tobytes()) == record['baseline_pcm16_sha256']
            assert sha(epoch.modules['standard_metrics'].pwm_duties(original_pcm).tobytes()) == record['baseline_pwm_sha256']
            equal(metric.quality(ref, original_pcm), record['baseline_metrics'])
            assert row['original_level_control']['segments'] == record['segments'] and row['original_level_control']['pcm16_sha256'] == record['baseline_pcm16_sha256'] and row['original_level_control']['pwm_sha256'] == record['baseline_pwm_sha256']
            equal(row['original_level_control']['metrics'], record['baseline_metrics'])
            assert row['whole_original_bytes'] == record['baseline_bytes'] == sum(map(len, original))
            track, objective = context(target)[1]
            equal(row['objective'], objective.describe())
            equal(row['target_pwm_voice'], voice.compare_voice(target, epoch.modules['standard_metrics'].pwm_pcm16(target), reference_track=track))
            captures = defaultdict(list)
            capture_paths = set()
            for item in row['captured_streams']:
                index = item['segment']; data = Path(item['path']).read_bytes()
                assert 0 <= index < len(geometry) and item['capture_order'] == len(captures[index])
                assert sha(data) == item['stream_sha256'] and len(data) == item['file_bytes']
                assert Path(item['path']).resolve().is_relative_to(folder.resolve())
                assert data not in [a[0] for a in captures[index]]
                captures[index].append((data, item['path']))
                capture_paths.add(Path(item['path']).relative_to(folder).as_posix())
                decode(data, *geometry[index]); counts['captured_stream_files'] += 1
            assert capture_paths == set(artifacts)
            local = {'control': [], 'concat-selected': [], 'concat-raw': []}
            at = 0
            assert len(row['segment_searches']) == len(geometry)
            for index, (samples, _) in enumerate(geometry):
                sr = row['segment_searches'][index]; report = sr['report']
                assert sr['index'] == index and sr['start'] == at and sr['samples'] == samples
                assert sr['completed_fresh_encoder_fits'] == (4 if mode == 'auto-quiet' else 3)
                assert len(report['trials']) == 3 and [t['preQ14'] for t in report['trials']] == [0, 8192, 13926]
                assert report['samples'] == samples and report['profile'] == profile and report['complete_byte_cap'] == record['baseline_bytes']
                piece = target[at:at + samples]
                local_ref = ref[at:at + samples]
                equal(report['level'], independent_level(local_ref, mode, np)[1])
                control = captures[index][0][0]
                if mode == 'preserve':
                    assert control == original[index] and report['control_kind'] == 'existing_original_level_v5'
                else:
                    assert report['control_kind'] == 'fresh_legacy_at_declared_target_level' and level['gain'] > 1
                base = assess(piece, decode(control, samples, profile))
                assert report['control_bytes'] == len(control)
                for field, key in (('metrics', 'baseline_metrics'), ('voice', 'baseline_voice'), ('pwm_voice', 'baseline_pwm_voice'), ('voice_score', 'baseline_voice_score')):
                    equal(base[field], report[key])
                equal(report['objective'], context(piece)[1][1].describe())
                ptr, _ = context(piece)[1]
                equal(report['target_pwm_voice'], voice.compare_voice(piece, epoch.modules['standard_metrics'].pwm_pcm16(piece), reference_track=ptr))
                selected = raw = control if len(control) <= record['baseline_bytes'] else None
                selected_score = raw_score = base['voice_score'] if selected is not None else math.inf
                trial_blobs = []
                for trial in report['trials']:
                    options = []
                    for data, path in captures[index]:
                        if int.from_bytes(data[12:14], 'little') != trial['preQ14'] or len(data) != trial['file_bytes']:
                            continue
                        value = assess(piece, decode(data, samples, profile))
                        if value['metrics'] == trial['metrics'] and abs(value['voice_score'] - trial['voice_score']) <= 1e-12:
                            options.append((data, value))
                    assert options, 'A stored trial cannot be mapped to any actual capture'
                    data, value = options[0]
                    trial_blobs.append(data)
                    for field, key in (('metrics', 'metrics'), ('voice', 'voice'), ('pwm_voice', 'pwm_voice'), ('voice_score', 'voice_score'), ('voice_components', 'components')):
                        equal(value[field], trial[key])
                    gate = flags(value, base)
                    assert trial['allow_zero_scale'] is True and trial['fits_complete_cap'] == (len(data) <= record['baseline_bytes'])
                    for key in ('old_pcm_pwm_floors_passed', 'pcm_voice_proxy_floors_passed', 'pwm_voice_proxy_floors_passed'):
                        assert trial[key] == gate[key]
                    assert trial['voice_proxy_floors_passed'] == (gate['pcm_voice_proxy_floors_passed'] and gate['pwm_voice_proxy_floors_passed'])
                    if len(data) <= record['baseline_bytes'] and value['voice_score'] < raw_score:
                        raw, raw_score = data, value['voice_score']
                    if len(data) <= record['baseline_bytes'] and all(gate[k] for k in ('old_pcm_pwm_floors_passed', 'pcm_voice_proxy_floors_passed', 'pwm_voice_proxy_floors_passed')) and value['voice_score'] < selected_score:
                        selected, selected_score = data, value['voice_score']
                assert set(data for data, _ in captures[index]) == set([control, *trial_blobs])
                assert report['selected_bytes'] == (None if selected is None else len(selected)) and report['raw_bytes'] == (None if raw is None else len(raw))
                equal(report['selected_voice_score'], None if selected is None else selected_score)
                equal(report['raw_voice_score'], None if raw is None else raw_score)
                assert report['selected_differs_from_control'] == (selected is not None and selected != control)
                assert report['raw_quality_adopted'] == (raw is not None and raw == selected)
                if selected is None:
                    assert report['selected'] is None
                else:
                    s = assess(piece, decode(selected, samples, profile))
                    equal(report['selected'], {key: s[key] for key in ('metrics', 'voice', 'pwm_voice')})
                local['control'].append(control); local['concat-selected'].append(selected); local['concat-raw'].append(raw)
                at += samples
            derived = []
            assert len(row['chains']) == 3
            for role, entry in zip(('control', 'concat-selected', 'concat-raw'), row['chains']):
                chain = local[role]
                if any(blob is None for blob in chain):
                    assert entry is None; derived.append(None); continue
                assert entry is not None and entry['role'] == role
                assert blobs(entry, geometry) == chain
                pcm = np.concatenate([decode(blob, *g) for blob, g in zip(chain, geometry)])
                value = assess(target, pcm)
                assert entry['samples'] == n and entry['stream_bytes'] == sum(map(len, chain))
                assert entry['pcm16_sha256'] == sha(pcm.astype('<i2').tobytes()) and entry['pwm_sha256'] == sha(epoch.modules['standard_metrics'].pwm_duties(pcm).tobytes())
                for key in value:
                    equal(value[key], entry[key])
                gate = {k: True for k in ('old_pcm_pwm_floors_passed', 'pcm_voice_proxy_floors_passed', 'pwm_voice_proxy_floors_passed', 'voice_objective_nonregression')} if role == 'control' else flags(value, derived[0])
                assert all(entry[key] == passed for key, passed in gate.items())
                assert entry['automatic_quality_eligible'] == all(gate.values())
                derived.append({**value, **gate, 'automatic_quality_eligible': all(gate.values()), 'role': role, 'stream_bytes': entry['stream_bytes'], 'streams': chain, 'entry': entry})
                counts[mode + '_whole_chain_entries'] += 1
                limits[mode + '_stoi_unassessed_domains'] += sum(value['metrics'][d]['stoi'] is None for d in ('pcm16', 'pwm8'))
                limits[mode + '_pcm_pitch_unassessed_chains'] += value['voice']['reference_period_frames'] == 0
                limits[mode + '_pwm_pitch_unassessed_chains'] += value['pwm_voice']['reference_period_frames'] == 0
            expected_counter = 1 + sum(e is not None for e in row['chains'])
            assert row['validation'] == {'native_output_domain_comparisons': 4 * len(geometry) * expected_counter, 'model_samples': n * expected_counter}
            assert len(row['budgets']) == 3
            for percent, reported in zip((100, 95, 90), row['budgets']):
                cap = record['baseline_bytes'] * percent // 100
                fitting = [entry for entry in derived if entry is not None and entry['stream_bytes'] <= cap]
                eligible = [entry for entry in fitting if entry['automatic_quality_eligible']]
                rank = {'control': 0, 'concat-selected': 1, 'concat-raw': 2}
                order = lambda e: (e['voice_score'], e['stream_bytes'], rank[e['role']])
                selected = sorted(eligible, key=order)[0] if eligible else None
                raw = sorted(fitting, key=order)[0] if fitting else None
                expected_budget = {'percent': percent, 'cap': cap, 'selected': None if selected is None else selected['role'],
                    'raw_tradeoff': None if raw is None else raw['role'], 'fitting_chain_count': len(fitting), 'eligible_chain_count': len(eligible),
                    'distinct_fitting_chain_count': len({tuple(sha(b) for b in e['streams']) for e in fitting}), 'no_fit': not fitting, 'no_automatic_admission': not eligible}
                assert reported == expected_budget
                if selected is not None:
                    changed_original = selected['streams'] != original
                    changed_control = selected['streams'] != local['control']
                    selections.append({'record_index': job['record_index'], 'source_ordinal': job['source_ordinal'], 'profile': profile, 'mode': mode,
                        'percent': percent, 'cap': cap, 'split': record['split'], 'cohort': record['cohort'], 'targeted': targeted,
                        'role': selected['role'], 'changed_from_original_level_control': changed_original,
                        'changed_from_declared_control': changed_control, 'level': level, 'candidate': selected['entry'],
                        'original': {'samples': n, 'profile': profile, 'segments': record['segments'], 'file_bytes': record['baseline_bytes']}})
                audit_rows.append({'mode': mode, 'percent': percent, 'targeted': targeted, 'selected': selected is not None,
                    'selected_changed_from_original': selected is not None and selected['streams'] != original,
                    'selected_changed_from_declared_control': selected is not None and selected['streams'] != local['control'],
                    'raw': raw is not None, 'no_fit': not fitting, 'automatic_no_admission': not eligible})
            counts[mode + '_groups'] += 1
            print(json.dumps({'audit_groups': number, 'total': len(jobs), 'mode': mode, 'unique_streams': counts['unique_native_model_streams']}), flush=True)
        assert counts['preserve_groups'] == 98 and counts['auto-quiet_groups'] == 8
        assert counts['preserve_fits'] == 354 and counts['auto-quiet_fits'] == 32
        assert sum(row['targeted_not_independent_heldout'] for row in combined.values() if row['mode'] == 'preserve') == 2
        for name, digest in binding['source']['core'].items():
            assert sha((epoch.root / name).read_bytes()) == digest
        assert (study / 'binding-private.json').read_bytes() == raw_binding
        for name, digest in binding['input_files_sha256'].items():
            assert sha(Path(name).read_bytes()) == digest
        groups = []
        for mode in ('preserve', 'auto-quiet'):
            for percent in (100, 95, 90):
                for targeted in (False, True):
                    subset = [r for r in audit_rows if r['mode'] == mode and r['percent'] == percent and r['targeted'] == targeted]
                    groups.append({'mode': mode, 'percent': percent, 'targeted_not_independent_heldout': targeted,
                        'groups': len(subset), **{key: sum(row[key] for row in subset) for key in ('selected', 'selected_changed_from_original', 'selected_changed_from_declared_control', 'raw', 'no_fit', 'automatic_no_admission')}})
        result = {'schema': 'lpx-quiet-voice-independent-corpus-audit-v1', 'status': 'passed', 'source_commit': binding['core_commit'],
            'groups': 106, 'preserve_groups': 98, 'auto_declared_target_groups': 8, 'original_sources': 49, 'original_reset_segments': 118,
            'observed_fresh_fits': 386, 'preserve_fits': 354, 'auto_fits': 32, 'prior_or_hidden_attempts': 0,
            'counts': dict(counts), 'unassessed_diagnostic_counts': dict(limits), 'budget_groups': groups,
            'all_original_full_pcm_pwm_and_reference_bindings_verified': True,
            'all_captured_streams_native_common_v5_model_pcm_pwm_verified': True,
            'all_local_trials_and_whole_chain_metrics_voice_pwm_objective_components_verified': True,
            'all_318_whole_caps_and_priority_choices_independently_derived': True,
            'no_driver_aggregation_or_selection_helpers_called': True,
            'nullable_scope': 'Known baseline to null/nonfinite fails. Unassessed baseline leaves that constraint unset and is counted separately, never reported as measured pitch success. Control self-eligibility is rollback only.',
            'scope': 'Separate preserve/auto and targeted cohorts. Finite three-chain pool; no fits, re-encoding, new search or audibility/default claim.',
            'audit_source_sha256': sha(Path(__file__).read_bytes()), 'seconds': time.perf_counter() - began}
        epoch.save(out / 'audit-private.json', {'schema': 'lpx-quiet-voice-independent-corpus-audit-private-v1',
            'status': 'passed', 'binding_sha256': sha(raw_binding), 'selections': selections, 'rows': audit_rows, 'summary': result})
        epoch.save(out / 'audit.json', result)
        print(json.dumps({'status': 'passed', 'groups': 106, 'unique_streams': counts['unique_native_model_streams'], 'seconds': result['seconds']}), flush=True)
    finally:
        for session in sessions:
            session.__exit__()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())

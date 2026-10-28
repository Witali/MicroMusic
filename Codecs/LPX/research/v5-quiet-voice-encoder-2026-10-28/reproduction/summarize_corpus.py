"""Project V1 private corpus receipts into anonymous numeric evidence, without fits."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def write(path, value):
    if path.is_symlink() or path.exists() and path.stat().st_nlink > 1:
        raise ValueError('Anonymous output must not alias another file')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, indent=2, allow_nan=False).encode() + b'\n')


def stream_key(entry):
    return tuple(s['stream_sha256'] for s in entry['segments'])


def group_id(record):
    return 'source-%03d-p%d-%s' % (record['source_ordinal'], record['profile'], record['mode'])


def projected_group(record):
    if record['split'] not in ('tuning', 'evaluation', 'additional') or record['cohort'] not in (
            'speech', 'regression', 'independent', 'phrases'):
        raise ValueError('Unexpected private cohort label; do not copy it into public output')
    original = tuple(s['stream_sha256'] for s in record['original_level_control']['segments'])
    control = stream_key(record['chains'][0])
    chains = []
    for entry in record['chains']:
        if entry is None:
            chains.append(None)
            continue
        # Explicit whitelist: no paths, stream/media/PCM hashes or original IDs.
        keep = ('role', 'samples', 'stream_bytes', 'metrics', 'voice', 'pwm_voice',
                'voice_score', 'voice_components', 'old_pcm_pwm_floors_passed',
                'pcm_voice_proxy_floors_passed', 'pwm_voice_proxy_floors_passed',
                'voice_objective_nonregression', 'automatic_quality_eligible')
        public = {key: entry[key] for key in keep}
        public.update(reset_sample_counts=[s['samples'] for s in entry['segments']],
                      differs_from_original_level_streams=stream_key(entry) != original,
                      differs_from_matching_level_control=stream_key(entry) != control,
                      metric_reference='original_level_source' if record['mode'] == 'preserve' else 'declared_amplified_target')
        chains.append(public)
    searches = []
    for search in record['segment_searches']:
        report = search['report']
        searches.append({'index': search['index'], 'start': search['start'], 'samples': search['samples'],
                        'completed_fresh_encoder_fits': search['completed_fresh_encoder_fits'],
                        'control_kind': report['control_kind'], 'control_bytes': report['control_bytes'],
                        'frontend_wall_seconds': report['seconds'],
                        'generation_byte_cap': report['complete_byte_cap'],
                        'selected_bytes': report['selected_bytes'], 'raw_bytes': report['raw_bytes'],
                        'trials': [{key: trial[key] for key in (
                            'preQ14', 'allow_zero_scale', 'file_bytes', 'fits_complete_cap',
                            'old_pcm_pwm_floors_passed', 'pcm_voice_proxy_floors_passed',
                            'pwm_voice_proxy_floors_passed', 'voice_proxy_floors_passed',
                            'voice_score', 'encoder_seconds')} for trial in report['trials']],
                        'scope': 'Local generation only; complete-chain gates and caps decide admission.'})
    by_role = {entry['role']: entry for entry in record['chains'] if entry is not None}
    budgets = []
    for budget in record['budgets']:
        selected = by_role.get(budget['selected'])
        raw = by_role.get(budget['raw_tradeoff'])
        budgets.append({**budget, 'raw_quality_adopted': raw is not None and selected is not None
                        and stream_key(raw) == stream_key(selected)})
    return {'group': group_id(record), 'source_ordinal': record['source_ordinal'],
            'profile': record['profile'], 'mode': record['mode'], 'samples': record['samples'],
            'split': record['split'], 'cohort': record['cohort'],
            'targeted_not_independent_heldout': record['targeted_not_independent_heldout'],
            'declared_level': record['level'], 'whole_original_bytes': record['whole_original_bytes'],
            'original_reset_sample_counts': [s['samples'] for s in record['original_level_control']['segments']],
            'target_pwm_voice': record['target_pwm_voice'], 'objective': record['objective'],
            'completed_fresh_encoder_fits': record['completed_fresh_encoder_fits'],
            'prior_incomplete_attempts': record['prior_incomplete_attempts'],
            'all_attempts_completed_v4_native_fit_calls': record['all_attempts_completed_v4_native_fit_calls'],
            'complete_chain_validation': record['validation'],
            'chains': chains, 'budgets': budgets, 'segment_searches': searches}


def chosen(record, percent=100):
    budget = next(row for row in record['budgets'] if row['percent'] == percent)
    if budget['selected'] is None:
        return None
    return next(entry for entry in record['chains'] if entry is not None and entry['role'] == budget['selected'])


def voice_coverage(entries, domain):
    reports = [entry[domain] for entry in entries if entry is not None]
    observed = [r for r in reports if r['reference_period_frames'] > 0]
    return {'reported_chain_groups': len(reports),
            'source_period_unassessed_groups': sum(r['reference_period_frames'] == 0 for r in reports),
            'observed_source_but_no_paired_output_period_groups': sum(r['paired_period_frames'] == 0 for r in observed),
            'null_paired_cents_groups': sum(r['absolute_cents_median_paired'] is None for r in reports),
            'reference_period_frames': sum(r['reference_period_frames'] for r in reports),
            'paired_period_frames': sum(r['paired_period_frames'] for r in reports),
            'within_tolerance_frames': sum(r['within_tolerance_frames'] for r in reports),
            'missing_decoded_period_frames': sum(r['missing_decoded_period_frames'] for r in reports),
            'decoded_collapsed_active_frames': sum(r['decoded_collapsed_active_frames'] for r in reports),
            'profile_group_window_counts': True,
            'status_counts': dict(Counter(r['pitch_status'] for r in reports)),
            'scope': 'Overlapping diagnostic windows, not independent samples or validated true F0; unassessed is not success.'}


def cohort_summary(records):
    budgets = {}
    for percent in (100, 95, 90):
        selected = [chosen(r, percent) for r in records]
        rows = [next(b for b in r['budgets'] if b['percent'] == percent) for r in records]
        budgets[str(percent)] = {
            'groups': len(records), 'automatic_admissions': sum(e is not None for e in selected),
            'finite_pool_byte_fit_groups': sum(b['raw_tradeoff'] is not None for b in rows),
            'tradeoff_only_groups': sum(b['selected'] is None and b['raw_tradeoff'] is not None for b in rows),
            'no_byte_fit_groups': sum(b['raw_tradeoff'] is None for b in rows),
            'selected_null_groups': sum(e is None for e in selected),
            'selected_changes_from_original_level_streams': sum(
                e is not None and stream_key(e) != tuple(s['stream_sha256'] for s in r['original_level_control']['segments'])
                for e, r in zip(selected, records)),
            'selected_changes_from_matching_level_control': sum(
                e is not None and stream_key(e) != stream_key(r['chains'][0])
                for e, r in zip(selected, records)),
            'selected_stream_bytes_total': sum(e['stream_bytes'] for e in selected if e is not None),
            'selected_role_counts': dict(Counter('null' if e is None else e['role'] for e in selected)),
            'selected_pcm_voice': voice_coverage(selected, 'voice'),
            'selected_pwm_voice': voice_coverage(selected, 'pwm_voice')}
    controls = [r['chains'][0] for r in records]
    return {'mode_groups': len(records), 'distinct_original_sources': len({r['source_ordinal'] for r in records}),
            'split_groups': dict(Counter(r['split'] for r in records)),
            'cohort_groups': dict(Counter(r['cohort'] for r in records)),
            'targeted_mode_groups': sum(r['targeted_not_independent_heldout'] for r in records),
            'original_segments': sum(len(r['original_level_control']['segments']) for r in records),
            'profile_group_samples': sum(r['samples'] for r in records),
            'completed_fresh_encoder_fits': sum(r['completed_fresh_encoder_fits'] for r in records),
            'prior_incomplete_attempts': sum(r['prior_incomplete_attempts'] for r in records),
            'all_attempts_completed_v4_native_fit_calls': sum(r['all_attempts_completed_v4_native_fit_calls'] for r in records),
            'whole_chain_native_domain_comparisons': sum(r['validation']['native_output_domain_comparisons'] for r in records),
            'original_stream_bytes_total': sum(r['whole_original_bytes'] for r in records),
            'matching_level_control_stream_bytes_total': sum(e['stream_bytes'] for e in controls),
            'control_pcm_voice': voice_coverage(controls, 'voice'),
            'control_pwm_voice': voice_coverage(controls, 'pwm_voice'), 'budgets': budgets,
            'sse_aggregation': 'Not reported across target levels; per-group metrics use their own matching declared target.'}


def project(study, output, audit_path=None, context_path=None):
    inputs = [study / 'binding-private.json', *[study / 'workers' / ('shard-%d-private.json' % s) for s in (0, 1)]]
    contents = [p.read_bytes() for p in inputs]
    binding, *workers = map(json.loads, contents)
    expected_identity = sha(canonical({k: v for k, v in binding.items() if k != 'identity'}))
    if binding['identity'] != expected_identity:
        raise ValueError('Prepared study binding changed')
    if any(w['status'] != 'complete' or w['identity'] != binding['identity'] or
           w['binding_sha256'] != sha(contents[0]) or w['source'] != binding['source'] for w in workers):
        raise ValueError('Study workers are incomplete or use different epochs')
    rows = [r for w in workers for r in w['records']]
    keys = [(r['record_index'], r['source_ordinal'], r['mode']) for r in rows]
    expected = [(j['record_index'], j['source_ordinal'], j['mode']) for j in binding['jobs']]
    if len(keys) != len(set(keys)) or set(keys) != set(expected):
        raise ValueError('Completed worker scope differs from the prepared study')
    preserve = [r for r in rows if r['mode'] == 'preserve']
    auto = [r for r in rows if r['mode'] == 'auto-quiet']
    if (len(preserve) != 98 or len(auto) != 8 or sum(r['completed_fresh_encoder_fits'] for r in preserve) != 354 or
            sum(r['completed_fresh_encoder_fits'] for r in auto) != 32):
        raise ValueError('Expected all98 preserve/8 auto groups and354+32 fits')
    quiet = set(binding['quiet_source_ordinals'])
    active = [r for r in preserve if r['source_ordinal'] not in quiet] + auto
    if len(active) != 98 or len({r['record_index'] for r in active}) != 98:
        raise ValueError('Active-policy view must replace, not add, the eight quiet groups')
    audit = context = None
    if audit_path is not None:
        data = audit_path.read_bytes()
        inputs.append(audit_path)
        contents.append(data)
        audit = json.loads(data)
        if audit.get('schema') != 'lpx-quiet-voice-independent-corpus-audit-v1' or audit.get('status') != 'passed':
            raise ValueError('Final evidence requires the completed independent corpus audit')
        required = {'groups': 106, 'preserve_groups': 98, 'auto_declared_target_groups': 8,
                    'original_sources': 49, 'original_reset_segments': 118, 'observed_fresh_fits': 386,
                    'preserve_fits': 354, 'auto_fits': 32, 'prior_or_hidden_attempts': 0}
        if any(audit[k] != value for k, value in required.items()):
            raise ValueError('Independent audit scope differs from projected study')
        if not str(audit['source_commit']).startswith(binding['core_commit']) or any(audit[k] is not True for k in (
                'all_original_full_pcm_pwm_and_reference_bindings_verified',
                'all_captured_streams_native_common_v5_model_pcm_pwm_verified',
                'all_local_trials_and_whole_chain_metrics_voice_pwm_objective_components_verified',
                'all_318_whole_caps_and_priority_choices_independently_derived',
                'no_driver_aggregation_or_selection_helpers_called')):
            raise ValueError('Independent audit source or proof flags do not match')
        context_path = audit_path.with_name('context-audit.json') if context_path is None else context_path
        data = context_path.read_bytes()
        inputs.append(context_path)
        contents.append(data)
        context = json.loads(data)
        if (context.get('schema') != 'lpx-quiet-voice-independent-context-audit-v1' or
                context.get('status') != 'passed' or
                context['sources_with_exactly_both_profiles_and_same_reference'] != 49 or
                context['whole_single_reset_auto_source_count'] != 4 or
                context['targeted_sources'] != 1 or context['targeted_profiles'] != 2 or
                context['prepared_python_packages_compiler_and_threads_match'] is not True or
                context['exact_record_marker_and_attempt_inventory'] != 106 or
                context['total_all_attempts_observed_native_v4_fits'] != 386 or
                context['unexpected_job_folders_or_attempts_or_worker_receipts'] != 0):
            raise ValueError('Independent runtime/attempt context audit did not pass full scope')
        if len(audit['budget_groups']) != 12 or len({(r['mode'], r['percent'], r['targeted_not_independent_heldout'])
                                                   for r in audit['budget_groups']}) != 12:
            raise ValueError('Independent cap/cohort inventory is incomplete')
        for checked in audit['budget_groups']:
            cohort = [r for r in rows if r['mode'] == checked['mode'] and
                      r['targeted_not_independent_heldout'] == checked['targeted_not_independent_heldout']]
            summary = cohort_summary(cohort)['budgets'][str(checked['percent'])]
            match = {'groups': len(cohort), 'selected': summary['automatic_admissions'],
                     'selected_changed_from_original': summary['selected_changes_from_original_level_streams'],
                     'selected_changed_from_declared_control': summary['selected_changes_from_matching_level_control'],
                     'raw': summary['finite_pool_byte_fit_groups'], 'no_fit': summary['no_byte_fit_groups'],
                     'automatic_no_admission': summary['selected_null_groups']}
            if any(checked[key] != value for key, value in match.items()):
                raise ValueError('Projection disagrees with independently derived cap/cohort counts')
    public_groups = [projected_group(r) for r in sorted(rows, key=lambda r: (r['record_index'], r['mode']))]
    fitting_sources = binding['source']
    runtime = binding['environment']
    source_runtime = {
        'schema': 'lpx-quiet-voice-corpus-public-source-runtime-v1', 'core_commit': binding['core_commit'],
        'production_decoder_commit': '5c7e0592', 'source_sha256': fitting_sources,
        'projection_source_sha256': sha(Path(__file__).read_bytes()),
        'runtime': {k: runtime[k] for k in ('python', 'platform', 'packages', 'compiler_file_sha256', 'threads')},
        'native_libraries_sha256': binding['native_libraries_sha256'],
        'native_library_role': 'Generic common/v5-only C++ receivers, built without audio or recording data.',
        'omitted_private_fields': ['source_root', 'input/recording paths and fingerprints',
                                   'private study identity', 'raw local compiler wrapper/version line'],
        'independent_audit_status': 'pending' if audit is None else 'passed',
        'auditor_source_sha256': None if audit is None else {
            'corpus': audit['audit_source_sha256'], 'context': context['audit_source_sha256']}}
    summary = {'schema': 'lpx-quiet-voice-corpus-public-summary-v1',
               'status': 'pending_independent_audit' if audit is None else 'independently_audited',
               'stage': 'V1 bounded first stage/control; V2 targets remaining rasp and unified search.',
               'original_sources': 49, 'original_profile_groups': 98, 'original_reset_segments': 118,
               'original_unique_samples': sum(r['samples'] for r in preserve if r['profile'] == 4),
               'original_unique_seconds': sum(r['samples'] for r in preserve if r['profile'] == 4) / 8000,
               'actual_mode_groups': 106, 'actual_fresh_encoder_fits': sum(w['fresh_encoder_fits'] for w in workers),
               'recorded_encoder_fits': sum(w['recorded_encoder_fits'] for w in workers),
               'reused_records': sum(w['reused_records'] for w in workers),
               'worker_timing': [{'shard': w['shard'], 'wall_seconds': w['wall_seconds'],
                                  'executed_mode_groups': w['executed_records'], 'fresh_encoder_fits': w['fresh_encoder_fits']}
                                 for w in workers],
               'timing_scope': 'Worker wall after initial source/input startup guards; includes encoding, verification, metrics and per-record guards. Concurrent durations must not be added as elapsed time. No matched search-only CPU comparison was measured.',
               'process_cpu_time_measured': False,
               'preserve_original_level': cohort_summary(preserve),
               'auto_declared_target_level': cohort_summary(auto),
               'active_policy': cohort_summary(active),
               'active_policy_composition': {'preserve_groups': 90, 'auto_groups': 8,
                                             'distinct_original_sources': 49,
                                             'gain_one_auto_groups_reused_from_preserve': 90,
                                             'extra_fits_for_reuse': 0},
               'interpretation': ['100% preserve rollback does not prove voice preservation.',
                                  'Auto metrics compare each amplified target with its fresh same-target legacy control.',
                                  'Do not aggregate SSE across original and amplified levels as a quality gain.',
                                  'Targeted source has two profiles; it is not independent held-out evidence.',
                                  'Missing reference pitch stays unassessed; missing decoded pitch is not a success.',
                                  'Finite-pool100/95/90 selection adds no cap-specific fitting or encoding-impossibility proof.',
                                  'Stream-byte totals sum benchmark alternatives, not one affordable firmware image.'],
               'active_policy_scope': 'Derived selection of90 existing preserve rows plus8 existing declared-target auto rows; no extra fits or independent rerun. The row-carried362 fits are part of the386 actual study fits.',
               'independent_audit_status': 'pending' if audit is None else 'passed',
               'independent_audit': None if audit is None else {
                   'status': 'passed', 'groups': audit['groups'], 'fits': audit['observed_fresh_fits'],
                   'counts': audit['counts'], 'unassessed_diagnostic_contexts': audit['unassessed_diagnostic_counts'],
                   'seconds': audit['seconds'], 'source_commit': audit['source_commit'],
                   'corpus_auditor_source_sha256': audit['audit_source_sha256'],
                   'context_auditor_source_sha256': context['audit_source_sha256'],
                   'scope': 'Separate fresh saved-output audit; no fitter aggregation/selection helpers called. Rechecks existing signals, not extra fitting.'}}
    for path, original in zip(inputs, contents):
        if path.read_bytes() != original:
            raise ValueError('Study/audit receipts changed during projection')
    write(output / 'summary.json', summary)
    write(output / 'groups.json', {'schema': 'lpx-quiet-voice-corpus-public-groups-v1', 'groups': public_groups,
                                  'active_policy_group_ids': [group_id(r) for r in sorted(active, key=lambda r: r['record_index'])],
                                  'scope': 'Anonymous numeric role/cap results. Targets have declared level policy; no media, source identities or fingerprints.'})
    write(output / 'source-runtime.json', source_runtime)
    print(json.dumps({'mode_groups': len(rows), 'fresh_encoder_fits': summary['actual_fresh_encoder_fits'],
                      'independent_audit_status': summary['independent_audit_status']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--audit', type=Path)
    parser.add_argument('--context-audit', type=Path)
    args = parser.parse_args()
    project(args.study.resolve(), args.output.resolve(), None if args.audit is None else args.audit.resolve(),
            None if args.context_audit is None else args.context_audit.resolve())

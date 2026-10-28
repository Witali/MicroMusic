"""Export anonymous numeric results from the audited frozen combined study.

Run from the repository root with the project tools on PYTHONPATH. Inputs and
all audio-derived fingerprints stay in ignored build storage; only aggregate
numbers, public ordinals and source/runtime hashes are exported.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bounds(values):
    return ({'count': len(values), 'min': min(values), 'mean': sum(values) / len(values),
             'max': max(values)} if values else {'count': 0, 'min': None, 'mean': None, 'max': None})


def comparison(pairs):
    result = {'groups': len(pairs)}
    for domain in ('pcm16', 'pwm8'):
        before = sum(a[domain]['error_energy'] for a, _ in pairs)
        after = sum(b[domain]['error_energy'] for _, b in pairs)
        stoi = [b[domain]['stoi'] - a[domain]['stoi'] for a, b in pairs
                if a[domain]['stoi'] is not None and b[domain]['stoi'] is not None]
        ser = [b[domain]['ser_db'] - a[domain]['ser_db'] for a, b in pairs
               if a[domain]['ser_status'] == b[domain]['ser_status'] == 'finite']
        result[domain] = {
            'before_error_energy': before if pairs else None,
            'after_error_energy': after if pairs else None,
            'aggregate_error_reduction_percent': 100 * (before - after) / before if before else None,
            'aggregate_ser_gain_db': 10 * math.log10(before / after) if before and after else None,
            'per_record_stoi_delta': bounds(stoi), 'per_record_ser_gain_db': bounds(ser),
        }
    return result


def main(study: Path, output: Path):
    study = study.resolve()
    root = Path.cwd()
    assert study.is_relative_to((root / 'build').resolve())
    workers = [json.loads((study / 'workers' / f'{mode}-shard-{shard}.json').read_text())
               for mode in ('sse', 'perceptual') for shard in (0, 1)]
    audit = json.loads((study / 'audit-anonymous.json').read_text())
    assert audit['status'] == 'complete' and all(w['status'] == 'complete' for w in workers)
    assert all(w['source'] == audit['source'] and w['settings'] == audit['settings']
               and w['runtime'] == workers[0]['runtime'] for w in workers)
    reproduction = Path(__file__).resolve().parent
    assert sha((reproduction / 'audit_combined.py').read_bytes()) == audit['auditor_source_sha256']
    assert sha((reproduction / 'run_combined.py').read_bytes()) == audit['source']['runner']
    assert sha((reproduction / 'test_protocol.py').read_bytes()) == audit['source']['protocol_tests']
    assert sha((reproduction.parent / 'PROTOCOL.md').read_bytes()) == audit['source']['protocol']
    audit_by = {(r['mode'], r['id'], r['percent'], r['role']): r for r in audit['rows']}
    inputs = []
    for path, digest in workers[0]['input_files_sha256'].items():
        data = Path(path).read_bytes()
        assert sha(data) == digest
        inputs.append(json.loads(data))
    manifest = next(d for d in inputs if d.get('schema') == 'lpx-v5-encoder-quality-study-v1')
    old = {r['id']: r for d in inputs if d.get('schema') == 'lpx-v5-encoder-quality-run-v1'
           for r in d['records']}
    assert len(manifest['records']) == len(old) == 98
    reference_samples = {}
    for r in manifest['records']:
        reference_samples[r['reference']['pcm16_sha256']] = r['samples']

    def signature(entry):
        return tuple(s['stream_sha256'] for s in entry['segments'])

    def budget_summary(records, mode, percent):
        pairs = [(r, next(b for b in r['budgets'] if b['percent'] == percent)) for r in records]
        selected = [(r, b) for r, b in pairs if b['selected'] is not None]
        raw = [(r, b) for r, b in pairs if b['tradeoff'] is not None]
        controls = [(r, b) for r, b in selected if b['accepted_control_present']]
        novelty = [audit_by[mode, r['id'], percent, 'selected'] for r, _ in selected]
        changed = []
        for r, b in controls:
            control = next(v for v in old[r['id']]['budgets'] if v['percent'] == percent)['selected']
            if signature(control) != signature(b['selected']):
                delta = comparison([(control['metrics'], b['selected']['metrics'])])
                changed.append({'id': r['id'], 'profile': r['profile'], 'split': r['split'],
                                'control_stream_bytes': control['stream_bytes'],
                                'selected_stream_bytes': b['selected']['stream_bytes'],
                                'selected_minus_control_stream_bytes': b['selected']['stream_bytes'] - control['stream_bytes'],
                                'new_segment_count': audit_by[mode, r['id'], percent, 'selected']['new_segments'],
                                'metrics_vs_control': {
                                    domain: {'error_reduction_percent': delta[domain]['aggregate_error_reduction_percent'],
                                             'stoi_delta': delta[domain]['per_record_stoi_delta']['mean']}
                                    for domain in ('pcm16', 'pwm8')}})
        return {
            'percent': percent, 'profile_groups': len(pairs),
            'complete_cap_bytes_sum': sum(b['cap'] for _, b in pairs),
            'byte_feasible_tradeoff_groups': len(raw),
            'finite_pool_no_byte_fit_groups': len(pairs) - len(raw),
            'automatic_selected_groups': len(selected),
            'old_accepted_control_groups': sum(b['accepted_control_present'] for _, b in pairs),
            'new_automatic_admissions': sum(not b['accepted_control_present'] for _, b in selected),
            'byte_feasible_but_no_automatic_selection': len(raw) - len(selected),
            'selected_stream_bytes_sum': sum(b['selected']['stream_bytes'] for _, b in selected),
            'accepted_control_stream_bytes_sum_on_selected': sum(b['accepted_control_bytes'] for _, b in controls),
            'selected_minus_accepted_control_stream_bytes_on_common_groups': sum(
                b['selected']['stream_bytes'] - b['accepted_control_bytes'] for _, b in controls),
            'smaller_selected_vs_accepted_control_groups': sum(
                b['selected']['stream_bytes'] < b['accepted_control_bytes'] for _, b in controls),
            'selected_with_new_segment_groups': sum(r['new_segments'] > 0 for r in novelty),
            'selected_whole_chain_preexisting_groups': sum(r['whole_chain_preexisting'] for r in novelty),
            'selected_vs_original': comparison([(r['baseline_metrics'], b['selected']['metrics']) for r, b in selected]),
            'selected_vs_accepted_control': comparison([(b['accepted_control_metrics'], b['selected']['metrics']) for _, b in controls]),
            'raw_vs_original': comparison([(r['baseline_metrics'], b['tradeoff']['metrics']) for r, b in raw]),
            'raw_original_floors_passed_groups': sum(b['tradeoff']['original_floors_passed'] for _, b in raw),
            'raw_automatic_floors_passed_groups': sum(b['tradeoff']['automatic_floors_passed'] for _, b in raw),
            'changed_selected_vs_accepted_control_groups': len(changed),
            'changed_selected_points': changed,
        }

    result = {
        'schema': 'lpx-v5-combined-study-anonymous-v1', 'status': 'passed',
        'base_source_commit': '0415d79149d3410d3afc74ba822160811e735184',
        'protocol_commits': ['956f300b', '5818632e'],
        'source': audit['source'], 'settings': audit['settings'], 'runtime': workers[0]['runtime'],
        'exporter_source_sha256': sha(Path(__file__).read_bytes()),
        'scope': {'references': len(reference_samples), 'profile_groups_per_mode': len(old),
                  'reset_segments_per_mode': sum(len(r['segments']) for r in manifest['records']),
                  'unique_reference_samples': sum(reference_samples.values()),
                  'automatic_gate': 'original PCM/PWM SSE/STOI plus accepted same-budget control floors',
                  'tradeoffs': 'listening/control alternatives only; never permission to relax original floors',
                  'zero_fit_metrics': 'null, never zero error',
                  'admission_scope': 'finite segment pools and explicitly bounded metric shortlist',
                  'audibility': 'not established', 'physical_board': 'not tested'},
        'independent_audit': {k: audit[k] for k in ('counters', 'unique_native_streams', 'elapsed_seconds',
            'auditor_source_sha256', 'all_original_and_accepted_control_gates_exact', 'all_complete_caps_exact',
            'all_whole_reference_metrics_objectives_and_native_model_pwm_exact')},
        'modes': {},
    }
    count_keys = ('full_synthesis_evaluations', 'objective_evaluations', 'spectral_trials',
                  'excitation_trials', 'local_synthesis_evaluations', 'local_synthesized_samples',
                  'serialization_calls', 'completed_windows', 'incomplete_windows',
                  'allocation_evaluations', 'state_advances', 'cache_hits', 'completed_parent_expansions',
                  'final_metric_evaluations')
    for mode in ('sse', 'perceptual'):
        owned = [w for w in workers if w['mode'] == mode]
        records = [r for w in owned for r in w['records']]
        assert len(records) == len({r['id'] for r in records}) == 98
        searches = [s for r in records for s in r['searches']]
        counts = {k: sum(s['report'][k] for s in searches) for k in count_keys}
        counts.update(segment_fits=len(searches),
                      full_synthesis_limit_hits=sum(s['report']['search_limit_reached'] for s in searches),
                      capacity_calls=sum(s['capacity_statistics']['calls'] for s in searches),
                      allocator_candidate_evaluations=sum(s['capacity_statistics']['candidate_evaluations'] for s in searches),
                      allocator_confirmation_evaluations=sum(s['capacity_statistics']['confirmation_evaluations'] for s in searches),
                      accepted_swaps=sum(s['capacity_statistics']['accepted_swaps'] for s in searches),
                      assembly_objective_evaluations=sum(b['assembly']['objective_evaluations'] for r in records for b in r['budgets']),
                      assembly_full_metric_evaluations=sum(b['assembly']['full_metric_evaluations'] for r in records for b in r['budgets']))
        groups = {'all': records}
        groups.update({split: [r for r in records if r['split'] == split]
                       for split in ('tuning', 'evaluation', 'additional')})
        groups['independent_cohort_subset'] = [r for r in records if r['cohort'] == 'independent']
        result['modes'][mode] = {
            'counts': counts,
            'fit_status_counts': dict(Counter(s['report']['fit_status'] for s in searches)),
            'maximum_full_synthesis_evaluations_per_fit': max(s['report']['full_synthesis_evaluations'] for s in searches),
            'maximum_allocator_evaluations_per_fit': max(s['report']['allocation_evaluations'] for s in searches),
            'record_cpu_seconds_including_reused_smoke': sum(r['cpu_seconds'] for r in records),
            'record_wall_seconds_sum_including_reused_smoke': sum(r['wall_seconds'] for r in records),
            'worker_cpu_seconds_excluding_reused_smoke': sum(w['cpu_seconds'] for w in owned),
            'worker_wall_seconds_by_shard': [w['wall_seconds'] for w in owned],
            'worker_warmup_wall_seconds_by_shard': [w['warmup_wall_seconds'] for w in owned],
            'records_executed_in_full_workers': sum(w['records_executed'] for w in owned),
            'records_reused_from_exact_smoke': sum(w['records_reused'] for w in owned),
            'effective_gamma2': bounds([r['objective']['effective_gamma2'] for r in records]),
            'maximum_coefficient_storage_bytes_per_reference': max(r['objective']['coefficient_storage_bytes'] for r in records),
            'groups': {name: [budget_summary(rows, mode, percent) for percent in (100, 95, 90)]
                       for name, rows in groups.items()},
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes((json.dumps(result, indent=2, allow_nan=False) + '\n').encode('utf-8'))
    print(json.dumps({'status': result['status'], 'profile_mode_groups': 196,
                      'segment_fits': sum(m['counts']['segment_fits'] for m in result['modes'].values())}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    main(args.study, args.output)

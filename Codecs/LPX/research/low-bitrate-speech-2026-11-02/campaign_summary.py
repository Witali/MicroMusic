"""Pure anonymous aggregation and the preregistered stopping transition."""
from __future__ import annotations

import math

TUNING = frozenset((*range(4), *range(8, 12), 16, 19))
HELDOUT = frozenset((*range(4, 8), *range(12, 16), 17, 18))
NEGATIVE = frozenset(range(20, 27))
EXPECTED_GROUPS = ('clean',) * 16 + ('quiet',) * 2 + ('noise15',) * 2 + ('acoustic_music',) * 3 + ('synthetic',) * 4


def split(ordinal):
    if ordinal in TUNING:
        return 'tuning_speech'
    if ordinal in HELDOUT:
        return 'heldout_speech'
    if ordinal in NEGATIVE:
        return 'negative_controls'
    raise ValueError('Unknown registered corpus ordinal')


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_metrics(row, n=32000):
    if (not row.get('admissible') or not finite(row['score']) or row['score'] < 0
            or isinstance(row['file_bytes'], bool) or not isinstance(row['file_bytes'], int) or row['file_bytes'] <= 0
            or isinstance(row['clipped_samples'], bool) or not isinstance(row['clipped_samples'], int)
            or not 0 <= row['clipped_samples'] <= n):
        raise ValueError('Receipt does not describe an admitted complete candidate')
    for domain in ('pcm16', 'pwm8'):
        value = row['metrics'][domain]
        if value['samples'] != n or any(not finite(value[key]) or value[key] < 0
                for key in ('reference_energy', 'error_energy')):
            raise ValueError('Inconsistent full-output metric geometry')
        if value['stoi'] is not None and not finite(value['stoi']):
            raise ValueError('Nonfinite intelligibility metric')
    for domain in ('voice', 'pwm_voice'):
        value = row[domain]
        if (any(isinstance(value[key], bool) or not isinstance(value[key], int)
                for key in ('within_tolerance_frames', 'reference_period_frames', 'frames'))
                or not 0 <= value['within_tolerance_frames'] <= value['reference_period_frames'] <= value['frames']):
            raise ValueError('Invalid source-period counts')


def verify_transition(before, after):
    """Verify receipt conformance; actual numerical admission belongs to RoundAdmission."""
    validate_metrics(before)
    validate_metrics(after)
    for domain in ('pcm16', 'pwm8'):
        a, b = before['metrics'][domain], after['metrics'][domain]
        if a['reference_energy'] != b['reference_energy'] or b['error_energy'] > a['error_energy']:
            raise ValueError('A selected receipt violates the fixed-target SSE guard')
        if a['stoi'] is not None and (b['stoi'] is None or b['stoi'] < a['stoi'] - 1e-12):
            raise ValueError('A selected receipt violates the fixed intelligibility guard')
    for domain in ('voice', 'pwm_voice'):
        if (before[domain]['reference_period_frames'] != after[domain]['reference_period_frames']
                or before[domain]['frames'] != after[domain]['frames']
                or after[domain]['within_tolerance_frames'] < before[domain]['within_tolerance_frames']):
            raise ValueError('The source-period denominator or count guard changed')
    if after['clipped_samples'] > before['clipped_samples']:
        raise ValueError('A selected receipt violates the clipping guard')
    if (after['score'], after['file_bytes']) > (before['score'], before['file_bytes']):
        raise ValueError('The protected incumbent was displaced by a worse selection key')


def same_anchor(previous, fresh):
    """A new round must freshly reconstruct the exact immediately prior target/output."""
    validate_metrics(previous)
    validate_metrics(fresh)
    if previous['file_bytes'] != fresh['file_bytes'] or abs(previous['score'] - fresh['score']) > 1e-12:
        raise ValueError('Fresh protected-incumbent metrics differ from the prior round')
    for domain in ('pcm16', 'pwm8'):
        a, b = previous['metrics'][domain], fresh['metrics'][domain]
        for key in ('samples', 'reference_energy', 'error_energy'):
            if a[key] != b[key]:
                raise ValueError('The full-output baseline changed between rounds')
        if (a['stoi'] is None) != (b['stoi'] is None) or (a['stoi'] is not None and abs(a['stoi'] - b['stoi']) > 1e-12):
            raise ValueError('Fresh incumbent intelligibility differs')
    for domain in ('voice', 'pwm_voice'):
        for key in ('reference_period_frames', 'within_tolerance_frames', 'frames'):
            if previous[domain][key] != fresh[domain][key]:
                raise ValueError('Fresh incumbent source-period diagnostics differ')
    if previous['clipped_samples'] != fresh['clipped_samples']:
        raise ValueError('Fresh incumbent clipping differs')


def aggregate(rows, eligible):
    """Fixed STOI membership, summed waveform energies and summed source windows."""
    by_ordinal = {item['ordinal']: item['metrics'] for item in rows}
    selected = sorted(set(by_ordinal) & set(eligible))
    stoi = [by_ordinal[index]['metrics']['pwm8']['stoi'] for index in selected]
    if any(value is None or not finite(value) for value in stoi):
        raise ValueError('A newly missing STOI value cannot be dropped from the fixed subset')
    power = sum(item['metrics']['metrics']['pwm8']['reference_energy'] for item in rows)
    error = sum(item['metrics']['metrics']['pwm8']['error_energy'] for item in rows)
    ser = 10 * math.log10(power / error) if power > 0 and error > 0 else None
    coverage = {}
    for domain in ('voice', 'pwm_voice'):
        denominator = sum(item['metrics'][domain]['reference_period_frames'] for item in rows)
        numerator = sum(item['metrics'][domain]['within_tolerance_frames'] for item in rows)
        all_windows = sum(item['metrics'][domain]['frames'] for item in rows)
        coverage[domain] = dict(source_windows=denominator, within_tolerance=numerator,
            total_reference_windows=all_windows, unknown_reference_windows=all_windows-denominator,
            coverage=numerator / denominator if denominator else None)
    return dict(cases=len(rows), mean_pwm_stoi=sum(stoi) / len(stoi) if stoi else None,
        stoi_assessed_cases=len(stoi), stoi_unassessed_cases=len(rows) - len(stoi),
        pwm_reference_energy=power, pwm_error_energy=error, aggregate_pwm_ser_db=ser,
        ser_status='finite' if ser is not None else 'perfect' if power and not error else 'zero_reference',
        period=coverage, encoded_bytes=sum(item['metrics']['file_bytes'] for item in rows),
        clipped_samples=sum(item['metrics']['clipped_samples'] for item in rows))


def deltas(before, after):
    for domain in ('voice', 'pwm_voice'):
        if before['period'][domain]['source_windows'] != after['period'][domain]['source_windows']:
            raise ValueError('The aggregated source-period denominator changed')
    a, b = before['mean_pwm_stoi'], after['mean_pwm_stoi']
    stoi = b - a if a is not None and b is not None else None
    a, b = before['aggregate_pwm_ser_db'], after['aggregate_pwm_ser_db']
    ser = b - a if a is not None and b is not None else None
    a, b = before['period']['pwm_voice']['coverage'], after['period']['pwm_voice']['coverage']
    period = (b - a) * 100 if a is not None and b is not None else None
    perfect_gain = before['ser_status'] == 'finite' and after['ser_status'] == 'perfect'
    # Tiny comparison slack only protects the decimal thresholds from binary
    # floating-point representation; it is far below reported precision.
    clear = bool(stoi is not None and stoi >= .01 - 1e-12
        or ser is not None and ser >= .3 - 1e-12 or perfect_gain
        or period is not None and period >= 5 - 1e-10)
    return dict(mean_pwm_stoi=stoi, aggregate_pwm_ser_db=ser,
        aggregate_pwm_ser_improved_to_perfect=perfect_gain,
        pwm_source_period_coverage_percentage_points=period, clear_numerical_gain=clear)


def summarize(records, stoi_eligible, previous_no_clear):
    if len(records) != 54 or {(r['ordinal'], r['kbps']) for r in records} != {(i, k) for i in range(27) for k in (2, 3)}:
        raise ValueError('Only a complete, unique 27-case by two-budget round can advance the ledger')
    for row in records:
        if row['status'] != 'PASS' or row['group'] != EXPECTED_GROUPS[row['ordinal']]:
            raise ValueError('Claimed, running, failed or misgrouped work is not a completed round')
        verify_transition(row['before'], row['after'])
    budgets = {}
    for kbps in (2, 3):
        available = [row for row in records if row['kbps'] == kbps]
        groups = {name: [row for row in available if split(row['ordinal']) == name]
                  for name in ('heldout_speech', 'tuning_speech', 'negative_controls')}
        groups.update({name: [row for row in available if row['group'] == name] for name in set(EXPECTED_GROUPS)})
        values = {}
        eligible = stoi_eligible[str(kbps)]
        for group, items in sorted(groups.items()):
            before = aggregate([dict(ordinal=r['ordinal'], metrics=r['before']) for r in items], eligible)
            after = aggregate([dict(ordinal=r['ordinal'], metrics=r['after']) for r in items], eligible)
            values[group] = dict(before=before, after=after, delta=deltas(before, after))
        budgets[str(kbps)] = dict(groups=values,
            changed_cases=sum(row['changed'] for row in available),
            clear_numerical_gain=values['heldout_speech']['delta']['clear_numerical_gain'])
    clear = any(value['clear_numerical_gain'] for value in budgets.values())
    count = 0 if clear else previous_no_clear + 1
    return dict(schema='lpx-followup-anonymous-round-v1', completed_jobs=54, budgets=budgets,
        previous_consecutive_no_clear=previous_no_clear, clear_numerical_gain=clear,
        consecutive_no_clear=count, stop_condition_met=count >= 3,
        threshold_scope='Heldout speech only, fixed per-budget STOI subsets; PWM coverage uses unchanged source windows',
        scope='Numerical stopping convention, not audibility, subjective quality or complete pitch preservation')

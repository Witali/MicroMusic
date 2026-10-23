"""Per-recording speech regression gates; no averaging across recordings.

This protects an explicitly named finite corpus. It does not establish quality
for an unseen recording or authorize character-dependent codec behavior. A
caller selecting a baseline fallback must retain that baseline's actual model.
"""
from collections.abc import Mapping
import math
from numbers import Real


METRIC_DIRECTIONS = (
    ('stoi','higher'),
    ('estoi','higher'),
    ('fine_log_error','lower'),
    ('envelope_error','lower'),
    ('unsupported_energy','lower'),
    ('missing_energy','lower'),
)


def _tolerance(value):
    if isinstance(value,bool) or not isinstance(value,Real) or not math.isfinite(value) or value < 0:
        raise ValueError('Numeric tolerance must be finite and nonnegative')
    return float(value)


def _metrics(value,source):
    result,errors = {},[]
    if not isinstance(value,Mapping):
        return result,[dict(source=source,reason='missing_or_invalid_recording')]
    for metric,_ in METRIC_DIRECTIONS:
        if metric not in value:
            errors.append(dict(source=source,metric=metric,reason='missing_metric'))
            continue
        number = value[metric]
        if isinstance(number,bool) or not isinstance(number,Real):
            errors.append(dict(source=source,metric=metric,reason='nonnumeric_metric'))
        elif not math.isfinite(number):
            errors.append(dict(source=source,metric=metric,reason='nonfinite_metric'))
        else:
            result[metric] = float(number)
    return result,errors


def compare_recording_metrics(baseline,candidate,*,tolerance=1e-9):
    """Require all six finite metrics and no individual quality regression.

    Higher STOI/eSTOI and lower each of the four spectral errors are better.
    Absolute numeric tolerance is the only permitted deterioration; there is
    no relative tolerance or compensation between metrics.
    """
    tolerance = _tolerance(tolerance)
    baseline,baseline_errors = _metrics(baseline,'baseline')
    candidate,candidate_errors = _metrics(candidate,'candidate')
    violations = baseline_errors+candidate_errors
    if not violations:
        for metric,direction in METRIC_DIRECTIONS:
            old,new = baseline[metric],candidate[metric]
            worse = new < old if direction == 'higher' else new > old
            if worse and not math.isclose(old,new,rel_tol=0.,abs_tol=tolerance):
                violations.append(dict(metric=metric,reason='decreased' if direction == 'higher' else 'increased',
                                       baseline=old,candidate=new))
    return dict(candidate_passed=not bool(violations),baseline_valid=not bool(baseline_errors),
                candidate_valid=not bool(candidate_errors),tolerance=tolerance,
                baseline_metrics=baseline,candidate_metrics=candidate,violations=violations)


def guard_recordings(baselines,candidates,protected_ids,*,fallback_to_baseline=False,tolerance=1e-9):
    """Check every protected recording, optionally select frozen fallbacks.

    ``candidate_passed`` stays false after rejection even if fallback makes
    ``selection_passed`` true. Unprotected recordings are explicitly unchecked.
    No dictionary-wide average or speaker/character rule is used.
    """
    tolerance = _tolerance(tolerance)
    if not isinstance(baselines,Mapping) or not isinstance(candidates,Mapping):
        raise TypeError('Expected recording-ID mappings for baseline and candidate metrics')
    if not isinstance(fallback_to_baseline,bool):
        raise ValueError('Baseline fallback must be an explicit boolean')
    if isinstance(protected_ids,str):
        raise ValueError('Pass a collection of protected recording IDs, not one string')
    protected_ids = tuple(dict.fromkeys(protected_ids))
    if not protected_ids or any(not isinstance(clip,str) or not clip for clip in protected_ids):
        raise ValueError('At least one nonempty protected recording ID is required')
    recordings = {}
    for clip in protected_ids:
        result = compare_recording_metrics(baselines.get(clip),candidates.get(clip),tolerance=tolerance)
        selected = ('candidate' if result['candidate_passed'] else
                    'baseline' if fallback_to_baseline and result['baseline_valid'] else None)
        result.update(selected_source=selected,baseline_fallback_used=selected == 'baseline',
                      selected_metrics=(result['candidate_metrics'] if selected == 'candidate' else
                                        result['baseline_metrics'] if selected == 'baseline' else None))
        recordings[clip] = result
    return dict(schema='speech-recording-regression-v1',tolerance=tolerance,
                protected_ids=list(protected_ids),
                unchecked_ids=sorted((set(baselines)|set(candidates))-set(protected_ids)),
                candidate_passed=all(result['candidate_passed'] for result in recordings.values()),
                selection_passed=all(result['selected_source'] is not None for result in recordings.values()),
                baseline_fallback_used=any(result['baseline_fallback_used'] for result in recordings.values()),
                recordings=recordings,
                scope='Explicit finite protected corpus; no guarantee for unseen recordings')

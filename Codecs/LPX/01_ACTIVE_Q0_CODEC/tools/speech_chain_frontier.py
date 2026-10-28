"""Bounded selection of v5 segment alternatives on the complete recording.

Decoder state resets at each stored segment. The supplied objective receives
one concatenated waveform, so perceptual error history need not reset there.
No proportional segment cap or segment-local quality floor decides admission.
"""
from __future__ import annotations

from dataclasses import dataclass
import itertools
import math
from numbers import Integral

import numpy as np
import speech_compact as compact
from refine_speech_compact import no_regression, quality


@dataclass
class ChainCandidate:
    streams: tuple
    pcm: np.ndarray
    file_bytes: int
    objective: float
    metrics: dict
    conservative_floors_passed: bool


@dataclass
class ChainSelection:
    """Owned result snapshot; selected/tradeoff/frontier may share a candidate."""
    selected: ChainCandidate | None
    tradeoff: ChainCandidate | None
    frontier: list
    report: dict


class _EvaluationLimit(Exception):
    pass


def assemble(reference, baseline_streams, alternatives, max_bytes, *, objective=None,
             beam_width=32, max_evaluations=4096):
    """Select actual stored streams, with whole-waveform scoring and admission.

    alternatives is one iterable of serialized streams per original segment;
    the baseline is always added to its segment pool. All PCM is independently
    reconstructed, never trusted from search reports. Enumerate all combinations
    when the pool fits the evaluation bound; otherwise use an explicit bounded
    left-to-right beam, retaining complete feasible continuations along the way.
    Conservative selection checks full PCM/PWM metrics against the original
    chain. A feasible raw alternative is returned separately even if it fails
    those floors. A no-fit result describes only these finite candidate pools.
    """
    for name, value, lower, upper in (('max_bytes', max_bytes, 22, 16711425),
                                     ('beam_width', beam_width, 1, 256),
                                     ('max_evaluations', max_evaluations, 1, 1000000)):
        if isinstance(value, bool) or not isinstance(value, Integral) or not lower <= value <= upper:
            raise ValueError('Invalid ' + name)
    ref = np.asarray(reference)
    if (ref.ndim != 1 or ref.dtype.kind not in 'iu' or not len(ref)
            or np.any(ref < -32768) or np.any(ref > 32767)):
        raise ValueError('Expected complete original PCM16 reference')
    if isinstance(baseline_streams, (bytes, bytearray, str)):
        raise ValueError('Expected ordered reset segments')
    baseline = tuple(bytes(b) for b in baseline_streams)
    alternatives = list(alternatives)
    if not 1 <= len(baseline) <= 255 or len(alternatives) != len(baseline):
        raise ValueError('Expected one alternative pool per baseline segment')
    pools = []; pcms = []; baseline_keys = []; lengths = []
    for seed, supplied in zip(baseline, alternatives):
        n, profile, *_ = compact.unpack(seed)
        blobs = sorted({seed, *(bytes(b) for b in supplied)}, key=lambda b: (len(b), b))
        decoded = []
        for blob in blobs:
            samples, p, *_ = compact.unpack(blob)
            if samples != n or p != profile:
                raise ValueError('Alternative changed segment geometry/profile')
            decoded.append(compact.decode_model(blob))
        pools.append(blobs); pcms.append(decoded); baseline_keys.append(blobs.index(seed)); lengths.append(n)
    if sum(lengths) != len(ref):
        raise ValueError('Chain does not cover the complete original recording')
    baseline_keys = tuple(baseline_keys)
    def join(keys):
        return np.concatenate([pcms[i][k] for i, k in enumerate(keys)])
    def size(keys):
        return sum(len(pools[i][k]) for i, k in enumerate(keys))
    reference64 = ref.astype(np.int64)
    if objective is None:
        def objective(pcm):
            error = pcm.astype(np.int64) - reference64
            return int(np.dot(error, error))
    elif not callable(objective):
        objective = getattr(objective, 'score', None)
        if not callable(objective):
            raise ValueError('Expected a callable objective or score(pcm16)')
    before = quality(ref, join(baseline_keys))
    product = math.prod(len(p) for p in pools)
    minimum = sum(len(p[0]) for p in pools)
    scores = {}; exhausted = False
    def evaluate(keys):
        if size(keys) > max_bytes:
            return None
        if keys not in scores:
            if len(scores) >= max_evaluations:
                raise _EvaluationLimit
            score = float(objective(join(keys)))
            if not np.isfinite(score):
                raise ValueError('Objective must return a finite score')
            scores[keys] = score
        return scores[keys]
    try:
        # Retain rollback independently of objective-only beam pruning.
        evaluate(baseline_keys)
        if product <= max_evaluations:
            for keys in itertools.product(*(range(len(p)) for p in pools)):
                evaluate(keys)
        elif minimum <= max_bytes:
            beam = [()]
            for depth, pool in enumerate(pools):
                expanded = []
                for prefix in beam:
                    for k in range(len(pool)):
                        partial = (*prefix, k)
                        complete = partial + (0,) * (len(pools) - len(partial))
                        score = evaluate(complete)
                        if score is not None:
                            expanded.append((partial, score, size(complete)))
                expanded.sort(key=lambda x: (x[1], x[2], x[0]))
                # Preserve a cheap continuation as well as the strongest scores.
                keep = expanded[:beam_width]
                if expanded and beam_width > 1:
                    cheap = min(expanded, key=lambda x: (x[2], x[1], x[0]))
                    if cheap not in keep:
                        keep[-1] = cheap
                beam = [x[0] for x in keep]
    except _EvaluationLimit:
        exhausted = True
    ranked = sorted(scores, key=lambda k: (scores[k], size(k), k))
    shortlist = ranked[:beam_width]
    if baseline_keys in scores and baseline_keys not in shortlist:
        shortlist.append(baseline_keys)
    # Preserve measured size/quality frontier points for later chain-level use.
    front_keys = []; best_score = math.inf
    for keys in sorted(scores, key=lambda k: (size(k), scores[k], k)):
        if scores[keys] < best_score:
            front_keys.append(keys); best_score = scores[keys]
    if len(front_keys) > 16:
        front_keys = [front_keys[int(i)] for i in np.linspace(0, len(front_keys) - 1, 16, dtype=int)]
    for keys in front_keys:
        if keys not in shortlist:
            shortlist.append(keys)
    measured = {}
    for keys in shortlist:
        pcm = join(keys); metrics = quality(ref, pcm)
        measured[keys] = ChainCandidate(tuple(pools[i][k] for i, k in enumerate(keys)),
            pcm.copy(), size(keys), scores[keys], metrics, no_regression(metrics, before))
    conservative = [measured[k] for k in ranked if k in measured and measured[k].conservative_floors_passed]
    selected = conservative[0] if conservative else None
    raw = measured[ranked[0]] if ranked else None
    report = {'status': 'selected' if selected else 'tradeoff_only' if raw else 'no_pool_combination_fits',
        'segment_samples': lengths, 'baseline_bytes': sum(map(len, baseline)), 'max_complete_stream_bytes': int(max_bytes),
        'minimum_pool_bytes': minimum, 'candidate_combinations': product, 'objective_evaluations': len(scores),
        'full_metric_evaluations': len(measured), 'enumeration': 'exhaustive' if product <= max_evaluations else 'bounded_beam',
        'evaluation_limit_reached': exhausted, 'beam_width': int(beam_width), 'whole_reference_floors': True,
        'metric_admission_scope': 'objective shortlist, bounded size frontier, and feasible baseline rollback',
        'retained_frontier_limit': 16,
        'no_fit_scope': 'finite supplied segment pools only', 'baseline': before}
    return ChainSelection(selected, raw, [measured[k] for k in front_keys], report)

"""Real HQ4-Q3 byte reduction under frozen-original partial-error bounds."""
from dataclasses import dataclass
import math
import numpy as np
from hq4_core import pack_stream


VERSION = 'q3-track-rate-v1'


@dataclass(frozen=True)
class TrackLimits:
    frequency_key: str
    amplitude_key: str
    frequency_cap: float
    amplitude_cap: float
    missing_cap: float
    extra_cap: float
    coverage_floor: float
    continuity_cap: float
    minimum_stoi: float | None = None

    @classmethod
    def create(cls, baseline, frequency, amplitude, *, unit='cents', statistic='p95', relative=False,
               minimum_stoi=None):
        if (unit not in ('cents', 'hz') or statistic not in ('mean', 'p95', 'max')
                or not math.isfinite(frequency) or not math.isfinite(amplitude)
                or frequency < 0 or amplitude < 0 or
                (minimum_stoi is not None and (not math.isfinite(minimum_stoi) or not 0 <= minimum_stoi <= 1))):
            raise ValueError('Expected finite nonnegative frequency/amplitude tolerances and known units')
        prefix = '' if statistic == 'mean' else statistic+'_'
        frequency_key = f'frequency_error_{prefix}{unit}'
        amplitude_key = f'level_error_{prefix}db'
        return cls(frequency_key, amplitude_key,
            frequency+(baseline[frequency_key] if relative else 0.),
            amplitude+(baseline[amplitude_key] if relative else 0.),
            baseline['missing_reference_energy'], baseline['extra_candidate_energy'],
            baseline['weighted_match_rate'], baseline['continuity_break_rate'], minimum_stoi)

    def failures(self, score):
        if score is None:
            return ['integer-arithmetic-or-PWM-guard']
        caps = {self.frequency_key:self.frequency_cap, self.amplitude_key:self.amplitude_cap,
                'missing_reference_energy':self.missing_cap,
                'extra_candidate_energy':self.extra_cap,
                'continuity_break_rate':self.continuity_cap}
        failed = [key for key, cap in caps.items() if not math.isfinite(score[key]) or score[key] > cap+1e-12]
        if not math.isfinite(score['weighted_match_rate']) or score['weighted_match_rate'] < self.coverage_floor-1e-12:
            failed.append('weighted_match_rate')
        if self.minimum_stoi is not None and (not math.isfinite(score['stoi']) or score['stoi'] < self.minimum_stoi-1e-12):
            failed.append('minimum_stoi')
        return failed


def _distance(before, after, durations):
    a, b = before[:, 2:].astype(float), after[:, 2:].astype(float)
    squared = (a % 16-b % 16)**2+(np.floor(a/16)-np.floor(b/16))**2
    return float(np.sum(squared*np.asarray(durations)[:, None]))


def byte_saving_candidates(frames, durations):
    """Share coefficient runs and legally merge frames; actual packing decides."""
    before = len(pack_stream(frames, durations))
    candidates, seen = [], set()
    def add(f, d, label, distance, rows):
        payload = pack_stream(f, d)
        saved = before-len(payload)
        if saved <= 0 or payload in seen:
            return
        seen.add(payload)
        candidates.append(dict(frames=f, durations=d, payload=payload, saved=saved,
                               rank=distance/saved, operation=label, refit_rows=rows))
    n = len(frames)
    for first in range(1, n):
        for length in (1, 2, 4):
            end = min(n, first+length)
            for low, high in ((2, 4), (4, 6), (2, 6)):
                for source in (first-1, end):
                    if source >= n:
                        continue
                    f = frames.copy()
                    f[first:end, low:high] = frames[source, low:high]
                    rows = tuple(sorted(set(range(first, end)) | {source}))
                    add(f, durations.copy(), f'share-{low}-{high}-rows-{first}-{end}-source-{source}',
                        _distance(frames, f, durations), rows)
    for first in range(n-1):
        total = int(durations[first])+int(durations[first+1])
        if total > 256:
            continue
        for source in (first, first+1):
            f = np.delete(frames, first+1, axis=0)
            f[first] = frames[source]
            d = np.delete(durations, first+1)
            d[first] = total
            # Merge ranking also includes replaced pitch/gain/mode differences.
            other = frames[first+1 if source == first else first]
            distance = float(np.sum((frames[source].astype(float)-other.astype(float))**2)*total)
            add(f, d, f'merge-rows-{first}-{first+1}-source-{source}', distance, (first,))
    return sorted(candidates, key=lambda item:(item['rank'], -item['saved'], item['operation']))


def refitted_candidates(candidate, rng, count):
    """Jointly edit shared coefficient groups while retaining real byte savings."""
    if count <= 0:
        return []
    dimensions = list(range(8))
    rng.shuffle(dimensions)
    variants = []
    for dimension in dimensions:
        byte, shift = 2+dimension//2, 4*(dimension & 1)
        for delta in (-1, 1):
            f = candidate['frames'].copy()
            for row in candidate['refit_rows']:
                nibble = (int(f[row, byte]) >> shift) & 15
                value = min(15, max(1, nibble+delta))  # exclude unstable Q3 -8
                f[row, byte] = (int(f[row, byte]) & (15 if shift else 240)) | value << shift
            payload = pack_stream(f, candidate['durations'])
            variants.append(dict(candidate, frames=f, payload=payload,
                                 operation=candidate['operation']+f'-refit-k{dimension}-{delta}'))
            if len(variants) >= count:
                return variants
    return variants


def reduce_rate(frames, durations, evaluate, limits, rng, *, max_evaluations=500, repairs=2):
    """Keep only strictly smaller, feasible streams; the seed is always retained."""
    f, d = frames.copy(), durations.copy()
    payload = pack_stream(f, d)
    score = evaluate(f, d)
    initial_bytes = len(payload)
    tested, evaluations, history = {payload}, 0, []
    while evaluations < max_evaluations:
        accepted = None
        for candidate in byte_saving_candidates(f, d):
            options = [candidate]+refitted_candidates(candidate, rng, repairs)
            for trial in options:
                data = trial['payload']
                if len(data) >= len(payload) or data in tested:
                    continue
                tested.add(data)
                if evaluations >= max_evaluations:
                    break
                measured = evaluate(trial['frames'], trial['durations'])
                evaluations += 1
                if not limits.failures(measured):
                    accepted = trial, measured
                    break
            if accepted is not None or evaluations >= max_evaluations:
                break
        if accepted is None:
            break
        trial, score = accepted
        f, d, payload = trial['frames'], trial['durations'], trial['payload']
        history.append(dict(evaluation=evaluations, operation=trial['operation'], stream_bytes=len(payload),
                            frames=len(f), tracking=score))
    return dict(frames=f, durations=d, payload=payload, score=score,
                feasible=not limits.failures(score), failed_guards=limits.failures(score),
                initial_stream_bytes=initial_bytes, stream_bytes=len(payload),
                evaluations=evaluations, accepted_operations=len(history), history=history)

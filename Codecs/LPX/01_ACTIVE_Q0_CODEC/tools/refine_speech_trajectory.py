"""Bounded multi-frame joint LPC/excitation trajectories for unchanged v5 streams.

Beam alternatives are allowed to get worse before a later frame improves them.
Every path owns its integer filter/pitch state. Ranking uses full-length output,
actual serialization and an optional bound objective; conservative PCM/PWM/STOI
floors are a separate final selection, never a local beam-pruning condition.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
from dataclasses import dataclass
import json
from numbers import Integral
from pathlib import Path
import time

import numpy as np

import speech_compact as compact
from enhance_speech_compact import advance, sse
from q0_model import coefficient_trace, table
from refine_speech_compact import no_regression, quality
from refine_speech_lpc import adapt_excitation, coefficient_patch, fit_capacity, frame_order, spectrum_bits
from standard_metrics import pwm_duties
from speech_rate_allocation import distortion_rate
from wav_lpc import pack_frames


@dataclass
class Fields:
    spectra: np.ndarray
    params: np.ndarray
    pulses: np.ndarray
    extras: np.ndarray

    def copy(self):
        return Fields(*(x.copy() for x in (self.spectra, self.params, self.pulses, self.extras)))


@dataclass
class State:
    history: np.ndarray
    deemphasis: int
    brightness: int
    pitch: np.ndarray

    @classmethod
    def zero(cls):
        return cls(np.zeros(10, np.int64), 0, 0, np.zeros(256, np.int64))

    def copy(self):
        return State(self.history.copy(), self.deemphasis, self.brightness, self.pitch.copy())


@dataclass
class PathState:
    fields: Fields
    coefficients: np.ndarray
    pcm: np.ndarray
    stream: bytes
    score: float
    state: State
    position: int
    moves: tuple


@dataclass
class OutputCandidate:
    stream: bytes
    pcm: np.ndarray
    score: float
    moves: tuple


class SearchBudgetExhausted(Exception):
    pass


class Search:
    def __init__(self, reference, n, profile, pre, bright, max_bytes, objective,
                 max_evaluations, capacity_policy, allocation_evaluations, rate_lambda):
        self.reference = reference
        self.n, self.profile, self.pre, self.bright = n, profile, pre, bright
        self.max_bytes, self.objective = max_bytes, objective
        self.max_evaluations = max_evaluations
        self.capacity_policy, self.allocation_limit = capacity_policy, allocation_evaluations
        self.rate_lambda = rate_lambda
        self.steps, self.cosine = table('scale_table.inc'), table('cos_table.inc')
        self.evaluations = self.objective_evaluations = self.state_advances = 0
        self.excitation_trials = self.allocation_evaluations = self.cache_hits = 0
        self.spectral_trials = self.expansions = 0
        self.cache = OrderedDict()
        self.finalists = {}
        self.frontier = {}
        self.best_infeasible = None
        self.best_sse = None

    def encode(self, fields):
        return compact.pack(self.n, self.profile, fields.spectra.tolist(), fields.params.tolist(),
                            fields.pulses.tolist(), self.pre, self.bright,
                            extras=fields.extras.tolist())[0]

    def rank(self, path):
        return (max(0, len(path.stream)-self.max_bytes),
                distortion_rate(path.score, len(path.stream), self.rate_lambda), len(path.stream), path.moves)

    def score(self, pcm):
        value = float(self.objective(pcm))
        self.objective_evaluations += 1
        if not np.isfinite(value):
            raise ValueError('Objective must return a finite scalar')
        return value

    def render(self, parent, fields, coefficients):
        if self.evaluations >= self.max_evaluations:
            raise SearchBudgetExhausted
        self.evaluations += 1
        state = parent.state
        suffix = advance(coefficients, fields.params, fields.pulses, fields.extras,
                         self.steps, self.pre, self.bright, parent.position, self.n,
                         state.history, state.deemphasis, state.brightness, state.pitch)[0]
        return np.concatenate((parent.pcm[:parent.position], suffix))

    def remember(self, path):
        if len(path.stream) > self.max_bytes:
            if self.best_infeasible is None or self.rank(path) < self.rank(self.best_infeasible):
                self.best_infeasible = path
            return
        self.finalists[path.stream] = path
        point = OutputCandidate(path.stream, path.pcm, path.score, path.moves)
        dominated = any(len(other.stream) <= len(point.stream) and other.score <= point.score
                        for other in self.frontier.values())
        if not dominated:
            self.frontier = {stream: other for stream, other in self.frontier.items()
                             if not (len(point.stream) <= len(other.stream) and point.score <= other.score)}
            self.frontier[point.stream] = point
            if len(self.frontier) > 16:
                ordered = sorted(self.frontier.values(), key=lambda p: (len(p.stream), p.score))
                keep = [ordered[int(i)] for i in np.linspace(0, len(ordered)-1, 16, dtype=int)]
                self.frontier = {p.stream: p for p in keep}
        if self.best_sse is None or int(sse(self.reference, path.pcm)) < int(sse(self.reference, self.best_sse.pcm)):
            self.best_sse = path
        if len(self.finalists) > 8:
            keep = sorted(self.finalists.values(), key=self.rank)[:8]
            self.finalists = {p.stream: p for p in keep}

    def reclaim(self, parent, fields, coefficients):
        stream = self.encode(fields)
        if self.capacity_policy == 'none' or (len(stream) <= self.max_bytes and not self.rate_lambda):
            return fields
        if self.capacity_policy == 'amplitude':
            bits = sum(spectrum_bits(row, None if i == 0 else fields.spectra[i-1], self.profile)
                       for i, row in enumerate(fields.spectra))
            extra, _, _, _ = fit_capacity(bits, len(fields.spectra), self.profile,
                                          fields.extras, self.max_bytes, parent.position, self.n)
            result = fields.copy()
            result.extras = extra
            return result
        policy = self.capacity_policy
        if policy == 'marginal':
            from speech_rate_allocation import reclaim_extras
            policy = reclaim_extras
        remaining = min(self.allocation_limit-self.allocation_evaluations,
                        self.max_evaluations-self.evaluations)
        if remaining <= 0:
            return fields
        def render(extras):
            candidate = fields.copy()
            candidate.extras = np.asarray(extras, np.int64).copy()
            self.allocation_evaluations += 1
            return self.render(parent, candidate, coefficients)
        def serialize(extras):
            candidate = fields.copy()
            candidate.extras = np.asarray(extras, np.int64).copy()
            return self.encode(candidate)
        allocated = policy(fields.spectra.copy(), self.profile, fields.extras.copy(),
                           self.max_bytes, render=render, objective=self.score,
                           start=parent.position, max_evaluations=remaining,
                           rate_lambda=self.rate_lambda, serialize=serialize)
        result = fields.copy()
        result.extras = np.asarray(allocated.extras, np.int64).copy()
        # This is necessary for the cached prefix, independently of policy claims.
        if (result.extras.shape != fields.extras.shape or
                not np.array_equal(result.extras[:parent.position//40], fields.extras[:parent.position//40])):
            raise ValueError('Capacity policy changed fields before the cached prefix')
        self.encode(result)  # Validate legal values and dimensions by actual serialization.
        return result

    def candidate(self, parent, fields, coefficients, move):
        fields = self.reclaim(parent, fields, coefficients)
        stream = self.encode(fields)
        if stream in self.cache:
            pcm, score = self.cache.pop(stream)
            self.cache[stream] = (pcm, score)
            self.cache_hits += 1
        else:
            pcm = self.render(parent, fields, coefficients)
            score = self.score(pcm)
            self.cache[stream] = (pcm, score)
            if len(self.cache) > 64:
                self.cache.popitem(last=False)
        end = min(self.n, parent.position+320)
        st = parent.state
        _, h, dd, cc, ring = advance(coefficients, fields.params, fields.pulses, fields.extras,
                                    self.steps, self.pre, self.bright, parent.position, end,
                                    st.history, st.deemphasis, st.brightness, st.pitch)
        self.state_advances += 1
        result = PathState(fields, coefficients, pcm, stream, score,
                           State(h, dd, cc, ring), end, parent.moves+(move,))
        self.remember(result)
        return result

    def at_position(self, path, position):
        if position == path.position:
            return path
        st = State.zero()
        _, h, dd, cc, ring = advance(path.coefficients, path.fields.params,
                                    path.fields.pulses, path.fields.extras, self.steps,
                                    self.pre, self.bright, 0, position,
                                    st.history, 0, 0, st.pitch)
        self.state_advances += 1
        return PathState(path.fields, path.coefficients, path.pcm, path.stream,
                         path.score, State(h, dd, cc, ring), position, path.moves)


def _spectral_neighbours(fields, frame, profile):
    for field in range(10):
        for delta in (-1, 1):
            vector = fields.spectra[frame].copy()
            vector[field] += delta
            if not 0 <= vector[field] < (32 if profile == 4 else 64):
                continue
            if ((field and vector[field] <= vector[field-1]) or
                    (field < 9 and vector[field] >= vector[field+1])):
                continue
            result = fields.copy()
            result.spectra[frame] = vector
            yield result, ('lsf', frame, field, delta)


def _excitation_neighbours(fields, start, n, profile):
    for index in range(start//160, min(len(fields.params), (start+319)//160+1)):
        for field, low, high, stride in ((0, 0, 31, 1), (1, 18, 145, 1), (2, 0, 14, 2)):
            for delta in (-stride, stride):
                value = int(fields.params[index, field])+delta
                if low <= value <= high:
                    result = fields.copy()
                    result.params[index, field] = value
                    yield result, ('pitch', index, field, delta)
    index = start//20
    position, amplitude = map(int, fields.pulses[index])
    for delta in (-1, 1):
        pos = position+delta
        if 0 <= pos < min(20, n-start) and not (profile == 4 and pos % 5 == 2):
            result = fields.copy()
            result.pulses[index, 0] = pos
            yield result, ('pulse-position', index, delta)
    amplitudes = (-amplitude,) if profile == 4 else (amplitude-1, amplitude+1)
    for amp in amplitudes:
        if -8 <= amp <= 7 or profile == 4 and amp == 8:
            result = fields.copy()
            result.pulses[index, 1] = amp
            yield result, ('pulse-amplitude', index, amp)
    index = start//40
    if fields.extras[index, 1]:
        for delta in (-1, 1):
            amp = int(fields.extras[index, 1])+delta
            if -8 <= amp <= 7:
                result = fields.copy()
                result.extras[index] = (int(fields.extras[index, 0]) if amp else -1, amp)
                yield result, ('extra-amplitude', index, amp)


def _expand(search, parent, frame, spectral_candidates, excitation_candidates, horizon):
    """Joint Cartesian proposals plus refit; no local-improvement acceptance."""
    spectral = [search.candidate(parent, parent.fields.copy(), parent.coefficients.copy(), ('keep', frame))]
    neighbours = []
    start = parent.position
    for fields, move in (_spectral_neighbours(parent.fields, frame, search.profile) if spectral_candidates else ()):
        co = parent.coefficients.copy()
        patch = coefficient_patch(fields.spectra, search.profile, frame, search.n, search.cosine)
        co[start:start+len(patch)] = patch
        neighbours.append(search.candidate(parent, fields, co, move))
        search.spectral_trials += 1
    spectral.extend(sorted(neighbours, key=search.rank)[:spectral_candidates])
    excitation = []
    for fields, move in (_excitation_neighbours(parent.fields, start, search.n, search.profile) if excitation_candidates else ()):
        excitation.append(search.candidate(parent, fields, parent.coefficients.copy(), move))
    excitation = sorted(excitation, key=search.rank)[:excitation_candidates]
    children = list(spectral)+list(excitation)
    for base in spectral:
        for excite in excitation:
            fields = Fields(base.fields.spectra.copy(), excite.fields.params.copy(),
                            excite.fields.pulses.copy(), excite.fields.extras.copy())
            children.append(search.candidate(parent, fields, base.coefficients.copy(),
                                             ('joint', frame, base.moves[-1], excite.moves[-1])))
        if excitation_candidates:
            st = parent.state
            pp, ii, ee, count = adapt_excitation(search.reference, base.coefficients,
                base.fields.params, base.fields.pulses, base.fields.extras, search.steps,
                search.pre, search.bright, search.profile, start, min(search.n, start+480),
                horizon, st.history, st.deemphasis, st.brightness, st.pitch,
                len(base.fields.extras))
            search.excitation_trials += int(count)
            fields = Fields(base.fields.spectra.copy(), pp, ii, ee)
            children.append(search.candidate(parent, fields, base.coefficients.copy(), ('refit', frame, base.moves[-1])))
    search.expansions += 1
    # Distinct serialized trajectories; deterministic ties prefer earlier moves.
    unique = {}
    for path in children:
        if path.stream not in unique or search.rank(path) < search.rank(unique[path.stream]):
            unique[path.stream] = path
    return sorted(unique.values(), key=search.rank)


def refine(reference, blob, decoder, max_bytes, *, frame_limit=8, window_frames=2,
           beam_width=3, spectral_candidates=2, excitation_candidates=2,
           excitation_horizon=80, max_evaluations=512, objective=None,
           objective_name='sse', selection='conservative', capacity_policy='amplitude',
           allocation_evaluations=64, rate_lambda=0.0, frontier=None):
    """Return (selected bytes or None, PCM or None, report, raw feasible bytes or None).

    Tuple layout matches the older refine API, but a cap below the seed is
    permitted: (None, None, report, raw) means only a tradeoff candidate exists,
    while raw=None means this finite search did not discover any feasible file.
    selection='objective' explicitly permits a final metric tradeoff. A supplied
    frontier list receives feasible nondominated alternatives without local metric
    gate filtering, for subsequent whole-reset-chain assembly and evaluation.
    """
    settings = (max_bytes, frame_limit, window_frames, beam_width, spectral_candidates,
                excitation_candidates, excitation_horizon, max_evaluations, allocation_evaluations)
    if any(isinstance(v, bool) or not isinstance(v, Integral) for v in settings):
        raise ValueError('Expected integer cap and bounded trajectory settings')
    if not (22 <= max_bytes <= 65535 and 1 <= frame_limit <= 200 and 2 <= window_frames <= 4
            and 1 <= beam_width <= 8 and 0 <= spectral_candidates <= 4
            and 0 <= excitation_candidates <= 4 and excitation_horizon in (80, 160)
            and 1 <= max_evaluations <= 4096 and 0 <= allocation_evaluations <= 4096):
        raise ValueError('Unsupported bounded trajectory settings')
    if frontier is not None and not isinstance(frontier, list):
        raise ValueError('Frontier output must be a list')
    if selection not in ('conservative', 'objective') or not (callable(capacity_policy) or capacity_policy in ('none', 'amplitude', 'marginal')):
        raise ValueError('Unknown selection or capacity policy')
    if isinstance(rate_lambda, bool) or not np.isfinite(rate_lambda) or rate_lambda < 0:
        raise ValueError('Expected finite nonnegative rate lambda')
    ref = np.asarray(reference)
    if ref.ndim != 1 or ref.dtype.kind not in 'iu' or np.any(ref < -32768) or np.any(ref > 32767):
        raise ValueError('Expected mono PCM16 reference')
    n, profile, spectra, params, pulses, pre, bright, extras = compact.unpack(blob)
    if len(ref) != n:
        raise ValueError('Reference/stream sample count mismatch')
    begun, cpu_begun = time.perf_counter(), time.process_time()
    ref64 = ref.astype(np.int64)
    scorer = (lambda pcm: int(sse(ref64, pcm))) if objective is None else getattr(objective, 'score', objective)
    if not callable(scorer):
        raise ValueError('Objective must be callable or expose score(pcm16)')
    fields = Fields(*(np.asarray(x, np.int64) for x in (spectra, params, pulses, extras)))
    shift = 5 if profile == 4 else 4
    vectors = [[(int(v) << shift)+(1 << (shift-1)) for v in row] for row in fields.spectra for _ in range(2)]
    co = coefficient_trace(pack_frames(vectors[:(n+159)//160]), n)
    zero = State.zero()
    pcm = advance(co, fields.params, fields.pulses, fields.extras, table('scale_table.inc'),
                  pre, bright, 0, n, zero.history, 0, 0, zero.pitch)[0]
    native = decoder.decode_one_s16(blob, n)
    if native is None or not np.array_equal(pcm, native) or not np.array_equal(pcm, compact.decode_model(blob)):
        raise AssertionError('Trajectory baseline integer/native/model mismatch')
    before = quality(ref, pcm)
    search = Search(ref64, n, profile, pre, bright, max_bytes, scorer, max_evaluations,
                    capacity_policy, allocation_evaluations, float(rate_lambda))
    original = PathState(fields, co, pcm, bytes(blob), search.score(pcm), zero, 0, ())
    search.remember(original)
    center = original
    checkpoints = []
    limit_reached = False
    anchors = frame_order(ref64, pcm, frame_limit)
    if objective is None and before['pcm16']['error_energy'] == 0 and len(blob) <= max_bytes and not rate_lambda:
        anchors = []
    try:
        for anchor in anchors:
            beam = [search.at_position(center, anchor*320)]
            completed = 0
            for frame in range(anchor, min(len(spectra), anchor+window_frames)):
                children = []
                for parent in beam:
                    children.extend(_expand(search, parent, frame, spectral_candidates,
                                            excitation_candidates, excitation_horizon))
                unique = {}
                for path in children:
                    if path.stream not in unique or search.rank(path) < search.rank(unique[path.stream]):
                        unique[path.stream] = path
                beam = sorted(unique.values(), key=search.rank)[:beam_width]
                completed += 1
            center = min([center, *beam], key=search.rank)
            checkpoints.append(dict(anchor=anchor, frames=completed, beam_paths=len(beam),
                                    file_bytes=len(center.stream), objective=center.score,
                                    moves=[list(p.moves) for p in beam]))
    except SearchBudgetExhausted:
        limit_reached = True
    pool = [*search.finalists.values(), *search.frontier.values()]
    if search.best_sse is not None:
        pool.append(search.best_sse)
    if len(blob) <= max_bytes:
        pool.append(original)
    unique = {p.stream: p for p in pool}
    ranked = sorted(unique.values(), key=search.rank)
    measured = [(p, quality(ref, p.pcm)) for p in ranked]
    eligible = [(p, q) for p, q in measured if p.stream == bytes(blob) or no_regression(q, before)]
    chosen = (measured[0] if selection == 'objective' and measured else eligible[0] if eligible else None)
    raw = ranked[0] if ranked else None
    for path in {p.stream: p for p in (original, *search.frontier.values(), raw, chosen[0] if chosen else None) if p is not None}.values():
        actual = decoder.decode_one_s16(path.stream, n)
        if (actual is None or not np.array_equal(actual, path.pcm) or
                not np.array_equal(actual, compact.decode_model(path.stream)) or
                not np.array_equal(decoder.decode_one(path.stream, n), pwm_duties(actual))):
            raise AssertionError('Trajectory final native/model/PWM mismatch')
        if path.stream[12:16] != blob[12:16]:
            raise AssertionError('Trajectory changed frozen header filters')
    metric_lookup = {p.stream: q for p, q in measured}
    alternatives = []
    for path in sorted(search.frontier.values(), key=lambda p: (len(p.stream), p.score)):
        q = metric_lookup[path.stream]
        floor = path.stream == bytes(blob) or no_regression(q, before)
        alternatives.append(dict(stream=path.stream, pcm=path.pcm.copy(), objective=path.score,
                                 file_bytes=len(path.stream), metrics=q,
                                 conservative_floors_passed=bool(floor)))
    if frontier is not None:
        frontier.extend(alternatives)
    selected_fields = compact.unpack(chosen[0].stream) if chosen else None
    report = dict(proposal='compact_joint_trajectory', samples=n, profile=profile,
        baseline_bytes=len(blob), max_file_bytes=int(max_bytes),
        file_bytes=len(chosen[0].stream) if chosen else None,
        fit_status='selected_feasible' if chosen else 'feasible_tradeoff_only' if raw else 'no_feasible_candidate',
        feasible_found=raw is not None, baseline=before, selected=chosen[1] if chosen else None,
        raw_best=quality(ref, raw.pcm) if raw else None, raw_file_bytes=len(raw.stream) if raw else None,
        raw_objective=raw.score if raw else None,
        conservative_floors_passed=bool(chosen and (chosen[0].stream == bytes(blob) or no_regression(chosen[1], before))),
        changed_spectral_indices=int(np.count_nonzero(np.asarray(selected_fields[2]) != fields.spectra)) if chosen else None,
        changed_excitation_fields=sum(int(np.count_nonzero(np.asarray(selected_fields[index]) != original))
            for index, original in ((3, fields.params), (4, fields.pulses), (7, fields.extras))) if chosen else None,
        retained_frontier=[{k: v for k, v in entry.items() if k not in ('stream', 'pcm')} for entry in alternatives],
        retained_frontier_limit=16,
        objective_name=str(objective_name), selection=selection,
        capacity_policy=capacity_policy if isinstance(capacity_policy, str) else 'callback',
        rate_lambda=float(rate_lambda), rate_unit='complete_serialized_bits',
        full_synthesis_evaluations=search.evaluations, objective_evaluations=search.objective_evaluations,
        spectral_trials=search.spectral_trials, excitation_trials=search.excitation_trials,
        allocation_evaluations=search.allocation_evaluations, state_advances=search.state_advances,
        cache_hits=search.cache_hits, completed_parent_expansions=search.expansions,
        final_metric_evaluations=len(measured), search_limit_reached=limit_reached,
        best_encountered_oversize_bytes=len(search.best_infeasible.stream) if search.best_infeasible else None,
        frame_limit=int(frame_limit), window_frames=int(window_frames), beam_width=int(beam_width),
        spectral_candidates=int(spectral_candidates), excitation_candidates=int(excitation_candidates),
        excitation_horizon=int(excitation_horizon), max_evaluations=int(max_evaluations),
        allocation_evaluation_limit=int(allocation_evaluations), checkpoints=checkpoints,
        header_filters_exact=True, native_model_pwm_exact=True,
        seconds=time.perf_counter()-begun, cpu_seconds=time.process_time()-cpu_begun)
    return (chosen[0].stream, chosen[0].pcm, report, raw.stream) if chosen else (None, None, report, raw.stream if raw else None)


def main():
    import soundfile as sf
    from batch_decoder import BatchSession
    from output_paths import protect_outputs
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('reference', type=Path)
    p.add_argument('input', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--max-bytes', type=int, required=True)
    p.add_argument('--frames', type=int, default=8)
    p.add_argument('--window-frames', type=int, default=2)
    p.add_argument('--beam-width', type=int, default=3)
    p.add_argument('--spectral-candidates', type=int, default=2)
    p.add_argument('--excitation-candidates', type=int, default=2)
    p.add_argument('--evaluations', type=int, default=512)
    p.add_argument('--selection', choices=('conservative', 'objective'), default='conservative')
    p.add_argument('--capacity-policy', choices=('none', 'amplitude', 'marginal'), default='amplitude')
    p.add_argument('--rate-lambda', type=float, default=0.0)
    a = p.parse_args()
    paths = [a.output/name for name in ('audio.l4hy', 'decoded.wav', 'raw.l4hy', 'report.json')]
    protect_outputs([a.reference, a.input], paths)
    ref, rate = sf.read(a.reference, dtype='int16')
    if rate != 8000:
        raise ValueError('Reference must be 8 kHz')
    with BatchSession('batch', speech=True, speech_compact=True, compact_only=True) as decoder:
        result, pcm, report, raw = refine(ref, a.input.read_bytes(), decoder, a.max_bytes,
            frame_limit=a.frames, window_frames=a.window_frames, beam_width=a.beam_width,
            spectral_candidates=a.spectral_candidates, excitation_candidates=a.excitation_candidates,
            max_evaluations=a.evaluations, selection=a.selection,
            capacity_policy=a.capacity_policy, rate_lambda=a.rate_lambda)
    a.output.mkdir(parents=True, exist_ok=True)
    if result is None:
        paths[0].unlink(missing_ok=True)
        paths[1].unlink(missing_ok=True)
    else:
        paths[0].write_bytes(result)
        sf.write(paths[1], pcm, 8000, subtype='PCM_16')
    if raw is not None:
        paths[2].write_bytes(raw)
    else:
        paths[2].unlink(missing_ok=True)
    paths[3].write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('fit_status', 'file_bytes', 'full_synthesis_evaluations', 'cpu_seconds')}))


if __name__ == '__main__':
    main()

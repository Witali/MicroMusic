"""Frozen experimental Sparse80 metadata/pulse Cartesian refinement.

The previous study is imported read-only. No production/default/decoder change.
See PROTOCOL.md for the current-baseline binding, finite pools and controls.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import itertools
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parents[1] / 'sparse2'
sys.path.insert(0, str(PREVIOUS))
import exhaustive as old
import numpy as np
import speech_compact as compact
import speech_sparse80 as sparse
from lpx4 import BitReader
from enhance_speech_compact import advance

ARMS = ('joint', 'coordinate_mp', 'coordinate_pm')
REGIONS = 2
METADATA = 2
POOL_SIZE = 3
HORIZON = 400
SWEEPS = 2
SHORTLIST = 12
VERSION = 'sparse2-joint-v1'


@dataclass(frozen=True)
class Pool:
    packet: int
    symbols: tuple[int, ...]
    winners: tuple[int, int]
    losses: tuple[tuple[int, ...], tuple[int, ...]]


@dataclass
class Point:
    frame: int
    metadata_index: int
    parameters: tuple[int, int, int]  # scale, lag, ACTUAL even gain.
    symbols: tuple[int, ...]
    ordinal: int
    blob: bytes
    pcm: np.ndarray
    pwm: np.ndarray
    pcm_sse: int


@dataclass
class Region:
    frame: int
    metadata: tuple[tuple[int, int, int], tuple[int, int, int]]
    metadata_screen: list[dict]
    pools: tuple[Pool, ...]
    points: list[Point]
    queried: dict[str, list[Point]]
    endpoints: dict[str, Point]
    query_attempts: dict[str, int]


@dataclass
class Result:
    baseline: Point
    regions: list[Region]
    queues: dict[str, list[Point]]
    raw: dict[str, Point]
    counters: dict[str, int]
    version: str = VERSION


def metadata_offsets(blob):
    layout = old.parse_layout(blob)
    reader = BitReader(blob[22:])
    previous, offsets = None, []
    for _ in range((layout.samples + 319) // 320):
        previous = compact.get_spectrum(reader, previous, 6)
        offsets.append(22 * 8 + reader.o * 8 - reader.n)
        reader.get(5)
        reader.get(7)
        reader.get(3)
        for _ in range(4):
            reader.get(7)
    return tuple(offsets)


def _bits(output, offset, width, value):
    for bit in range(width):
        at = offset + bit
        mask = 1 << (at & 7)
        output[at >> 3] = (output[at >> 3] & ~mask) | (((value >> bit) & 1) * mask)


class Context:
    def __init__(self, blob):
        self.base = old.Context(blob)
        self.n, _, parameters, _, _, _ = sparse.unpack(blob)
        self.original_parameters = tuple(tuple(map(int, p)) for p in parameters)
        self.offsets = metadata_offsets(blob)

    def parameters(self, frame, metadata):
        result = self.base.parameters.copy()
        result[frame * 2:frame * 2 + 2] = metadata
        return result

    def forward(self, parameters, pulses, start, stop, snapshot):
        h, dd, cc, ring = snapshot
        b = self.base
        return advance(b.co, parameters, pulses, b.extras, b.steps, b.pre, b.bright,
                       start, stop, h, dd, cc, ring)

    def render(self, frame, metadata, symbols=None):
        if not 0 <= frame < self.n // 320:
            raise ValueError('Only complete real frames are editable')
        work = self.base.pulses.copy()
        if symbols is not None:
            if len(symbols) != 4:
                raise ValueError('A complete four-pulse tuple is required')
            for i, symbol in enumerate(symbols):
                old._set_symbol(work, frame * 4 + i, symbol)
        at = frame * 320
        out = self.forward(self.parameters(frame, metadata), work, at, self.n, self.base.snapshots[at])[0]
        return np.concatenate((self.base.pcm[:at], out))

    def patch(self, frame, metadata, symbols):
        if type(frame) is not int or not 0 <= frame < self.n // 320:
            raise ValueError('Only a valid complete real frame may be patched')
        if (not hasattr(symbols, '__len__') or len(symbols) != 4
                or any(type(symbol) is not int or not 0 <= symbol < 128 for symbol in symbols)):
            raise ValueError('Exactly four built-in integer seven-bit symbols are required')
        scale, lag, gain = metadata
        original = self.original_parameters[frame]
        if (type(scale) is not int or not 0 <= scale < 32 or type(lag) is not int or lag != original[1]
                or type(gain) is not int or gain not in range(0, 15, 2)):
            raise ValueError('Illegal scale/gain or changed lag')
        output = bytearray(old.patch_symbols(self.base.blob, self.base.layout,
            {frame * 4 + i: symbol for i, symbol in enumerate(symbols)}))
        _bits(output, self.offsets[frame], 5, scale)
        _bits(output, self.offsets[frame] + 12, 3, gain // 2)
        return bytes(output)


def freeze_metadata(context, reference, frame):
    original = context.original_parameters[frame]
    scale, lag, gain = original
    legal = sorted({(max(0, min(31, scale + ds)), lag,
                     2 * max(0, min(7, gain // 2 + dg)))
                    for ds in (-1, 0, 1) for dg in (-1, 0, 1)} - {original})
    rows = [dict(parameters=p, pcm_sse=old._sse(reference, context.render(frame, p))) for p in legal]
    chosen = min(rows, key=lambda row: (row['pcm_sse'], row['parameters'][0], row['parameters'][2]))
    return (original, chosen['parameters']), rows


def freeze_pools(context, reference, frame, metadata):
    """Shared400 pools; each metadata state carries its OWN original-pulse prefix."""
    losses = [[None] * 4 for _ in metadata]
    for m, meta in enumerate(metadata):
        parameters = context.parameters(frame, meta)
        snapshot = context.base.snapshots[frame * 320]
        work = context.base.pulses.copy()
        for part in range(4):
            packet = frame * 4 + part
            at = packet * 80
            stop = min(at + HORIZON, context.n)
            scores = []
            for symbol in range(128):
                old._set_symbol(work, packet, symbol)
                pcm = context.forward(parameters, work, at, stop, snapshot)[0]
                scores.append(old._sse(reference[at:stop], pcm))
            losses[m][part] = tuple(scores)
            old._set_symbol(work, packet, context.base.layout.symbols[packet])
            if part != 3:
                _, h, dd, cc, ring = context.forward(parameters, work, at, at + 80, snapshot)
                snapshot = h, dd, cc, ring
    pools = []
    for part in range(4):
        packet = frame * 4 + part
        incumbent = context.base.layout.symbols[packet]
        ranks = [sorted(range(128), key=lambda s: (losses[m][part][s], s != incumbent, s)) for m in range(2)]
        chosen = list(dict.fromkeys((incumbent, ranks[0][0], ranks[1][0])))
        for a, b in zip(*ranks):
            for symbol in (a, b):
                if symbol not in chosen and len(chosen) < POOL_SIZE:
                    chosen.append(symbol)
            if len(chosen) == POOL_SIZE:
                break
        pools.append(Pool(packet, tuple(chosen), (ranks[0][0], ranks[1][0]),
                          (losses[0][part], losses[1][part])))
    return tuple(pools)


def controls(points, pools, incumbent):
    """Two exact block-coordinate orders; all queries use complete PCM SSE."""
    lookup = {(p.metadata_index, p.symbols): p for p in points}
    paths = list(itertools.product(*(pool.symbols for pool in pools)))
    queried, endpoints, attempts = {}, {}, {}
    for arm, order in (('coordinate_mp', ('m', 'p')), ('coordinate_pm', ('p', 'm'))):
        seen = {}
        count = 0
        def query(m, path):
            nonlocal count
            count += 1
            point = lookup[m, path]
            seen.setdefault((m, path), point)
            return point
        # Equal common axis finalists for both orders, retained without forcing
        # the coordinate state to a winner from another arm or minimization.
        for path in paths:
            query(0, path)
        for m in range(2):
            query(m, incumbent)
        state = (0, incumbent)
        for _ in range(SWEEPS):
            for axis in order:
                m, path = state
                if axis == 'm':
                    choices = [query(i, path) for i in range(2)]
                    winner = min(choices, key=lambda p: (p.pcm_sse, p.metadata_index != m, p.metadata_index))
                else:
                    choices = [query(m, candidate) for candidate in paths]
                    winner = min(choices, key=lambda p: (p.pcm_sse, p.symbols != path, p.ordinal))
                state = winner.metadata_index, winner.symbols
        queried[arm], endpoints[arm], attempts[arm] = list(seen.values()), lookup[state], count
    return queried, endpoints, attempts


def search(reference, blob, receiver):
    context = Context(blob)
    target = old._reference(reference, context.n)
    pcm, pwm = old._oracle(receiver, blob, context.base.pcm)
    baseline = Point(-1, 0, (0, 18, 0), (), 0, bytes(blob), pcm, pwm, old._sse(target, pcm))
    cache = {bytes(blob): baseline}
    counters = dict(metadata_screens=0, metadata_screen_samples=0, pulse_screens=0,
        pulse_screen_samples=0, branch_prefix_samples=0, leaves=0, suffix_samples=0,
        model_checks=1, native_oracle_calls=1, coordinate_mp_queries=0, coordinate_pm_queries=0)
    order = sorted(range(context.n // 320), key=lambda f:
        (-old._sse(target[f * 320:(f + 1) * 320], pcm[f * 320:(f + 1) * 320]), f))[:REGIONS]
    regions, all_points = [], {arm: {} for arm in ARMS}
    for frame in order:
        metadata, screen = freeze_metadata(context, target, frame)
        counters['metadata_screens'] += len(screen)
        counters['metadata_screen_samples'] += len(screen) * (context.n - frame * 320)
        pools = freeze_pools(context, target, frame, metadata)
        counters['pulse_screens'] += 2 * 4 * 128
        counters['pulse_screen_samples'] += 2 * sum(128 * min(HORIZON, context.n - p.packet * 80) for p in pools)
        counters['branch_prefix_samples'] += 2 * 3 * 80
        points = []
        for m, meta in enumerate(metadata):
            for pi, path in enumerate(itertools.product(*(p.symbols for p in pools))):
                encoded = context.patch(frame, meta, path)
                modeled = context.render(frame, meta, path)
                counters['leaves'] += 1
                counters['suffix_samples'] += context.n - frame * 320
                if not np.array_equal(modeled, sparse.decode_model(encoded)):
                    raise AssertionError('Metadata/pulse carried suffix and independent full model differ')
                counters['model_checks'] += 1
                if encoded not in cache:
                    actual, duty = old._oracle(receiver, encoded, modeled)
                    cache[encoded] = Point(frame, m, meta, path, m * 81 + pi, encoded, actual, duty,
                                           old._sse(target, actual))
                    counters['native_oracle_calls'] += 1
                saved = cache[encoded]
                points.append(Point(frame, m, meta, path, m * 81 + pi, encoded, saved.pcm, saved.pwm, saved.pcm_sse))
        original = tuple(context.base.layout.symbols[frame * 4:frame * 4 + 4])
        queried, endpoints, attempts = controls(points, pools, original)
        queried['joint'] = points
        endpoints['joint'] = min(points, key=lambda p: (p.pcm_sse, p.ordinal))
        for arm in ARMS:
            for p in queried[arm]:
                if p.blob != blob:
                    all_points[arm].setdefault(p.blob, p)
        for arm in ('coordinate_mp', 'coordinate_pm'):
            counters[arm + '_queries'] += attempts[arm]
        regions.append(Region(frame, metadata, screen, pools, points, queried, endpoints, attempts))
    key = lambda p: (p.pcm_sse, p.frame, p.metadata_index, p.ordinal)
    queues = {arm: sorted(values.values(), key=key)[:SHORTLIST] for arm, values in all_points.items()}
    raw = {arm: min(values.values(), key=key) if values else baseline for arm, values in all_points.items()}
    return Result(baseline, regions, queues, raw, counters)


def admit(reference, result, *, speech=True):
    """Same old strict floors; each arm owns at most12 complete proposals."""
    from refine_sparse80_pulses import _measure, _floors, _band_context, _band_measure, band_error_floors
    from speech_noise_objective import NoiseObjective
    from voice_character import track_pitch
    from standard_metrics import pwm_pcm16
    target = old._reference(reference, len(result.baseline.pcm))
    track = track_pitch(target)
    objective, bands = NoiseObjective(target, track.period), _band_context(target)
    baseline = _measure(target, result.baseline.pcm, track, objective, bool(speech))
    floor_bands = _band_measure(bands, pwm_pcm16(result.baseline.pcm))
    measured = {result.baseline.blob: (baseline, floor_bands, 'baseline')}
    selections, journals = {}, {}
    for arm in ARMS:
        best, best_metrics = result.baseline, baseline
        rows = []
        for point in result.queues[arm]:
            cached = point.blob in measured
            if not cached:
                metrics = _measure(target, point.pcm, track, objective, bool(speech))
                freq = _band_measure(bands, pwm_pcm16(point.pcm))
                measured[point.blob] = metrics, freq, arm
            metrics, freq, created = measured[point.blob]
            floors = dict(same_complete_bytes=len(point.blob) == len(result.baseline.blob),
                quality=bool(_floors(metrics, baseline)), highband=bool(band_error_floors(freq, floor_bands)),
                changed_pwm=not np.array_equal(point.pwm, result.baseline.pwm),
                finite=bool(np.isfinite(metrics['score']) and np.isfinite(metrics['pwm_joint_score'])))
            improve = (metrics['score'] < best_metrics['score'] - 1e-12
                       and metrics['pwm_joint_score'] < best_metrics['pwm_joint_score'] - 1e-12)
            take = all(floors.values()) and improve
            rows.append(dict(frame=point.frame, metadata_index=point.metadata_index, parameters=point.parameters,
                symbols=point.symbols, sha256=hashlib.sha256(point.blob).hexdigest(), pcm_sse=point.pcm_sse,
                metrics=metrics, floors=floors, selected_at_step=bool(take),
                metrics_cached=cached, metrics_created_by=created))
            if take:
                best, best_metrics = point, metrics
        selections[arm], journals[arm] = best, rows
    return selections, dict(baseline=baseline, baseline_pwm_bands=floor_bands, candidates=journals,
        metric_proposal_attempts=sum(map(len, result.queues.values())),
        unique_metric_evaluations=len(measured), scope='Numerical admission only; no audible quality claim')

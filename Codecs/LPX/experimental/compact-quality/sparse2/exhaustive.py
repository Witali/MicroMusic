"""Experimental fixed-pool four-innovation search for unchanged v8 Sparse80.

All choices are offline. There is no new format, decoder, target gain or
candidate-dependent pool. Native replay uses an explicitly supplied oracle.
See MECHANISM_PROTOCOL.md for the prospectively fixed bounds and admissions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import itertools
from pathlib import Path
import sys
from typing import Callable

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
ACTIVE = REPO / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
if str(ACTIVE / 'tools') not in sys.path:
    sys.path.insert(0, str(ACTIVE / 'tools'))

import numpy as np
from numba import njit
import speech_compact as compact
import speech_sparse80 as sparse
from enhance_speech_compact import advance, sse
from lpx4 import BitReader
from q0_model import coefficient_trace, table
from standard_metrics import pwm_duties
from wav_lpc import pack_frames

VERSION = 'sparse2-frozen-four-v1'
MAX_REGIONS = 4
POOL_SIZE = 3
TAIL_SAMPLES = 400
FULL_SHORTLIST = 12
BEAM_WIDTHS = (1, 2, 4)


@dataclass(frozen=True)
class Layout:
    samples: int
    pulse_offsets: tuple[int, ...]  # Absolute LSB-first bit positions.
    symbols: tuple[int, ...]  # code6 | positiveSign1 << 6.


@dataclass(frozen=True)
class Pool:
    packet: int
    symbols: tuple[int, ...]
    immediate_winner: int
    tail_winner: int
    immediate_losses: tuple[int, ...]  # Indexed by wire symbol, all128 legal.
    tail_losses: tuple[int, ...]


@dataclass
class Candidate:
    blob: bytes
    pcm: np.ndarray
    pwm: np.ndarray
    pcm_sse: int
    region: int
    symbols: tuple[int, ...]
    ordinal: int


@dataclass
class Region:
    frame: int
    baseline_pcm_sse: int
    pools: tuple[Pool, ...]
    leaves: list[Candidate]
    exhaustive: Candidate
    controls: dict[int, Candidate]
    surviving_symbols: dict[int, tuple[tuple[int, ...], ...]]


@dataclass
class SearchResult:
    baseline: Candidate
    regions: list[Region]
    shortlist: list[Candidate]
    control_shortlists: dict[int, list[Candidate]]
    raw: Candidate  # Best generated changed leaf, even if worse than baseline.
    counters: dict[str, int]
    version: str = VERSION


def parse_layout(blob: bytes) -> Layout:
    """Validate the original stream, retaining each original pulse bit offset.

    Legal nonminimal spectral Rice spelling is deliberately not canonicalized.
    The strict Python unpacker rejects nonzero unused bits before native replay.
    """
    blob = bytes(blob)
    n, spectra, parameters, pulses, pre, bright = sparse.unpack(blob)
    reader = BitReader(blob[22:])
    previous = None
    offsets, symbols = [], []
    for _ in range((n + 319) // 320):
        previous = compact.get_spectrum(reader, previous, 6)
        reader.get(5)
        reader.get(7)
        reader.get(3)
        for _ in range(4):
            offsets.append(22 * 8 + reader.o * 8 - reader.n)
            symbols.append(reader.get(6) | (reader.get(1) << 6))
    return Layout(n, tuple(offsets), tuple(symbols))


def patch_symbols(blob: bytes, layout: Layout, replacements: dict[int, int]) -> bytes:
    """Replace existing seven-bit innovations; preserve every other input bit."""
    if parse_layout(blob) != layout:
        raise ValueError('Layout does not describe this exact input pulse sequence')
    output = bytearray(blob)
    for packet, symbol in replacements.items():
        if (type(packet) is not int or not 0 <= packet < len(layout.symbols)
                or type(symbol) is not int or not 0 <= symbol < 128):
            raise ValueError('Expected a legal pulse packet and seven-bit symbol')
        # Only complete real320-sample frames are editable in this experiment.
        if (packet // 4 + 1) * 320 > layout.samples:
            raise ValueError('The partial final frame is protected')
        offset = layout.pulse_offsets[packet]
        for bit in range(7):
            mask = 1 << ((offset + bit) & 7)
            at = (offset + bit) >> 3
            output[at] = (output[at] & ~mask) | (((symbol >> bit) & 1) * mask)
    return bytes(output)


def symbol_fields(symbol: int) -> tuple[int, int]:
    if type(symbol) is not int or not 0 <= symbol < 128:
        raise ValueError('Expected a seven-bit Sparse80 symbol')
    return sparse.POSITIONS[symbol & 63], 7 if symbol & 64 else -8


def _set_symbol(pulses, packet, symbol):
    position, amplitude = symbol_fields(int(symbol))
    first = packet * 4
    pulses[first:first + 4] = 0
    pulses[first + position // 20] = position % 20, amplitude


def _reference(reference, n):
    values = np.asarray(reference)
    if (values.shape != (n,) or values.dtype.kind not in 'iu'
            or np.any(values < -32768) or np.any(values > 32767)):
        raise ValueError('Expected the complete declared integer PCM16 target')
    result = values.astype(np.int16, copy=True)
    result.flags.writeable = False
    return result


class Context:
    """Original frozen decoder fields, waveform and h/ring/dd/cc snapshots."""
    def __init__(self, blob: bytes):
        self.blob = bytes(blob)
        self.layout = parse_layout(self.blob)
        self.n, spectra, parameters, pulses, self.pre, self.bright = sparse.unpack(self.blob)
        vectors = [[(int(value) << 4) + 8 for value in row]
                   for row in spectra for _ in range(2)]
        self.co = coefficient_trace(pack_frames(vectors[:(self.n + 159) // 160]), self.n)
        self.parameters = np.asarray([row for row in parameters for _ in range(2)], np.int64)
        self.pulses = np.zeros((len(spectra) * 16, 2), np.int64)
        for packet, symbol in enumerate(self.layout.symbols):
            _set_symbol(self.pulses, packet, symbol)
        self.extras = np.zeros((len(spectra) * 8, 2), np.int64)
        self.extras[:, 0] = -1
        self.steps = table('scale_table.inc')
        self.snapshots = {}
        h, ring = np.zeros(10, np.int64), np.zeros(256, np.int64)
        dd = cc = 0
        pcm = np.empty(self.n, np.int16)
        for start in range(0, self.n, 80):
            # The original state before every pulse, including carried pitch.
            self.snapshots[start] = h.copy(), int(dd), int(cc), ring.copy()
            stop = min(start + 80, self.n)
            out, h, dd, cc, ring = self.advance(self.pulses, start, stop, (h, dd, cc, ring))
            pcm[start:stop] = out
        self.pcm = pcm
        if not np.array_equal(self.pcm, sparse.decode_model(self.blob)):
            raise AssertionError('Snapshot recurrence and independent complete model differ')
        for value in (self.co, self.parameters, self.pulses, self.extras, self.steps, self.pcm):
            value.flags.writeable = False
        for h, _, _, ring in self.snapshots.values():
            h.flags.writeable = ring.flags.writeable = False

    def advance(self, pulses, start, stop, snapshot):
        h, dd, cc, ring = snapshot
        return advance(self.co, self.parameters, pulses, self.extras, self.steps,
                       self.pre, self.bright, start, stop, h, dd, cc, ring)

    def render(self, frame: int, symbols: tuple[int, ...], stop=None):
        """Exact original prefix plus actual changed state through the suffix."""
        if type(frame) is not int or not 0 <= frame < self.n // 320:
            raise ValueError('Expected a complete real frame')
        if not 0 <= len(symbols) <= 4:
            raise ValueError('At most four existing innovations are editable')
        work = self.pulses.copy()
        for index, symbol in enumerate(symbols):
            _set_symbol(work, frame * 4 + index, symbol)
        start = frame * 320
        stop = self.n if stop is None else stop
        if type(stop) is not int or not start <= stop <= self.n:
            raise ValueError('Invalid real synthesis range')
        out = self.advance(work, start, stop, self.snapshots[start])[0]
        return np.concatenate((self.pcm[:start], out))


def _sse(reference, pcm) -> int:
    return int(sse(reference, pcm))


def freeze_pool(context: Context, reference: np.ndarray, packet: int) -> Pool:
    """Incumbent + immediate80/tail400 winners from the SAME original state."""
    at = packet * 80
    if type(packet) is not int or packet < 0 or (packet // 4 + 1) * 320 > context.n:
        raise ValueError('Pool must belong to a complete real frame')
    stop = min(at + TAIL_SAMPLES, context.n)
    work = context.pulses.copy()
    immediate, tail = [], []
    for symbol in range(128):
        _set_symbol(work, packet, symbol)
        pcm = context.advance(work, at, stop, context.snapshots[at])[0]
        immediate.append(_sse(reference[at:at + 80], pcm[:80]))
        tail.append(_sse(reference[at:stop], pcm))
    incumbent = context.layout.symbols[packet]
    # Equal losses prefer the incumbent, then ascending seven-bit wire value.
    rank = lambda losses: sorted(range(128), key=lambda x: (losses[x], x != incumbent, x))
    short, long = rank(immediate), rank(tail)
    chosen = list(dict.fromkeys((incumbent, short[0], long[0])))
    # Duplicate winners do not reduce coverage arbitrarily. Alternate stable
    # immediate/tail rankings; no candidate or earlier chosen pulse changes them.
    for a, b in zip(short, long):
        for symbol in (a, b):
            if symbol not in chosen and len(chosen) < POOL_SIZE:
                chosen.append(symbol)
        if len(chosen) == POOL_SIZE:
            break
    return Pool(packet, tuple(chosen), short[0], long[0], tuple(immediate), tuple(tail))


def prune_controls(reference, context: Context, frame: int, pools: tuple[Pool, ...], leaves):
    """Same-pool prefix greedy/width2/width4, retaining actual carried state.

    Prefix loss ends at the newly added pulse's real80-sample boundary. Even at
    depth4 pruning precedes whole-suffix loss. Only retained complete paths are
    compared by whole-file PCM SSE, as in the prior pulse-by-pulse beam topology.
    """
    lookup = {candidate.symbols: candidate for candidate in leaves}
    controls, survivors = {}, {}
    incumbent = tuple(context.layout.symbols[frame * 4:frame * 4 + 4])
    for width in BEAM_WIDTHS:
        live = [()]
        for depth, pool in enumerate(pools, 1):
            trials = []
            stop = frame * 320 + depth * 80
            for prefix in live:
                for symbol in pool.symbols:
                    path = prefix + (symbol,)
                    # Lookup a full leaf carrying this prefix: later pulses
                    # cannot affect its earlier samples. Avoid extra synthesis.
                    full = path + incumbent[depth:]
                    pcm = lookup[full].pcm
                    loss = _sse(reference[:stop], pcm[:stop])
                    order = tuple(pools[i].symbols.index(value) for i, value in enumerate(path))
                    trials.append((loss, order, path))
            live = [path for _, _, path in sorted(trials)[:width]]
        survivors[width] = tuple(live)
        controls[width] = min((lookup[path] for path in live),
                              key=lambda c: (c.pcm_sse, c.ordinal))
    return controls, survivors


def bridge_receiver(common, only):
    """Explicit existing v8->v5/P6 bridge, checked by BOTH fixed C receivers.

    This does not claim these v5-only IPC binaries parse Sparse80 directly.
    NativeReceiver validates complete PCM/PWM lengths, error and finished/EOF.
    """
    def receiver(blob):
        n = sparse.unpack(blob)[0]
        expanded = sparse.expand(blob)
        outputs = []
        for decoder in (common, only):
            pcm, pwm = decoder.decode_one_s16(expanded, n), decoder.decode_one(expanded, n)
            if pcm is None or pwm is None:
                raise AssertionError('Native bridge rejected a valid full stream')
            outputs.append((pcm, pwm))
        if not all(np.array_equal(a, b) for a, b in zip(*outputs)):
            raise AssertionError('Native common/v5-only PCM or PWM differs')
        return outputs[0]
    return receiver


def _oracle(receiver, blob, modeled):
    native, pwm = receiver(blob)
    native, pwm = np.asarray(native), np.asarray(pwm)
    if (native.dtype != np.dtype('int16') or pwm.dtype != np.dtype('uint8')
            or native.shape != modeled.shape or pwm.shape != modeled.shape
            or not np.array_equal(native, modeled)
            or not np.array_equal(pwm, pwm_duties(modeled))):
        raise AssertionError('Independent native PCM/PWM and snapshot model differ')
    return native, pwm


def search(reference, blob: bytes, receiver: Callable) -> SearchResult:
    """Exhaust fixed pools in at most four independently edited complete frames.

    receiver(blob) must return actual native PCM int16 and PWM uint8. No speech
    metric/quality admission or source-dependent parameter tuning occurs here.
    The mandatory complete native/model comparison is performed for EVERY leaf.
    """
    context = Context(blob)
    target = _reference(reference, context.n)
    pcm, pwm = _oracle(receiver, context.blob, context.pcm)
    baseline = Candidate(context.blob, pcm, pwm, _sse(target, pcm), -1, (), 0)
    counters = dict(symbol_screens=0, symbol_screen_samples=0, leaves=0,
                    unique_native_leaves=0, native_oracle_calls=1, full_model_checks=1,
                    suffix_samples=0, prefix_control_extensions=0, full_quality_limit=FULL_SHORTLIST)
    complete = range(context.n // 320)
    ranked = sorted(complete, key=lambda f: (-_sse(target[f * 320:(f + 1) * 320],
                                                  pcm[f * 320:(f + 1) * 320]), f))[:MAX_REGIONS]
    cache = {context.blob: baseline}
    regions, all_changed = [], {}
    for frame in ranked:
        pools = tuple(freeze_pool(context, target, frame * 4 + i) for i in range(4))
        counters['symbol_screens'] += 128 * 4
        counters['symbol_screen_samples'] += sum(128 * min(TAIL_SAMPLES, context.n - p.packet * 80)
                                                  for p in pools)
        leaves = []
        for ordinal, path in enumerate(itertools.product(*(pool.symbols for pool in pools))):
            changed = {frame * 4 + i: int(symbol) for i, symbol in enumerate(path)}
            candidate_blob = patch_symbols(context.blob, context.layout, changed)
            counters['leaves'] += 1
            modeled = context.render(frame, path)
            counters['suffix_samples'] += context.n - frame * 320
            if not np.array_equal(modeled, sparse.decode_model(candidate_blob)):
                raise AssertionError('Full independent pulse model and carried suffix differ')
            counters['full_model_checks'] += 1
            if candidate_blob not in cache:
                native, duty = _oracle(receiver, candidate_blob, modeled)
                counters['native_oracle_calls'] += 1
                counters['unique_native_leaves'] += 1
                cache[candidate_blob] = Candidate(candidate_blob, native, duty, _sse(target, native),
                                                  frame, path, ordinal)
            cached = cache[candidate_blob]
            leaf = Candidate(candidate_blob, cached.pcm, cached.pwm, cached.pcm_sse, frame, path, ordinal)
            leaves.append(leaf)
            if candidate_blob != context.blob:
                all_changed.setdefault(candidate_blob, leaf)
        controls, survivors = prune_controls(target, context, frame, pools, leaves)
        for width in BEAM_WIDTHS:
            live = 1
            for pool in pools:
                counters['prefix_control_extensions'] += live * len(pool.symbols)
                live = min(width, live * len(pool.symbols))
        regions.append(Region(frame, _sse(target[frame * 320:(frame + 1) * 320],
                                          pcm[frame * 320:(frame + 1) * 320]), pools, leaves,
                              min(leaves, key=lambda c: (c.pcm_sse, c.ordinal)), controls, survivors))
    order = lambda c: (c.pcm_sse, c.region, c.ordinal)
    shortlist = sorted(all_changed.values(), key=order)[:FULL_SHORTLIST]
    control_shortlists = {}
    for width in BEAM_WIDTHS:
        unique = {region.controls[width].blob: region.controls[width] for region in regions
                  if region.controls[width].blob != context.blob}
        control_shortlists[width] = sorted(unique.values(), key=order)
    raw = min(all_changed.values(), key=order) if all_changed else baseline
    return SearchResult(baseline, regions, shortlist, control_shortlists, raw, counters)


def admit(reference, result: SearchResult, *, speech=True):
    """Independent baseline-protected whole-output selection for each topology.

    Reuse existing strict PCM/PWM SSE+STOI, voice/clip and fixed PWM high-band,
    burst/tail floors. Require changed PWM and strict old joint/PWM-joint score
    improvement. Only the prospectively fixed12 exhaustive shortlist candidates
    get full quality scoring; each control has at most4 winners, scored separately.
    Raw changed proposals are retained by search even when every gate rejects.
    """
    from refine_sparse80_pulses import (_measure, _floors, _band_context,
                                         _band_measure, band_error_floors)
    from speech_noise_objective import NoiseObjective
    from standard_metrics import pwm_pcm16
    from voice_character import track_pitch
    target = _reference(reference, len(result.baseline.pcm))
    track = track_pitch(target)
    objective = NoiseObjective(target, track.period)
    bands = _band_context(target)
    baseline = _measure(target, result.baseline.pcm, track, objective, bool(speech))
    floor_bands = _band_measure(bands, pwm_pcm16(result.baseline.pcm))
    selections, journals = {}, {}
    queues = {'exhaustive': result.shortlist,
              **{'beam' + str(width): values for width, values in result.control_shortlists.items()}}
    for topology, candidates in queues.items():
        best, best_metrics = result.baseline, baseline
        entries = []
        for candidate in candidates:
            metrics = _measure(target, candidate.pcm, track, objective, bool(speech))
            freq = _band_measure(bands, pwm_pcm16(candidate.pcm))
            floors = dict(same_complete_bytes=len(candidate.blob) == len(result.baseline.blob),
                          quality=bool(_floors(metrics, baseline)),
                          highband=bool(band_error_floors(freq, floor_bands)),
                          changed_pwm=not np.array_equal(candidate.pwm, result.baseline.pwm),
                          finite=bool(np.isfinite(metrics['score']) and np.isfinite(metrics['pwm_joint_score'])))
            eligible = all(floors.values())
            improves = (metrics['score'] < best_metrics['score'] - 1e-12
                        and metrics['pwm_joint_score'] < best_metrics['pwm_joint_score'] - 1e-12)
            entries.append(dict(region=candidate.region, symbols=list(candidate.symbols),
                                sha256=hashlib.sha256(candidate.blob).hexdigest(),
                                pcm_sse=candidate.pcm_sse, floors=floors, metrics=metrics,
                                selected_at_step=bool(eligible and improves)))
            if eligible and improves:
                best, best_metrics = candidate, metrics
        selections[topology] = best
        journals[topology] = entries
    return selections, dict(baseline=baseline, candidates=journals,
                           scope='Numerical admission only; no audible-quality claim')

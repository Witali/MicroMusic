"""Research-only saved-spectrum proposals; full-output admission is external.

See PROTOCOL.md. Importing this module does not launch any search. The active
encoder dependencies are reused without edits. This bounded operator neither
selects an output nor claims a subjective/global quality optimum.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from numbers import Integral
from pathlib import Path
import sys
import time

import numpy as np

TOOLS = Path(__file__).resolve().parents[2] / '01_ACTIVE_Q0_CODEC/tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
ROUND_TOOLS = Path(__file__).resolve().parents[1] / 'low-bitrate-speech-2026-11-02'
if str(ROUND_TOOLS) not in sys.path:
    sys.path.insert(0, str(ROUND_TOOLS))

import speech_compact as compact
import speech_sparse80 as sparse
import speech_v4
from encode_low_bitrate_speech import search_excitation, spectral_bytes
from q0_model import coefficient_trace, table
from wav_lpc import analyze, pack_frames
from round_admission import RoundAdmission, fields, save


@dataclass(frozen=True)
class Proposal:
    identity: str
    family: str
    spectra: np.ndarray
    exact_layout_bytes: int
    proxy_delta: float
    first_frame: int
    last_frame: int
    index: int
    direction: int
    _context_digest: bytes = field(repr=False)


def _inputs(reference, blob, kbps):
    if isinstance(kbps, bool) or not isinstance(kbps, Integral) or kbps not in (2, 3):
        raise ValueError('Expected the existing exact 2 or 3 kbit/s cap')
    values = np.asarray(reference)
    if (values.ndim != 1 or values.dtype.kind not in 'iu' or not 1 <= len(values) <= 64000
            or int(values.min()) < -32768 or int(values.max()) > 32767 or len(values) % 320):
        raise ValueError('This frozen round requires complete 320-sample PCM16 frames')
    blob = bytes(blob)
    sparse80 = kbps == 2
    n, actual_sparse, spectra, _, _, pre, bright = fields(blob)
    if actual_sparse != sparse80 or not sparse80 and blob[5] & 128:
        raise ValueError('This round only refits sparse80 or plain v5/P4; retain the input unchanged')
    cap = len(values) * kbps // 64
    if n != len(values) or len(blob) > cap or bright != 0:
        raise ValueError('Incumbent count, cap or frozen zero-brightness contract differs')
    vectors = np.array(spectra, dtype=np.int64, copy=True)
    vectors.flags.writeable = False
    target = np.array(values, dtype=np.int16, copy=True)
    target.flags.writeable = False
    return target, blob, vectors, int(pre), sparse80, cap


def _context(target, blob):
    # The private binding is not emitted in metrics, plans or dataclass repr.
    return hashlib.sha256(blob + target.astype('<i2', copy=False).tobytes()).digest()


def _runs(spectra):
    first = 0
    for end in range(1, len(spectra) + 1):
        if end == len(spectra) or not np.array_equal(spectra[end], spectra[first]):
            yield first, end
            first = end


def proposals(reference, blob, kbps):
    """Return at most four immutable changed spectra and anonymous work counts.

    Ranking only allocates the finite refit budget. No audio reconstruction or
    admission is performed here, and the input arrays/bytes are not modified.
    """
    target, blob, spectra, pre, sparse80, cap = _inputs(reference, blob, kbps)
    context = _context(target, blob)
    vectors, _ = analyze(target, pre=pre, bandwidth=.97)
    desired = np.asarray(speech_v4.quantize_spectrum(vectors, 6 if sparse80 else 4), np.int64)
    weights = 1 + np.sqrt(np.mean(target.astype(np.float64).reshape(-1, 320) ** 2, axis=1))
    original_loss = float(np.sum(weights[:, None] * (desired - spectra) ** 2))
    maximum = 63 if sparse80 else 31
    families = {'coordinate': [], 'boundary': []}
    seen = {spectra.tobytes()}
    counts = dict(legal_proposals=0, over_cap=0, duplicate_spectra=0)

    def add(family, trial, first, last, index, direction):
        if (np.any(trial < 0) or np.any(trial > maximum) or np.any(np.diff(trial, axis=1) <= 0)):
            return
        counts['legal_proposals'] += 1
        key = trial.tobytes()
        if key in seen:
            counts['duplicate_spectra'] += 1
            return
        seen.add(key)
        size = spectral_bytes(trial, sparse80)
        if size > cap:
            counts['over_cap'] += 1
            return
        delta = float(np.sum(weights[:, None] * (desired - trial) ** 2)) - original_loss
        owned = np.array(trial, dtype=np.int64, copy=True)
        owned.flags.writeable = False
        families[family].append((delta, size, first, index, direction, last, owned))

    runs = list(_runs(spectra))
    for first, last in runs:
        for index in range(10):
            for direction in (-1, 1):
                trial = spectra.copy()
                trial[first:last, index] += direction
                add('coordinate', trial, first, last, index, direction)
    for (first, middle), (_, last) in zip(runs, runs[1:]):
        for direction in (-1, 1):
            boundary = middle + direction
            if not first < boundary < last:
                continue
            trial = spectra.copy()
            trial[boundary:middle] = spectra[middle]
            trial[middle:boundary] = spectra[middle - 1]
            add('boundary', trial, first, last, middle, direction)
    for family in families:
        families[family].sort(key=lambda item: item[:6])
    selected = {family: items[:2] for family, items in families.items()}
    for family in ('coordinate', 'boundary'):
        available = 4 - sum(len(items) for items in selected.values())
        if available:
            selected[family].extend(families[family][2:2 + available])
    result = []
    for family in ('coordinate', 'boundary'):
        for delta, size, first, index, direction, last, trial in selected[family]:
            result.append(Proposal('spectral-%02d' % len(result), family, trial, size,
                                   delta, first, last, index, direction, context))
    return result, dict(schema='lpx-saved-spectrum-round-v1', complete_byte_cap=cap,
        runs=len(runs), shortlisted_refits=len(result), source_lpc_bandwidth=.97,
        whole_input_level_changed=False, **counts)


def refit(reference, incumbent_blob, kbps, proposal, source_lags):
    """Return one complete changed stream/expected PCM and full attempt counts.

    The coordinator must retain the exact incumbent and pass every return value
    through independent whole-output model/native/quality admission. Even if a
    returned stream duplicates another attempt, retain this attempt's work.
    """
    target, incumbent_blob, original, pre, sparse80, cap = _inputs(reference, incumbent_blob, kbps)
    if (not isinstance(proposal, Proposal) or proposal.spectra.shape != original.shape
            or proposal.spectra.dtype.kind not in 'iu' or proposal._context_digest != _context(target, incumbent_blob)):
        raise ValueError('Expected a proposal from this saved-spectrum round')
    spectra = proposal.spectra
    if (np.any(spectra < 0) or np.any(spectra > (63 if sparse80 else 31))
            or np.any(np.diff(spectra, axis=1) <= 0) or spectral_bytes(spectra, sparse80) > cap):
        raise ValueError('Invalid or over-cap spectrum proposal')
    block = 320 if sparse80 else 160
    lags = np.asarray(source_lags)
    if (lags.shape != (len(target) // block,) or lags.dtype.kind not in 'iu'
            or np.any(lags < 0) or np.any(lags > 256)):
        raise ValueError('Supply the frozen source-period lag array for this full refit')
    shift = 4 if sparse80 else 5
    expanded = [[(int(value) << shift) + (1 << (shift - 1)) for value in row]
                for row in spectra for _ in range(2)]
    coefficients = coefficient_trace(pack_frames(expanded), len(target))
    params, pulses, pcm, work = search_excitation(target.astype(np.int64), coefficients,
        table('scale_table.inc'), np.array(lags, dtype=np.int64, copy=True), pre, sparse80, True, True)
    if sparse80:
        blob = sparse.pack(len(target), spectra.tolist(), params.tolist(), pulses.tolist(), pre)
    else:
        blob = compact.pack(len(target), 4, spectra.tolist(), params.tolist(), pulses.tolist(), pre)[0]
    if len(blob) != proposal.exact_layout_bytes or len(blob) > cap:
        raise AssertionError('Actual serialized layout differs or exceeds the frozen complete cap')
    replay_blocks = len(target) // block
    fits = int(work) + replay_blocks
    return blob, pcm, dict(identity=proposal.identity, family=proposal.family,
        file_bytes=len(blob), complete_byte_cap=cap, parameter_trials=int(work),
        selected_block_replays=replay_blocks,
        pulse_position_sign_trials=fits * (512 if sparse80 else 256),
        committed_group_replays=fits * (4 if sparse80 else 8),
        first_frame=proposal.first_frame, last_frame=proposal.last_frame,
        index=proposal.index, direction=proposal.direction, proxy_delta=proposal.proxy_delta,
        admitted=False, scope='Unadmitted full refit; root harness must check exact model/native PCM/PWM and full quality')


def run(reference, incumbent, output, common, only, *, speech=True):
    """Run only when scheduled by the root coordinator after current workers.

    The shared harness owns every metric, gate, native check and checkpoint.
    This module only proposes spectra and refits complete excitation chains.
    """
    _, sparse80, *_ = fields(incumbent)
    kbps = 2 if sparse80 else 3
    target, incumbent, _, _, _, _ = _inputs(reference, incumbent, kbps)
    gate = RoundAdmission(target, incumbent, output, common, only, speech=speech)
    started = time.perf_counter()
    shortlist, plan = proposals(target, incumbent, kbps)
    plan['proposals'] = [dict(identity=item.identity, family=item.family,
        first_frame=item.first_frame, last_frame=item.last_frame, index=item.index,
        direction=item.direction, proxy_delta=item.proxy_delta,
        exact_layout_bytes=item.exact_layout_bytes) for item in shortlist]
    save(gate.output/'spectral-plan-private.json', plan)
    # Exact source-to-block mapping from the frozen active encoder. It adds no
    # mask, forced pitch or neighbor beyond that unchanged refit routine.
    block = 320 if sparse80 else 160
    lags = np.zeros(len(target) // block, np.int64)
    track = gate.track
    for bi in range(len(lags)):
        center = bi * block + block / 2
        if len(track.period):
            index = int(np.argmin(abs(track.sample_center - center)))
            if np.isfinite(track.period[index]):
                lags[bi] = int(np.rint(track.period[index]))
    for proposal in shortlist:
        blob, pcm, metadata = refit(target, incumbent, kbps, proposal, lags)
        work = {key: metadata[key] for key in ('parameter_trials', 'selected_block_replays',
            'pulse_position_sign_trials', 'committed_group_replays')}
        origin = {key: metadata[key] for key in ('identity', 'family', 'first_frame',
            'last_frame', 'index', 'direction', 'proxy_delta')}
        gate.add(blob, pcm, origin=origin, work=work)
    return gate.finish(round='saved_spectrum_coordinate_boundary_v1', proposal_plan=plan,
        seconds=time.perf_counter() - started, whole_input_level_changed=False,
        header_filters_changed=False, decoder_changed=False,
        scope='Finite research round; numerical admission does not establish subjective quality or a global optimum')

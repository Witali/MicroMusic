"""Bounded offline LPX speech search at exact complete-file rate caps.

2 kbit/s uses explicit sparse80 version8/mode15; 3 kbit/s uses existing v5/P4.
Search parameters, spectral updates and innovations run on the host. Every
complete candidate is serialized, saved and checked against the v5 native
reference bridge. This finite search cannot promise a global optimum.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from numbers import Integral
from pathlib import Path
import time

import numpy as np
from numba import njit

import speech_compact as compact
import speech_sparse80 as sparse
import speech_v4
from q0_model import clamp, coefficient_trace, table
from refine_speech_compact import quality, no_regression
from speech_noise_objective import NoiseObjective
from speech_rate_allocation import spectrum_bits
from standard_metrics import pwm_duties, pwm_pcm16
from voice_character import compare_voice, track_pitch
from voice_input import load_voice_wav, prepare_level
from wav_lpc import analyze, pack_frames


class NoSpectralFit(ValueError):
    """This source-derived proposal failed; other proposals/seeds may fit."""


def recover_best_checkpoint(directory):
    """Read the authoritative pointer; ignore unfinished convenience copies."""
    directory = Path(directory)
    pointer = json.loads((directory/'best-private.json').read_text(encoding='utf-8'))
    identifier = pointer['selected_id']
    if isinstance(identifier, bool) or not isinstance(identifier, int) or identifier < 0:
        raise ValueError('Invalid checkpoint candidate ID')
    if pointer['candidate_file'] != 'candidate-%03d.lpx' % identifier:
        raise ValueError('Invalid checkpoint candidate filename')
    blob = (directory/pointer['candidate_file']).read_bytes()
    metadata = (directory/('candidate-%03d-private.json' % identifier)).read_bytes()
    if (hashlib.sha256(blob).hexdigest() != pointer['candidate_sha256']
            or hashlib.sha256(metadata).hexdigest() != pointer['metrics_sha256']):
        raise ValueError('Checkpoint stream or metadata changed')
    row = json.loads(metadata)
    if row['id'] != identifier or not row['admissible'] or row['file_bytes'] != len(blob):
        raise ValueError('Checkpoint metadata is not an admitted complete candidate')
    return blob, row


def _ordered(values, maximum):
    vector = np.clip(np.rint(values), 0, maximum).astype(np.int64)
    for index in range(1, 10):
        vector[index] = max(vector[index], vector[index-1] + 1)
    if vector[-1] > maximum:
        vector[-1] = maximum
        for index in range(8, -1, -1):
            vector[index] = min(vector[index], vector[index+1] - 1)
    return vector


def spectral_bytes(spectra, sparse80):
    profile = 6 if sparse80 else 4
    cost = sum(spectrum_bits(row, None if index == 0 else spectra[index-1], profile)
               for index, row in enumerate(spectra))
    return 22 + (cost + len(spectra) * (43 if sparse80 else 110) + 7) // 8


def spectral_plans(target, desired, max_bytes, sparse80):
    """Return uniform control and adaptive contiguous spectral allocation.

    Merge the least costly adjacent segments until the real Rice-coded complete
    size fits. Segment centers are energy-weighted legal LSF means. This LSF
    proxy only proposes candidates; reconstructed whole speech decides quality.
    Uniform plans remain controls. Complete final packets always count.
    """
    desired = np.asarray(desired, np.int64)
    frames = len(desired)
    uniform = None
    for cadence in range(1, frames + 1):
        trial = np.asarray([desired[(i // cadence) * cadence] for i in range(frames)])
        if spectral_bytes(trial, sparse80) <= max_bytes:
            uniform = trial
            break
    if uniform is None:
        raise NoSpectralFit('No uniform source-derived spectrum fits the complete-file cap')
    weights = np.asarray([1. + np.sqrt(np.mean(np.asarray(target[i*320:(i+1)*320], np.float64)**2))
                          for i in range(frames)])
    maximum = 63 if sparse80 else 31
    segments = [(i, i+1, desired[i].copy()) for i in range(frames)]

    def render(items):
        return np.asarray([center for first, last, center in items for _ in range(first, last)])

    def loss(first, last, center):
        return float(np.sum(weights[first:last, None] * (desired[first:last] - center)**2))

    current = render(segments)
    while spectral_bytes(current, sparse80) > max_bytes and len(segments) > 1:
        proposals = []
        size = spectral_bytes(current, sparse80)
        for index in range(len(segments)-1):
            first, middle, left = segments[index]
            _, last, right = segments[index+1]
            center = _ordered(np.average(desired[first:last], axis=0, weights=weights[first:last]), maximum)
            merged = segments[:index] + [(first, last, center)] + segments[index+2:]
            trial_size = spectral_bytes(render(merged), sparse80)
            if trial_size >= size:
                continue
            delta = loss(first, last, center) - loss(first, middle, left) - loss(middle, last, right)
            proposals.append((delta / (size-trial_size), delta, index, merged))
        if not proposals:
            # A legal fallback remains available even if no single merge saves
            # a padded byte. Do not fake feasibility with an estimated bit cost.
            break
        segments = min(proposals, key=lambda p: p[:3])[3]
        current = render(segments)
    result = [('uniform', uniform)]
    if spectral_bytes(current, sparse80) <= max_bytes and not np.array_equal(current, uniform):
        result.append(('adaptive', current))
    return result


@njit(cache=True)
def trial_group(target, co, hist, dd, cc, ring, start, group, step, lag, gain,
                position, amplitude, pre, clip_guard):
    history, qring = hist.copy(), ring.copy()
    output = np.empty(group, np.int16)
    loss = np.int64(0)
    for j in range(group):
        at = start + j
        q = min(31, max(-32, (gain*qring[(at-lag)&255]+8)>>4))
        q = min(31, max(-32, q + (amplitude if j == position else 0)))
        qring[at&255] = q
        accumulator = np.int64(0)
        for k in range(10):
            accumulator += (co[at, k]*history[k])>>12
        predicted = clamp(q*step-accumulator)
        for k in range(9, 0, -1):
            history[k] = history[k-1]
        history[0] = predicted
        dd = clamp(predicted+((pre*dd)>>14))
        cc = clamp(dd, -16384, 16384)
        output[j] = clamp(cc*2, -32768, 32767)
        difference = np.int64(output[j])-target[at]
        loss += difference*difference
        if clip_guard and (output[j] <= -32768 or output[j] >= 32767):
            # Proposal-only penalty; reported quality always uses unmodified
            # reconstructed audio. One clip outweighs any320-sample SSE.
            loss += np.int64(1) << 42
    return loss, history, dd, cc, qring, output


@njit(cache=True)
def fit_block(target, co, hist, dd, cc, ring, start, group, block, step, lag,
              gain, pre, sparse80, clip_guard):
    history, qring = hist.copy(), ring.copy()
    pulses = np.empty((block//group, 2), np.int64)
    output = np.empty(block, np.int16)
    total = np.int64(0)
    for part in range(block//group):
        at = start+part*group
        best = np.int64(9223372036854775807)
        best_position, best_amplitude = 0, -8
        for code in range(64 if sparse80 else 16):
            position = code+((code+2)>>2)
            for sign in range(2):
                amplitude = -8 if sign == 0 else (7 if sparse80 else 8)
                err, _, _, _, _, _ = trial_group(target, co, history, dd, cc, qring,
                    at, group, step, lag, gain, position, amplitude, pre, clip_guard)
                if err < best:
                    best, best_position, best_amplitude = err, position, amplitude
        err, history, dd, cc, qring, pcm = trial_group(target, co, history, dd, cc, qring,
            at, group, step, lag, gain, best_position, best_amplitude, pre, clip_guard)
        pulses[part, 0], pulses[part, 1] = best_position, best_amplitude
        output[part*group:(part+1)*group] = pcm
        total += err
    return total, history, dd, cc, qring, pulses, output


@njit(cache=True)
def search_excitation(reference, co, steps, source_lags, pre, sparse80, expanded,
                      clip_guard=False):
    n = len(reference)
    group, block = (80, 320) if sparse80 else (20, 160)
    params = np.empty((n//block, 3), np.int64)
    pulses = np.empty((n//group, 2), np.int64)
    output = np.empty(n, np.int16)
    hist, ring = np.zeros(10, np.int64), np.zeros(256, np.int64)
    dd = cc = 0
    emphasized, residual = np.zeros(n, np.float64), np.zeros(n, np.float64)
    for at in range(n):
        emphasized[at] = reference[at]/2 - (pre*(reference[at-1]/2) if at else 0)/16384
        residual[at] = emphasized[at]
        for k in range(10):
            if at > k:
                residual[at] += co[at, k]*emphasized[at-k-1]/4096
    trials = 0
    for bi in range(n//block):
        start, stop = bi*block, (bi+1)*block
        desired = max(1., np.sqrt(np.mean(residual[start:stop]**2)*group)/7.5)
        center = max(1, min(31, int(np.rint((128+16*np.log2(desired/16.384))/8))))
        scores = np.zeros(128, np.float64)
        for candidate in range(18, 146):
            dot = energy = 0.
            for at in range(start, stop):
                value = residual[at-candidate] if at >= candidate else 0.
                dot += value*residual[at]
                energy += value*value
            scores[candidate-18] = max(0., dot)**2/(energy+1.)
        top = np.argmax(scores)+18
        lags = np.full(7, top, np.int64)
        count = 1
        if expanded:
            # Source YIN period is an additional proposal, never a forced
            # decoded pitch. Keep the residual proposal and its tie order.
            for value in (source_lags[bi], source_lags[bi]-1, source_lags[bi]+1):
                if 18 <= value <= 145 and not np.any(lags[:count] == value):
                    lags[count] = value
                    count += 1
            for _ in range(2):
                for index in range(128):
                    if np.any(np.abs(lags[:count]-(index+18)) <= 2):
                        scores[index] = -1
                value = np.argmax(scores)+18
                if not np.any(lags[:count] == value):
                    lags[count] = value
                    count += 1
        best = np.int64(9223372036854775807)
        best_scale, best_lag, best_gain = 0, top, 0
        scales = np.empty(7, np.int64)
        scale_count = 0
        for value in range(max(0, center-2), min(31, center+2)+1):
            scales[scale_count] = value
            scale_count += 1
        for value in (0, 1):
            if not np.any(scales[:scale_count] == value):
                scales[scale_count] = value
                scale_count += 1
        for scale_index in range(scale_count):
            scale = scales[scale_index]
            for li in range(count):
                lag = lags[li]
                for gain in range(0, 15, 2 if clip_guard else 4):
                    # The original four proposals are0/6/10/14. The guarded
                    # branch may use every legal gain without adding a bit.
                    if not clip_guard:
                        gain = 0 if gain == 0 else gain+2
                    if li and gain == 0:
                        continue
                    error, _, _, _, _, _, _ = fit_block(reference, co, hist, dd, cc,
                        ring, start, group, block, steps[scale*8], lag, gain, pre, sparse80, clip_guard)
                    trials += 1
                    if error < best:
                        best, best_scale, best_lag, best_gain = error, scale, lag, gain
        _, hist, dd, cc, ring, pp, pcm = fit_block(reference, co, hist, dd, cc, ring,
            start, group, block, steps[best_scale*8], best_lag, best_gain, pre, sparse80, clip_guard)
        params[bi] = np.asarray([best_scale, best_lag, best_gain])
        pulses[start//group:stop//group] = pp
        output[start:stop] = pcm
    return params, pulses, output, trials


def encode(reference, kbps, decoder, *, output=None, level_policy='preserve',
           pres=(13926, 11469, 8192), bandwidths=(.97, .94), candidate_sink=None,
           seeds=(), speech=True):
    """Return bytes, PCM and anonymous report; save every contender if requested.

    The uniform .97/13926 control is retained. Alternatives must preserve both
    PCM/PWM SSE and STOI, source-bound period tolerance counts and clipping.
    A lower joint voice/noise score then chooses among admitted contenders.
    """
    if isinstance(kbps, bool) or not isinstance(kbps, Integral) or kbps not in (2, 3):
        raise ValueError('Expected exact complete-file cap2 or3kbit/s')
    if (not 1 <= len(pres) <= 3 or any(isinstance(value, bool) or not isinstance(value, Integral)
            or not 0 <= value <= 16384 for value in pres)
            or not 1 <= len(bandwidths) <= 2
            or any(not np.isfinite(value) or not 0 < value <= 1 for value in bandwidths)):
        raise ValueError('Expected bounded valid pre-emphasis/bandwidth proposals')
    target, level = prepare_level(reference, level_policy)
    n = len(target)
    if not 1 <= n <= 64000:
        raise ValueError('Expected1..64000 PCM16 samples')
    sparse80 = kbps == 2
    cap = n*kbps//64
    padded = np.pad(target.astype(np.int64), (0, (-n)%320))
    if output is not None:
        output = Path(output)
        if output.exists():
            raise ValueError('Use a fresh candidate directory')
        output.mkdir(parents=True)
    track = track_pitch(target)
    objective = NoiseObjective(target, track.period)
    group_block = 320 if sparse80 else 160
    source_lags = np.zeros(len(padded)//group_block, np.int64)
    for bi in range(len(source_lags)):
        center = bi*group_block+group_block/2
        if len(track.period):
            index = int(np.argmin(abs(track.sample_center-center)))
            if np.isfinite(track.period[index]):
                source_lags[bi] = int(np.rint(track.period[index]))
    rows, candidates, by_blob, attempts = [], [], {}, []
    spectral_no_fit = []
    seeds_added = False
    started = time.perf_counter()

    def atomic_bytes(name, data):
        path = output/name
        temporary = path.with_name(path.name+'.partial')
        temporary.write_bytes(data)
        temporary.replace(path)

    def allowed(row, baseline):
        return bool(no_regression(row['metrics'], baseline['metrics'])
            and row['clipped_samples'] <= baseline['clipped_samples']
            and all(row[key]['within_tolerance_frames'] >= baseline[key]['within_tolerance_frames']
                    for key in ('voice', 'pwm_voice')))

    def checkpoint(attempt):
        if output is None:
            return
        atomic_bytes('attempt-%03d-private.json' % attempt['id'],
                     (json.dumps(attempt, indent=2)+'\n').encode())
        incumbent = min((entry for entry in rows if entry['admissible']),
            key=lambda entry: (entry['score'], entry['file_bytes'], entry['id']))
        best = candidates[incumbent['id']][0]
        metadata = (output/('candidate-%03d-private.json' % incumbent['id'])).read_bytes()
        # The single pointer commits immutable bytes and metrics together.
        # selected.lpx and the aggregate journal are convenience copies only.
        atomic_bytes('best-private.json', (json.dumps(dict(selected_id=incumbent['id'],
            candidate_file='candidate-%03d.lpx' % incumbent['id'],
            candidate_sha256=hashlib.sha256(best).hexdigest(),
            metrics_sha256=hashlib.sha256(metadata).hexdigest(),
            completed_candidates=len(rows), completed_attempts=len(attempts)), indent=2)+'\n').encode())
        atomic_bytes('selected.lpx', best)
        atomic_bytes('candidates-private.json', (json.dumps(rows, indent=2)+'\n').encode())

    def add(blob, expected, settings, work):
        blob = bytes(blob)
        if len(blob) > cap:
            raise AssertionError('Final serialized candidate exceeds complete rate cap')
        modeled = sparse.decode_model(blob) if sparse80 else compact.decode_model(blob)
        if not np.array_equal(expected[:n], modeled):
            raise AssertionError('Search/model PCM differs')
        fits = int(work)+(len(padded)//group_block if work else 0)
        counters = dict(parameter_trials=int(work),
            selected_block_replays=len(padded)//group_block if work else 0,
            pulse_position_sign_trials=fits*(512 if sparse80 else 256),
            committed_group_replays=fits*(4 if sparse80 else 8))
        attempt = dict(id=len(attempts), settings=settings, work=counters)
        if blob in by_blob:
            attempt['duplicate_of'] = by_blob[blob]
            attempts.append(attempt)
            checkpoint(attempt)
            return
        native_blob = sparse.expand(blob) if sparse80 else blob
        native = decoder.decode_one_s16(native_blob, n)
        duty = decoder.decode_one(native_blob, n)
        if native is None or duty is None or not np.array_equal(native, modeled) or not np.array_equal(duty, pwm_duties(modeled)):
            raise AssertionError('Native bridge/model PCM/PWM differs')
        pwm = pwm_pcm16(modeled)
        voice = [compare_voice(target, result, reference_track=track) for result in (modeled, pwm)]
        score = float(np.mean([objective.voice_objective(result)+objective(result) for result in (modeled, pwm)]))
        row = dict(id=len(rows), settings=settings, file_bytes=len(blob), bitrate_bps=len(blob)*64000/n,
            score=score, metrics=quality(target, modeled, bool(speech)), voice=voice[0], pwm_voice=voice[1],
            clipped_samples=int(np.count_nonzero((modeled <= -32768) | (modeled >= 32767))),
            native_reference_bridge_exact=True, **counters)
        row['admissible'] = allowed(row, rows[0] if rows else row)
        if output is not None:
            atomic_bytes('candidate-%03d.lpx' % row['id'], blob)
            atomic_bytes('candidate-%03d-private.json' % row['id'],
                         (json.dumps(row, indent=2)+'\n').encode())
        rows.append(row)
        candidates.append((blob, modeled))
        by_blob[blob] = row['id']
        attempt['candidate_id'] = row['id']
        attempts.append(attempt)
        checkpoint(attempt)
        if candidate_sink is not None:
            candidate_sink(blob, row)

    def add_seeds():
        nonlocal seeds_added
        if seeds_added:
            return
        seeds_added = True
        for seed in seeds:
            seed = bytes(seed)
            if not sparse80 and compact.unpack(seed)[1] != 4:
                raise ValueError('Expected a retained v5/P4 seed at3kbit/s')
            modeled = sparse.decode_model(seed) if sparse80 else compact.decode_model(seed)
            if len(modeled) != n:
                raise ValueError('Retained seed sample count differs from reference')
            if len(seed) <= cap:
                add(seed, modeled, dict(retained_seed=True), 0)

    for pre in pres:
        for bandwidth in bandwidths:
            vectors, _ = analyze(padded, pre=pre, bandwidth=bandwidth)
            desired = speech_v4.quantize_spectrum(vectors, 6 if sparse80 else 4)
            try:
                plans = spectral_plans(padded, desired, cap, sparse80)
            except NoSpectralFit:
                spectral_no_fit.append(dict(pre_q14=pre, bandwidth=bandwidth))
                continue
            for allocation, spectra in plans:
                shift = 4 if sparse80 else 5
                expanded = [[(int(v)<<shift)+(1<<(shift-1)) for v in row] for row in spectra for _ in range(2)]
                co = coefficient_trace(pack_frames(expanded), len(padded))
                # Keep the cheaper exact uniform control before widening lag
                # proposals. Both get full fresh reconstruction and metrics.
                choices = ((False, False), (True, True)) if not rows else ((True, True),)
                for expanded_lags, clip_guard in choices:
                    params, pulses, pcm, work = search_excitation(padded, co, table('scale_table.inc'),
                        source_lags, pre, sparse80, expanded_lags, clip_guard)
                    if sparse80:
                        blob = sparse.pack(n, spectra.tolist(), params.tolist(), pulses.tolist(), pre)
                    else:
                        blob = compact.pack(n, 4, spectra.tolist(), params.tolist(), pulses.tolist(), pre)[0]
                    add(blob, pcm, dict(pre_q14=pre, bandwidth=bandwidth,
                        allocation=allocation, expanded_lags=expanded_lags, clip_guard=clip_guard), work)
                    if len(rows) == 1:
                        add_seeds()
    if not rows:
        add_seeds()
    if not rows:
        raise NoSpectralFit('No searched spectrum or retained seed fits the complete-file cap')
    selected = min((row for row in rows if row['admissible']), key=lambda row: (row['score'], row['file_bytes'], row['id']))
    blob, pcm = candidates[selected['id']]
    totals = {key: sum(attempt['work'][key] for attempt in attempts) for key in (
        'parameter_trials', 'selected_block_replays', 'pulse_position_sign_trials', 'committed_group_replays')}
    report = dict(schema='lpx-low-bitrate-speech-v2', samples=n, target_kbps=kbps,
        complete_byte_cap=cap, level=level, container_version=8 if sparse80 else 5,
        mode=15 if sparse80 else 4, selected_id=selected['id'], selected_bytes=len(blob),
        baseline_id=0, candidate_count=len(rows), candidates=rows,
        spectral_no_fit_proposals=spectral_no_fit,
        attempt_count=len(attempts), attempts=attempts, actual_work_totals=totals,
        source_voiced_windows=int(track.voiced.sum()), seconds=time.perf_counter()-started,
        selection='minimum joint PCM/PWM voice+noise proxy under unchanged SSE/STOI/pitch/clipping floors',
        scope='Finite bounded offline search; no subjective or realtime quality claim')
    if output is not None:
        recovered, _ = recover_best_checkpoint(output)
        if recovered != blob:
            raise AssertionError('Durable best checkpoint differs from final selection')
        atomic_bytes('selected.lpx', blob)
        atomic_bytes('report-private.json', (json.dumps(report, indent=2)+'\n').encode())
    return blob, pcm, report


def main():
    from batch_decoder import BatchSession
    from pcm16_wav import write_pcm16_wav
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--kbps', type=int, choices=(2, 3), required=True)
    parser.add_argument('--level-policy', choices=('preserve', 'auto-quiet'), default='auto-quiet')
    parser.add_argument('--non-speech', action='store_true')
    args = parser.parse_args()
    reference, input_info = load_voice_wav(args.input, args.level_policy)
    with BatchSession('batch', speech=True, speech_compact=True) as decoder:
        blob, pcm, report = encode(reference, args.kbps, decoder, output=args.output,
                                   level_policy='preserve', speech=not args.non_speech)
    report['input'] = input_info
    report['level'] = input_info['input_level']
    write_pcm16_wav(args.output/'decoded-pcm16.wav', pcm)
    write_pcm16_wav(args.output/'decoded.wav', pwm_pcm16(pcm))
    report['listening_wav_native_pcm_exact'] = True
    report_path = args.output/'report-private.json'
    temporary = report_path.with_name(report_path.name+'.partial')
    temporary.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    temporary.replace(report_path)
    print(json.dumps({key:report[key] for key in ('selected_bytes', 'samples', 'candidate_count', 'selected_id', 'seconds')}))


if __name__ == '__main__':
    main()

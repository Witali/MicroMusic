"""Five preregistered costed scale-ramp attempts; see RAMP_PROTOCOL.md."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from encode_meta320 import (Admission, ACTIVE, BatchDecoder, save, np, njit,
    compact, sparse, ramp, coefficient_trace, table, pack_frames)
from q0_model import clamp
from pcm16_wav import write_pcm16_wav
from standard_metrics import pwm_pcm16
from voice_input import load_voice_wav


@njit(cache=True)
def trial(reference, co, hist, dd, cc, ring, start, group, metadata_start,
          previous_raw, target_raw, lag, gain, position, amplitude, pre, bright, clip_guard):
    history, qring = hist.copy(), ring.copy()
    output = np.empty(group, np.int16)
    previous = target_raw if previous_raw < 0 else previous_raw
    error, step = np.int64(0), target_raw
    for j in range(group):
        at = start+j
        if j%20 == 0:
            k = min(8, (at-metadata_start)//20+1)
            step = (previous*(8-k)+target_raw*k+4)>>3
        q = min(31, max(-32, (gain*qring[(at-lag)&255]+8)>>4))
        q = min(31, max(-32, q+(amplitude if j == position else 0)))
        qring[at&255] = q
        accumulator = np.int64(0)
        for k in range(10):
            accumulator += (co[at, k]*history[k])>>12
        predicted = clamp(q*step-accumulator)
        for k in range(9, 0, -1):
            history[k] = history[k-1]
        history[0] = predicted
        dd = clamp(predicted+((pre*dd)>>14))
        clipped = clamp(dd, -16384, 16384)
        value = clamp(clipped-((bright*cc)>>14), -16384, 16384)
        cc = clipped
        output[j] = clamp(value*2, -32768, 32767)
        delta = np.int64(output[j])-reference[at]
        error += delta*delta
        if clip_guard and (output[j] <= -32768 or output[j] >= 32767):
            error += np.int64(1)<<42
    return error, history, dd, cc, qring, output


@njit(cache=True)
def fit_block(reference, co, hist, dd, cc, ring, start, previous_raw, target_raw,
              lag, gain, pre, bright, sparse80, clip_guard):
    block, group = (320, 80) if sparse80 else (160, 20)
    history, qring = hist.copy(), ring.copy()
    pulses, output = np.empty((block//group, 2), np.int64), np.empty(block, np.int16)
    total = np.int64(0)
    for part in range(block//group):
        at = start+part*group
        best, chosen_position, chosen_amplitude = np.int64(9223372036854775807), 0, -8
        for code in range(64 if sparse80 else 16):
            position = code+((code+2)>>2)
            for sign in range(2):
                amplitude = -8 if sign == 0 else (7 if sparse80 else 8)
                loss, _, _, _, _, _ = trial(reference, co, history, dd, cc, qring, at, group,
                    start, previous_raw, target_raw, lag, gain, position, amplitude, pre, bright, clip_guard)
                if loss < best:
                    best, chosen_position, chosen_amplitude = loss, position, amplitude
        loss, history, dd, cc, qring, pcm = trial(reference, co, history, dd, cc, qring, at, group,
            start, previous_raw, target_raw, lag, gain, chosen_position, chosen_amplitude, pre, bright, clip_guard)
        pulses[part] = np.asarray([chosen_position, chosen_amplitude])
        output[part*group:(part+1)*group] = pcm
        total += loss
    return total, history, dd, cc, qring, pulses, output


@njit(cache=True)
def fixed_next_block(reference, co, hist, dd, cc, ring, start, previous_raw, target_raw,
                     lag, gain, pulses, pre, bright, sparse80, clip_guard):
    block, group = (320, 80) if sparse80 else (160, 20)
    history, qring = hist.copy(), ring.copy()
    loss = np.int64(0)
    for part in range(block//group):
        at = start+part*group
        position, amplitude = pulses[at//group]
        error, history, dd, cc, qring, _ = trial(reference, co, history, dd, cc, qring,
            at, group, start, previous_raw, target_raw, lag, gain, position, amplitude,
            pre, bright, clip_guard)
        loss += error
    return loss


@njit(cache=True)
def search(reference, co, old_params, old_pulses, source_lags, steps, pre, bright,
           sparse80, clip_guard, lookahead):
    block, group = (320, 80) if sparse80 else (160, 20)
    params = np.empty_like(old_params)
    pulses, output = np.empty((len(reference)//group, 2), np.int64), np.empty(len(reference), np.int16)
    history, ring = np.zeros(10, np.int64), np.zeros(256, np.int64)
    dd = cc = 0
    previous_raw, fits, lookahead_samples = -1, 0, 0
    emphasized, residual = np.zeros(len(reference), np.float64), np.zeros(len(reference), np.float64)
    for at in range(len(reference)):
        emphasized[at] = reference[at]/2-(pre*(reference[at-1]/2) if at else 0)/16384
        residual[at] = emphasized[at]
        for k in range(10):
            if at > k:
                residual[at] += co[at, k]*emphasized[at-k-1]/4096
    for bi in range(len(params)):
        start, stop = bi*block, (bi+1)*block
        desired = max(1., np.sqrt(np.mean(residual[start:stop]**2)*group)/7.5)
        center = max(1, min(31, int(np.rint((128+16*np.log2(desired/16.384))/8))))
        scales, ns = np.empty(8, np.int64), 0
        for code in range(max(0, center-2), min(31, center+2)+1):
            scales[ns] = code
            ns += 1
        for code in (0, 1, old_params[bi, 0]):
            if not np.any(scales[:ns] == code):
                scales[ns] = code
                ns += 1
        scores = np.zeros(128, np.float64)
        for lag in range(18, 146):
            dot = energy = 0.
            for at in range(start, stop):
                value = residual[at-lag] if at >= lag else 0.
                dot += value*residual[at]
                energy += value*value
            scores[lag-18] = max(0., dot)**2/(energy+1.)
        lags, nl = np.full(8, np.argmax(scores)+18, np.int64), 1
        for lag in (source_lags[bi], source_lags[bi]-1, source_lags[bi]+1):
            if 18 <= lag <= 145 and not np.any(lags[:nl] == lag):
                lags[nl] = lag
                nl += 1
        for _ in range(2):
            for i in range(128):
                if np.any(np.abs(lags[:nl]-(i+18)) <= 2):
                    scores[i] = -1
            lag = np.argmax(scores)+18
            if not np.any(lags[:nl] == lag):
                lags[nl] = lag
                nl += 1
        if not np.any(lags[:nl] == old_params[bi, 1]):
            lags[nl] = old_params[bi, 1]
            nl += 1
        best, chosen_scale, chosen_lag, chosen_gain = np.int64(9223372036854775807), 0, 18, 0
        for si in range(ns):
            scale = scales[si]
            for li in range(nl):
                for gain in range(0, 15, 2):
                    if li and gain == 0:
                        continue
                    loss, future_h, future_d, future_c, future_ring, _, _ = fit_block(reference, co, history, dd, cc, ring, start,
                        previous_raw, steps[scale*8], lags[li], gain, pre, bright, sparse80, clip_guard)
                    fits += 1
                    if lookahead and bi+1 < len(old_params):
                        next_scale, next_lag, next_gain = old_params[bi+1]
                        loss += fixed_next_block(reference, co, future_h, future_d, future_c,
                            future_ring, stop, steps[scale*8], steps[next_scale*8], next_lag,
                            next_gain, old_pulses, pre, bright, sparse80, clip_guard)
                        lookahead_samples += block
                    if loss < best:
                        best, chosen_scale, chosen_lag, chosen_gain = loss, scale, lags[li], gain
        _, history, dd, cc, ring, pp, pcm = fit_block(reference, co, history, dd, cc, ring, start,
            previous_raw, steps[chosen_scale*8], chosen_lag, chosen_gain, pre, bright, sparse80, clip_guard)
        previous_raw = steps[chosen_scale*8]
        params[bi] = np.asarray([chosen_scale, chosen_lag, chosen_gain])
        pulses[start//group:stop//group] = pp
        output[start:stop] = pcm
    return params, pulses, output, fits, lookahead_samples


def native_references(receipt_path):
    receipt = json.loads(Path(receipt_path).read_text(encoding='utf-8'))
    if not receipt['passed']:
        raise ValueError('Native ramp reference receipt is not verified')
    for name, digest in receipt['source_sha256'].items():
        if Path(name).name != name or hashlib.sha256((ACTIVE/'src'/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Pinned native source differs from current source')
    receivers = []
    for name in ('direct_q0', 'direct_q4'):
        item = receipt['libraries'][name]
        path = Path(item['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256'] or item['assembly']:
            raise ValueError('Pinned native ramp library differs or is not C')
        receivers.append(BatchDecoder(path))
    return receivers, receipt


def preflight(receipt_path):
    """Small exact fitted-state fixture before any real tuning, in one slot."""
    receivers, _ = native_references(receipt_path)
    for mode in (4, 15):
        n = 640
        block, group, shift = (160, 20, 5) if mode == 4 else (320, 80, 4)
        spectra = [[2, 4, 7, 10, 13, 16, 19, 22, 25, 28]]*2
        reference = np.rint(1800*np.sin(2*np.pi*233*np.arange(n)/8000)).astype(np.int64)
        old_params = np.asarray([(8 if i%2 else 16, 34, 10) for i in range(n//block)], np.int64)
        old_pulses = np.asarray([(0, -8)]*(n//group), np.int64)
        lags = np.full(n//block, 34, np.int64)
        vectors = [[(value<<shift)+(1<<(shift-1)) for value in vector]
                   for vector in spectra for _ in range(2)]
        co = coefficient_trace(pack_frames(vectors), n)
        for lookahead in (False, True):
            for clip_guard in (False, True):
                pp, ii, expected, fits, future = search(reference, co, old_params, old_pulses,
                    lags, table('scale_table.inc'), 11469, 4096, mode == 15, clip_guard, lookahead)
                blob = ramp.pack(n, mode, spectra, pp.tolist(), ii.tolist(), 11469, 4096)
                if not np.array_equal(expected, ramp.decode_model(blob)) or fits > 400*(n//block):
                    raise AssertionError('Ramp fitter/model or declared fit bound differs')
                if not lookahead and future:
                    raise AssertionError('Unexpected lookahead work')
                for receiver in receivers:
                    if (not np.array_equal(receiver.decode_one_s16(blob, n), expected)
                            or not np.array_equal(receiver.decode_one(blob, n), __import__('standard_metrics').pwm_duties(expected))):
                        raise AssertionError('Ramp fitter/direct Q0/Q4 C differs')
    native_references(receipt_path)
    return dict(status='PASS', modes=[4, 15], guard_branches=2, lookahead_branches=2,
                samples_per_fixture=640, target_arithmetic_receivers=2)


def run(reference, incumbent, output, receipt_path, speech=True):
    started = time.perf_counter()
    receivers, receipt = native_references(receipt_path)
    if incumbent[4:6] == bytes((8, 15)):
        n, spectra, old_params, old_pulses, pre, bright = sparse.unpack(incumbent)
        mode, block, group, shift = 15, 320, 80, 4
    else:
        n, profile, spectra, old_params, old_pulses, pre, bright, extras = compact.unpack(incumbent)
        if profile != 4 or any(amplitude for _, amplitude in extras):
            raise ValueError('Expected a plain P4 or sparse80 protected incumbent')
        mode, block, group, shift = 4, 160, 20, 5
    if n != len(reference) or n%320:
        raise ValueError('The fitting study requires complete aligned source targets')
    gate = Admission(reference, incumbent, output, *receivers, speech=speech)
    save(gate.output/'native-references-private.json', receipt)
    save(gate.output/'ramp-plan-private.json', dict(mode=mode, new_complete_attempts=5,
        refit_guards=[False, True], next_block_lookahead=[False, True], maximum_scales=8, maximum_lags=7,
        maximum_parameter_fits_per_metadata=400, spectra_and_filters_fixed=True))
    converted = ramp.pack(n, mode, spectra, old_params, old_pulses, pre, bright)
    if converted[:4]+incumbent[4:5]+converted[5:] != incumbent:
        raise AssertionError('Payload-only ramp conversion changed old fields')
    gate.add(converted, origin='payload_only_new_ramp_semantics', work=dict(full_model_reconstructions=1))
    source_lags = np.zeros(n//block, np.int64)
    for bi in range(len(source_lags)):
        if len(gate.track.period):
            index = int(np.argmin(abs(gate.track.sample_center-(bi*block+block/2))))
            if np.isfinite(gate.track.period[index]):
                source_lags[bi] = int(np.rint(gate.track.period[index]))
    vectors = [[(int(value)<<shift)+(1<<(shift-1)) for value in vector]
               for vector in spectra for _ in range(2)]
    co = coefficient_trace(pack_frames(vectors), n)
    for lookahead in (False, True):
        for clip_guard in (False, True):
            pp, ii, expected, fits, future_samples = search(np.asarray(reference, np.int64), co,
                np.asarray(old_params, np.int64), np.asarray(old_pulses, np.int64), source_lags,
                table('scale_table.inc'), pre, bright, mode == 15, clip_guard, lookahead)
            blob = ramp.pack(n, mode, spectra, pp.tolist(), ii.tolist(), pre, bright)
            total_fits = int(fits)+n//block
            gate.add(blob, expected, origin=dict(full_refit=True, clip_guard=clip_guard, next_block_lookahead=lookahead),
                work=dict(parameter_trials=int(fits), selected_block_replays=n//block,
                    pulse_position_sign_trials=total_fits*(block//group)*(128 if mode == 15 else 32),
                    committed_group_replays=total_fits*(block//group),
                    lookahead_sample_renders=int(future_samples), lookahead_group_renders=int(future_samples)//group))
            native_references(receipt_path)
    best = gate.best()
    blob, pcm = gate.candidates[best['id']]
    if __import__('encode_meta320').recover_best_checkpoint(gate.output)[0] != blob:
        raise AssertionError('Recoverable ramp best differs')
    totals = {}
    for attempt in gate.attempts:
        for name, count in attempt['work'].items():
            totals[name] = totals.get(name, 0)+count
    report = dict(schema='lpx-costed-scale-ramp-v1', selected_id=best['id'], selected_is_ramp=best['version'] == 10,
        mode=mode, candidates=gate.rows, attempts=gate.attempts, actual_work_totals=totals,
        admissible_candidate_ids=[row['id'] for row in gate.rows if row['admissible']],
        native_q0_q4_source_pins_verified=True, complete_byte_cap=gate.cap, seconds=time.perf_counter()-started,
        target_cost_measured=False, scope='Fixed source/filter/spectrum ramp tuning; target and heldout checks separate')
    save(gate.output/'report-private.json', report)
    write_pcm16_wav(gate.output/'decoded.wav', pwm_pcm16(pcm))
    return blob, pcm, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('incumbent', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--native-receipt', required=True, type=Path)
    parser.add_argument('--level-policy', choices=('auto-quiet', 'preserve'), default='auto-quiet')
    args = parser.parse_args()
    reference, info = load_voice_wav(args.reference, args.level_policy)
    _, _, report = run(reference, args.incumbent.read_bytes(), args.output, args.native_receipt)
    save(args.output/'input-private.json', info)
    print(json.dumps(dict(selected_id=report['selected_id'], selected_is_ramp=report['selected_is_ramp'],
                         seconds=report['seconds'])), flush=True)


if __name__ == '__main__':
    main()

"""Bounded explicit version9 metadata320 experiment; see PROTOCOL.md.

Run only in a coordinator-reserved slot. All media, logs and detailed metrics
stay under ignored build/. The ordinary v5 incumbent is always protected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

for variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    os.environ[variable] = '1'

ROOT = Path(__file__).resolve().parents[4]
ACTIVE = ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
sys.path.insert(0, str(ACTIVE/'tools'))

import numpy as np
from numba import njit
import speech_compact as compact
import speech_meta320 as meta
import speech_sparse80 as sparse
import speech_scale_ramp as ramp
import speech_v4
from batch_decoder import BatchDecoder
from encode_low_bitrate_speech import fit_block, _ordered, recover_best_checkpoint
from pcm16_wav import write_pcm16_wav
from q0_model import coefficient_trace, table
from refine_speech_compact import quality, no_regression
from speech_noise_objective import NoiseObjective
from speech_rate_allocation import spectrum_bits
from standard_metrics import pwm_duties, pwm_pcm16
from voice_character import compare_voice, track_pitch
from voice_input import load_voice_wav
from wav_lpc import analyze, pack_frames


def layout_bytes(spectra):
    bits = sum(spectrum_bits(vector, None if i == 0 else spectra[i-1], 4)
               for i, vector in enumerate(spectra))
    return 22+(95*len(spectra)+bits+7)//8


def adaptive_spectra(reference, desired, cap):
    """Exact local spectrum-bit costs; proxy proposes, complete audio decides."""
    desired = np.asarray(desired, np.int64)
    weights = 1+np.sqrt(np.mean(np.asarray(reference, np.float64).reshape(-1, 320)**2, axis=1))
    prefix_w = np.r_[0., np.cumsum(weights)]
    prefix_x = np.vstack((np.zeros(10), np.cumsum(weights[:, None]*desired, axis=0)))
    prefix_xx = np.vstack((np.zeros(10), np.cumsum(weights[:, None]*desired**2, axis=0)))

    def center(first, last):
        return _ordered((prefix_x[last]-prefix_x[first])/(prefix_w[last]-prefix_w[first]), 31)

    def loss(first, last, vector):
        w, x, xx = prefix_w[last]-prefix_w[first], prefix_x[last]-prefix_x[first], prefix_xx[last]-prefix_xx[first]
        return float(np.sum(xx-2*vector*x+vector**2*w))

    segments = []
    for i, vector in enumerate(desired):
        if segments and np.array_equal(segments[-1][2], vector):
            segments[-1] = (segments[-1][0], i+1, vector.copy())
        else:
            segments.append((i, i+1, vector.copy()))
    bits = sum(spectrum_bits(vector, None if i == 0 else segments[i-1][2], 4)+last-first-1
               for i, (first, last, vector) in enumerate(segments))
    while 22+(95*len(desired)+bits+7)//8 > cap:
        choices = []
        for i in range(len(segments)-1):
            first, middle, left = segments[i]
            _, last, right = segments[i+1]
            previous = segments[i-1][2] if i else None
            merged = center(first, last)
            old_bits = spectrum_bits(left, previous, 4)+(middle-first-1)+spectrum_bits(right, left, 4)+(last-middle-1)
            new_bits = spectrum_bits(merged, previous, 4)+(last-first-1)
            if i+2 < len(segments):
                following = segments[i+2][2]
                old_bits += spectrum_bits(following, right, 4)
                new_bits += spectrum_bits(following, merged, 4)
            saved = old_bits-new_bits
            if saved > 0:
                delta = loss(first, last, merged)-loss(first, middle, left)-loss(middle, last, right)
                choices.append((delta/saved, delta, i, saved, merged))
        if not choices:
            return None
        _, _, index, saved, merged = min(choices, key=lambda value: value[:3])
        first, _, _ = segments[index]
        _, last, _ = segments[index+1]
        segments[index:index+2] = [(first, last, merged)]
        bits -= saved
    result = np.asarray([vector for first, last, vector in segments for _ in range(first, last)], np.int64)
    if layout_bytes(result) != 22+(95*len(desired)+bits+7)//8:
        raise AssertionError('Local spectrum accounting differs from complete serialization')
    return result


@njit(cache=True)
def search(reference, co, steps, source_lags, old_params, pre):
    """One tuple per320; reuse the unchanged exact20-sample P4 pulse fitter."""
    n = len(reference)
    parameters = np.empty((n//320, 3), np.int64)
    pulses = np.empty((n//20, 2), np.int64)
    output = np.empty(n, np.int16)
    history, ring = np.zeros(10, np.int64), np.zeros(256, np.int64)
    dd = cc = 0
    emphasized, residual = np.zeros(n, np.float64), np.zeros(n, np.float64)
    for at in range(n):
        emphasized[at] = reference[at]/2-(pre*(reference[at-1]/2) if at else 0)/16384
        residual[at] = emphasized[at]
        for k in range(10):
            if at > k:
                residual[at] += co[at, k]*emphasized[at-k-1]/4096
    trials = 0
    for fi in range(n//320):
        start, stop = fi*320, (fi+1)*320
        desired = max(1., np.sqrt(np.mean(residual[start:stop]**2)*20)/7.5)
        center = max(1, min(31, int(np.rint((128+16*np.log2(desired/16.384))/8))))
        scales, count_scales = np.empty(9, np.int64), 0
        for value in range(max(0, center-2), min(31, center+2)+1):
            scales[count_scales] = value
            count_scales += 1
        for value in (0, 1, old_params[fi*2, 0], old_params[fi*2+1, 0]):
            if not np.any(scales[:count_scales] == value):
                scales[count_scales] = value
                count_scales += 1
        scores = np.zeros(128, np.float64)
        for lag in range(18, 146):
            dot = energy = 0.
            for at in range(start, stop):
                value = residual[at-lag] if at >= lag else 0.
                dot += value*residual[at]
                energy += value*value
            scores[lag-18] = max(0., dot)**2/(energy+1.)
        lags, count_lags = np.full(9, np.argmax(scores)+18, np.int64), 1
        for value in (source_lags[fi], source_lags[fi]-1, source_lags[fi]+1):
            if 18 <= value <= 145 and not np.any(lags[:count_lags] == value):
                lags[count_lags] = value
                count_lags += 1
        for _ in range(2):
            for i in range(128):
                if np.any(np.abs(lags[:count_lags]-(i+18)) <= 2):
                    scores[i] = -1
            value = np.argmax(scores)+18
            if not np.any(lags[:count_lags] == value):
                lags[count_lags] = value
                count_lags += 1
        for value in (old_params[fi*2, 1], old_params[fi*2+1, 1]):
            if not np.any(lags[:count_lags] == value):
                lags[count_lags] = value
                count_lags += 1
        best, selected_scale, selected_lag, selected_gain = np.int64(9223372036854775807), 0, 18, 0
        for si in range(count_scales):
            scale = scales[si]
            for li in range(count_lags):
                lag = lags[li]
                for gain in range(0, 15, 2):
                    if li and gain == 0:
                        continue
                    error, _, _, _, _, _, _ = fit_block(reference, co, history, dd, cc, ring,
                        start, 20, 320, steps[scale*8], lag, gain, pre, False, True)
                    trials += 1
                    if error < best:
                        best, selected_scale, selected_lag, selected_gain = error, scale, lag, gain
        _, history, dd, cc, ring, pp, pcm = fit_block(reference, co, history, dd, cc, ring,
            start, 20, 320, steps[selected_scale*8], selected_lag, selected_gain, pre, False, True)
        parameters[fi] = np.asarray([selected_scale, selected_lag, selected_gain])
        pulses[fi*16:(fi+1)*16] = pp
        output[start:stop] = pcm
    return parameters, pulses, output, trials


def atomic(path, data):
    pending = path.with_name(path.name+'.partial')
    pending.write_bytes(data)
    pending.replace(path)


def save(path, value):
    atomic(path, (json.dumps(value, indent=2, allow_nan=False)+'\n').encode())


class Admission:
    """Same output guards across ordinary v5 and the explicit new container."""
    def __init__(self, reference, incumbent, output, common, only, speech=True):
        self.output = Path(output).resolve()
        self.output.relative_to((ROOT/'build').resolve())
        if self.output.exists():
            raise ValueError('Use a fresh ignored prototype directory')
        self.output.mkdir(parents=True)
        self.reference = np.array(reference, np.int16, copy=True)
        self.reference.flags.writeable = False
        self.budget_kbps = 2 if incumbent[4] in (8, 10) and incumbent[5] == 15 else 3
        self.cap = len(reference)*self.budget_kbps//64
        self.incumbent, self.common, self.only, self.speech = incumbent, common, only, speech
        self.track = track_pitch(reference)
        self.objective = NoiseObjective(reference, self.track.period)
        self.rows, self.attempts, self.candidates, self.seen = [], [], [], {}
        self.add(incumbent, origin='protected_ordinary_v5_incumbent')

    def add(self, blob, expected=None, origin=None, work=None):
        blob, work = bytes(blob), {} if work is None else dict(work)
        candidate_mode = None
        if blob[4] == 10:
            n, candidate_mode, spectra, _, _, _, _ = ramp.unpack(blob)
            bridge, version = blob, 10
        elif blob[4:6] == bytes((8, 15)):
            n, spectra, _, _, _, _ = sparse.unpack(blob)
            bridge, version = sparse.expand(blob), 8
        elif blob[4:6] == bytes((9, 3)):
            n, spectra, _, _, _, _ = meta.unpack(blob)
            bridge, version = meta.expand(blob), 9
        else:
            n, profile, spectra, _, _, _, _, extras = compact.unpack(blob)
            if profile != 4 or any(amplitude for _, amplitude in extras):
                raise ValueError('Expected ordinary P4 or explicit version9')
            bridge, version = blob, 5
        if (n != len(self.reference) or len(blob) > self.cap
                or self.budget_kbps == 2 and not (version == 8 or version == 10 and candidate_mode == 15)
                or self.budget_kbps == 3 and not (version in (5, 9) or version == 10 and candidate_mode == 4)):
            raise ValueError('Candidate changed count or complete byte cap')
        modeled = ramp.decode_model(bridge) if version == 10 else compact.decode_model(bridge)
        if expected is not None and not np.array_equal(expected, modeled):
            raise AssertionError('Search and independent model differ')
        attempt = dict(id=len(self.attempts), origin=origin, work={key: int(value) for key, value in work.items()})
        if any(value < 0 for value in attempt['work'].values()):
            raise ValueError('Negative work counter')
        if blob in self.seen:
            attempt['duplicate_of'] = self.seen[blob]
            self.attempts.append(attempt)
            save(self.output/('attempt-%03d-private.json' % attempt['id']), attempt)
            return
        for receiver in (self.common, self.only):
            if (not np.array_equal(receiver.decode_one_s16(bridge, n), modeled)
                    or not np.array_equal(receiver.decode_one(bridge, n), pwm_duties(modeled))):
                raise AssertionError('Common/v5-only native bridge differs')
        pwm = pwm_pcm16(modeled)
        voice = [compare_voice(self.reference, output, reference_track=self.track) for output in (modeled, pwm)]
        score = float(np.mean([self.objective.voice_objective(output)+self.objective(output) for output in (modeled, pwm)]))
        row = dict(id=len(self.rows), origin=origin, file_bytes=len(blob), version=version, score=score,
            spectrum_updates=1+sum(first != second for first, second in zip(spectra, spectra[1:])),
            metrics=quality(self.reference, modeled, self.speech), voice=voice[0], pwm_voice=voice[1],
            clipped_samples=int(np.count_nonzero((modeled <= -32768) | (modeled >= 32767))),
            native_common_v5_only_model_pcm_pwm_exact=True)
        baseline = self.rows[0] if self.rows else row
        row['admissible'] = bool(no_regression(row['metrics'], baseline['metrics'])
            and row['clipped_samples'] <= baseline['clipped_samples']
            and all(row[key]['within_tolerance_frames'] >= baseline[key]['within_tolerance_frames'] for key in ('voice', 'pwm_voice')))
        metadata = (json.dumps(row, indent=2, allow_nan=False)+'\n').encode()
        atomic(self.output/('candidate-%03d.lpx' % row['id']), blob)
        atomic(self.output/('candidate-%03d-private.json' % row['id']), metadata)
        self.rows.append(row)
        self.candidates.append((blob, modeled))
        self.seen[blob] = row['id']
        attempt['candidate_id'] = row['id']
        self.attempts.append(attempt)
        save(self.output/('attempt-%03d-private.json' % attempt['id']), attempt)
        selected = self.best()
        best = self.candidates[selected['id']][0]
        selected_metadata = (self.output/('candidate-%03d-private.json' % selected['id'])).read_bytes()
        save(self.output/'best-private.json', dict(selected_id=selected['id'],
            candidate_file='candidate-%03d.lpx' % selected['id'], candidate_sha256=hashlib.sha256(best).hexdigest(),
            metrics_sha256=hashlib.sha256(selected_metadata).hexdigest()))
        atomic(self.output/'selected.lpx', best)

    def best(self):
        return min((row for row in self.rows if row['admissible']), key=lambda row: (row['score'], row['file_bytes'], row['id']))


def run(reference, incumbent, output, common, only, speech=True):
    started = time.perf_counter()
    n, profile, old_spectra, old_params, _, old_pre, old_bright, extras = compact.unpack(incumbent)
    if n != len(reference) or n % 320 or profile != 4 or old_bright or any(amplitude for _, amplitude in extras):
        raise ValueError('Prototype requires exact aligned ordinary P4 target with zero brightness')
    gate = Admission(reference, incumbent, output, common, only, speech)
    source_lags = np.zeros(n//320, np.int64)
    for i in range(len(source_lags)):
        if len(gate.track.period):
            at = int(np.argmin(abs(gate.track.sample_center-(i*320+160))))
            if np.isfinite(gate.track.period[at]):
                source_lags[i] = int(np.rint(gate.track.period[at]))
    proposals, skipped, seen = [], [], set()

    def propose(pre, spectra, origin):
        spectra = np.asarray(spectra, np.int64)
        key = pre, spectra.tobytes()
        size = layout_bytes(spectra)
        if size > gate.cap:
            skipped.append(dict(origin=origin, reason='complete_cap', file_bytes=size))
        elif key in seen:
            skipped.append(dict(origin=origin, reason='duplicate_header_spectrum'))
        else:
            seen.add(key)
            proposals.append((pre, spectra.copy(), origin))

    propose(old_pre, old_spectra, dict(family='incumbent_spectra'))
    for pre in (13926, 11469, 8192):
        for bandwidth in (.97, .94):
            vectors, _ = analyze(reference, pre=pre, bandwidth=bandwidth, window=256)
            desired = np.asarray(speech_v4.quantize_spectrum(vectors, 4), np.int64)
            for cadence in (1, 2, 4, 8):
                spectra = np.asarray([desired[(i//cadence)*cadence] for i in range(len(desired))])
                propose(pre, spectra, dict(family='uniform', cadence=cadence, pre_q14=pre, bandwidth=bandwidth))
            spectra = adaptive_spectra(reference, desired, gate.cap)
            if spectra is not None:
                propose(pre, spectra, dict(family='adaptive', pre_q14=pre, bandwidth=bandwidth))
    save(gate.output/'plan-private.json', dict(maximum_new_full_candidates=31, actual_distinct_proposals=len(proposals),
        proposals=[dict(id=i, origin=origin, file_bytes=layout_bytes(spectra),
            spectrum_updates=1+int(np.count_nonzero(np.any(spectra[1:] != spectra[:-1], axis=1))))
            for i, (_, spectra, origin) in enumerate(proposals)], skipped=skipped,
        counter_scope='Every actual complete fit; duplicate proposals skipped before fitting'))
    for pre, spectra, origin in proposals:
        vectors = [[(int(value)<<5)+16 for value in vector] for vector in spectra for _ in range(2)]
        co = coefficient_trace(pack_frames(vectors), n)
        params, pulses, pcm, fits = search(np.asarray(reference, np.int64), co, table('scale_table.inc'),
            source_lags, np.asarray(old_params, np.int64), pre)
        blob = meta.pack(n, spectra.tolist(), params.tolist(), pulses.tolist(), pre)
        if len(blob) != layout_bytes(spectra):
            raise AssertionError('Final serialized complete size differs')
        total_fits = int(fits)+n//320
        gate.add(blob, pcm, origin, dict(parameter_trials=int(fits), selected_block_replays=n//320,
            pulse_position_sign_trials=total_fits*512, committed_group_replays=total_fits*16))
        row = gate.rows[-1]
        print(json.dumps(dict(stage='complete_candidate', candidate=row['id'], bytes=len(blob),
            origin=origin, admitted=row['admissible'], stoi=row['metrics']['pwm8']['stoi'],
            spectrum_updates=row['spectrum_updates'])), flush=True)
    selected = gate.best()
    blob, pcm = gate.candidates[selected['id']]
    if recover_best_checkpoint(gate.output)[0] != blob:
        raise AssertionError('Recovered best differs')
    totals = {}
    for attempt in gate.attempts:
        for key, value in attempt['work'].items():
            totals[key] = totals.get(key, 0)+value
    report = dict(schema='lpx-meta320-host-pilot-v1', selected_id=selected['id'],
        selected_is_new_format=selected['version'] == 9, complete_byte_cap=gate.cap,
        candidates=gate.rows, attempts=gate.attempts, actual_work_totals=totals,
        admissible_candidate_ids=[row['id'] for row in gate.rows if row['admissible']],
        source_period_frames=gate.rows[0]['voice']['reference_period_frames'], seconds=time.perf_counter()-started,
        decoder_cost_measured=False, scope='Bread tuning only; target cost and heldout admission are separate')
    save(gate.output/'report-private.json', report)
    write_pcm16_wav(gate.output/'decoded.wav', pwm_pcm16(pcm))
    return blob, pcm, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('incumbent', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--common', required=True, type=Path)
    parser.add_argument('--v5-only', required=True, type=Path)
    parser.add_argument('--level-policy', choices=('auto-quiet', 'preserve'), default='auto-quiet')
    args = parser.parse_args()
    reference, input_info = load_voice_wav(args.reference, args.level_policy)
    common, only = BatchDecoder(args.common), BatchDecoder(args.v5_only)
    # A small independent numerical fixture precedes any tuning work. It is
    # not a quality search point and cannot influence candidate settings.
    fixture = np.rint(1800*np.sin(2*np.pi*233*np.arange(640)/8000)).astype(np.int64)
    fixture_spectra = [[2, 4, 7, 10, 13, 16, 19, 22, 25, 28]]*2
    fixture_co = coefficient_trace(pack_frames([[(v<<5)+16 for v in vector]
        for vector in fixture_spectra for _ in range(2)]), 640)
    pp, ii, expected, _ = search(fixture, fixture_co, table('scale_table.inc'),
        np.asarray([34, 34], np.int64), np.asarray([(10, 34, 10)]*4, np.int64), 11469)
    fixture_blob = meta.pack(640, fixture_spectra, pp.tolist(), ii.tolist(), 11469)
    if not np.array_equal(expected, meta.decode_model(fixture_blob)):
        raise AssertionError('Synthetic meta320 fit/model differs')
    for receiver in (common, only):
        if (not np.array_equal(receiver.decode_one_s16(meta.expand(fixture_blob), 640), expected)
                or not np.array_equal(receiver.decode_one(meta.expand(fixture_blob), 640), pwm_duties(expected))):
            raise AssertionError('Synthetic meta320 fit/native differs')
    print(json.dumps(dict(stage='synthetic_kernel_contract', status='PASS', samples=640)), flush=True)
    _, _, report = run(reference, args.incumbent.read_bytes(), args.output, common, only)
    save(args.output/'input-private.json', input_info)
    print(json.dumps(dict(stage='finished', selected_id=report['selected_id'],
        selected_is_new_format=report['selected_is_new_format'], seconds=report['seconds'])))


if __name__ == '__main__':
    main()

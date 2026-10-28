"""Opt-in v5 pitch-directed excitation reseed with exact integer lookahead.

This produces a raw alternative, not an automatically admitted improvement.
The caller supplies reliable source-period lags and owns whole-record quality
selection. Existing encoder defaults, spectrum, filters, extras and MCU stay
unchanged. Analysis and fitting use the original PCM level and complete length.
"""
from __future__ import annotations

import time
import math

import numpy as np
from numba import njit

from enhance_speech_compact import advance, sse
from q0_model import coefficient_trace, table
import speech_compact as compact
from standard_metrics import pwm_duties
from wav_lpc import pack_frames


@njit(cache=True)
def _local_cost(target, output, lag, periodicity_weight):
    error = sse(target, output)
    if not periodicity_weight or not lag or len(output) <= lag:
        return float(error)
    # Source-frozen delay: the candidate cannot evade this term by losing F0.
    power = 0.
    mean = 0.
    for index in range(len(target)):
        power += float(target[index]) * target[index]
        mean += float(output[index])
    mean /= len(output)
    difference = left_power = right_power = 0.
    for index in range(lag, len(output)):
        left = float(output[index - lag]) - mean
        right = float(output[index]) - mean
        difference += (right - left) * (right - left)
        left_power += left * left
        right_power += right * right
    denominator = left_power + right_power
    periodicity = difference / denominator if denominator > 0 else 1.
    return error / max(float(len(target)), power) + periodicity_weight * periodicity


@njit(cache=True)
def _fit(reference, co, params, pulses, extras, steps, pre, bright, profile,
         source_lags, gain, horizon, periodicity_weight):
    parameters = params.copy()
    innovations = pulses.copy()
    history = np.zeros(10, np.int64)
    ring = np.zeros(256, np.int64)
    dd = cc = evaluations = changed_pulses = changed_parameters = 0
    for at in range(0, len(reference), 20):
        if at % 160 == 0:
            block = at // 160
            lag = source_lags[block]
            if lag:
                if parameters[block, 1] != lag or gain >= 0 and parameters[block, 2] != gain:
                    changed_parameters += 1
                parameters[block, 1] = lag
                if gain >= 0:
                    parameters[block, 2] = gain
        stop = min(len(reference), at + horizon)
        target = reference[at:stop]
        index = at // 20
        old_position, old_amplitude = innovations[index]
        best_position, best_amplitude = old_position, old_amplitude
        output, _, _, _, _ = advance(co, parameters, innovations, extras,
                                     steps, pre, bright, at, stop,
                                     history, dd, cc, ring)
        lag = source_lags[at // 160]
        best_loss = _local_cost(target, output, lag, periodicity_weight)
        evaluations += 1
        for position_index in range(16 if profile == 4 else 20):
            position = (position_index + (position_index + 2) // 4
                        if profile == 4 else position_index)
            if at + position >= len(reference):
                continue
            for amplitude_index in range(2 if profile == 4 else 16):
                amplitude = (-8 if amplitude_index == 0 else 8) if profile == 4 else amplitude_index - 8
                if position == old_position and amplitude == old_amplitude:
                    continue
                innovations[index, 0] = position
                innovations[index, 1] = amplitude
                output, _, _, _, _ = advance(co, parameters, innovations, extras,
                                             steps, pre, bright, at, stop,
                                             history, dd, cc, ring)
                loss = _local_cost(target, output, lag, periodicity_weight)
                evaluations += 1
                if loss < best_loss:
                    best_loss = loss
                    best_position, best_amplitude = position, amplitude
        innovations[index, 0] = best_position
        innovations[index, 1] = best_amplitude
        if best_position != old_position or best_amplitude != old_amplitude:
            changed_pulses += 1
        _, history, dd, cc, ring = advance(
            co, parameters, innovations, extras, steps, pre, bright,
            at, min(len(reference), at + 20), history, dd, cc, ring)
    return parameters, innovations, evaluations, changed_parameters, changed_pulses


def reseed(reference, blob, decoder, *, source_lags, horizon=160, gain=14,
           periodicity_weight=0.):
    """Return (raw v5 alternative, exact PCM16, numeric work/scope report).

    source_lags has one integer per audible 160-sample block. Zero retains the
    existing pitch tuple; 18..145 sets a supplied source-period lag and gain.
    gain=None retains each original gain instead of forcing one common gain.
    periodicity_weight>0 adds an explicit proposal-only fixed-delay difference
    penalty to level-relative local MSE. Vanished/constant output pays a unit
    periodicity error; no candidate pitch tracker participates in ranking.
    Lags must come from a separately validated source analysis; this API does
    not reinterpret an unreliable pitch estimate as a voiced frame. It never
    clips an out-of-range source period into the codec's valid lag interval.

    Every audible base-pulse decision uses bounded exact synthesis lookahead.
    Future fields not yet fitted remain from the input stream. No intermediate
    local decision is a whole-record quality gate. The full candidate can trade
    off old SSE/STOI and must be evaluated by the caller before adoption.
    """
    if isinstance(horizon, bool) or not isinstance(horizon, (int, np.integer)) or horizon not in (40, 80, 160, 320, 640):
        raise ValueError('Expected horizon in 40/80/160/320/640')
    if gain is not None and (isinstance(gain, bool) or not isinstance(gain, (int, np.integer)) or not 0 <= gain <= 14 or gain & 1):
        raise ValueError('Expected None or even gain in 0..14')
    if isinstance(periodicity_weight, bool) or not isinstance(periodicity_weight, (int, float, np.integer, np.floating)) or not math.isfinite(periodicity_weight) or not 0 <= periodicity_weight <= 64:
        raise ValueError('Expected finite periodicity_weight in 0..64')
    ref = np.asarray(reference)
    if ref.ndim != 1 or ref.dtype.kind not in 'iu' or np.any(ref < -32768) or np.any(ref > 32767):
        raise ValueError('Expected mono PCM16 reference')
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        raise ValueError('Expected a complete v5 byte stream')
    original = bytes(blob)
    n, profile, spectra, params, pulses, pre, bright, extras = compact.unpack(original)
    if len(ref) != n:
        raise ValueError('Reference/stream length mismatch')
    lags = np.asarray(source_lags)
    if (lags.shape != ((n + 159) // 160,) or lags.dtype.kind not in 'iu'
            or np.any((lags != 0) & ((lags < 18) | (lags > 145)))):
        raise ValueError('Expected one source lag per audible block: 0 or 18..145')
    begin = time.perf_counter()
    shift = 5 if profile == 4 else 4
    vectors = [[(value << shift) + (1 << (shift - 1)) for value in row]
               for row in spectra for _ in range(2)]
    coefficients = coefficient_trace(pack_frames(vectors[:(n + 159) // 160]), n)
    parameters = np.asarray(params, np.int64)
    innovations = np.asarray(pulses, np.int64)
    extra_array = np.asarray(extras, np.int64)
    steps = table('scale_table.inc')
    baseline = compact.decode_model(original)
    native = decoder.decode_one_s16(original, n)
    if native is None or not np.array_equal(native, baseline):
        raise AssertionError('Initial native/model output mismatch')
    fitted_params, fitted_pulses, evaluations, parameter_changes, pulse_changes = _fit(
        ref.astype(np.int64), coefficients, parameters, innovations, extra_array,
        steps, pre, bright, profile, lags.astype(np.int64),
        -1 if gain is None else int(gain), int(horizon), float(periodicity_weight))
    result, _ = compact.pack(n, profile, spectra, fitted_params, fitted_pulses,
                             pre, bright, extras=extras,
                             force_extras=bool(original[5] & 128))
    if len(result) > len(original):
        raise AssertionError('Frozen-spectrum/extras reseed grew serialized data')
    decoded = compact.decode_model(result)
    actual = decoder.decode_one_s16(result, n)
    if actual is None or not np.array_equal(actual, decoded):
        raise AssertionError('Reseed native/model PCM mismatch')
    actual_pwm = decoder.decode_one(result, n)
    if actual_pwm is None or not np.array_equal(actual_pwm, pwm_duties(decoded)):
        raise AssertionError('Reseed native/model PWM mismatch')
    fields = compact.unpack(result)
    if (fields[:3] != (n, profile, spectra) or fields[5:] != (pre, bright, extras)
            or fields[3][(n + 159) // 160:] != params[(n + 159) // 160:]
            or fields[4][(n + 19) // 20:] != pulses[(n + 19) // 20:]):
        raise AssertionError('Frozen fields or mandatory stored tail changed')
    return result, decoded, {
        'proposal': 'source_pitch_excitation_reseed', 'raw_alternative': True,
        'quality_adopted': False, 'profile': profile, 'samples': n,
        'original_bytes': len(original), 'file_bytes': len(result),
        'horizon_samples': int(horizon), 'supplied_pitch_blocks': int(np.count_nonzero(lags)),
        'forced_gain': None if gain is None else int(gain), 'candidate_evaluations': int(evaluations),
        'local_periodicity_weight': float(periodicity_weight),
        'changed_parameter_blocks': int(parameter_changes), 'changed_base_pulses': int(pulse_changes),
        'spectra_filters_extras_and_stored_tail_preserved': True,
        'native_model_pcm_pwm_exact': True, 'decoder_modified': False,
        'original_level_and_length': True,
        'seconds': time.perf_counter() - begin,
    }

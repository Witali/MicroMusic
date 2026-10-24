"""Independent exact HQ4 arithmetic audit and optional continuous pulse phase.

This does not modify the legacy oracle. Continuous phase starts at the first
frame's period, then retains the pulse countdown across later frame updates.
"""
import numpy as np
from numba import njit


@njit
def signed(value):
    return ((value+128)&255)-128


@njit
def multiply(value, coefficient):
    a = signed(value)
    if coefficient < 0:
        a = signed(-a)
    return signed((a*abs(coefficient)) >> 4)


@njit
def render(frames, durations, continuous):
    n = int(np.sum(durations))
    out = np.empty(n, np.uint8)
    excitation = np.empty(n, np.int16)
    pulses = np.zeros(n, np.uint8)
    boundaries = np.zeros(n, np.uint8)
    states = np.zeros(8, np.int32)
    coefficients = np.zeros(8, np.int32)
    # sub-wraps, state-add-wraps, neg(-128), fractional products, products,
    # phase resets, period changes, moved countdown total, total quantization
    # error*16, lowest intermediate, highest intermediate.
    counts = np.zeros(11, np.int64)
    seed, phase, fi, next_t = 0xa7, int(frames[0, 0]), 0, int(durations[0])-1
    period, gain, mode = 0, 0, 0
    for t in range(n):
        if t == 0 or t == next_t:
            if t:
                fi += 1
                if fi == len(frames):
                    fi = 0
                next_t += int(durations[fi])
                boundaries[t] = 1
            old_period = period
            period = int(frames[fi, 0])
            gain, mode = int(frames[fi, 1]) & 15, (int(frames[fi, 1]) >> 4) & 3
            if t and period != old_period:
                counts[6] += 1
            if not continuous:
                if t and period:
                    counts[5] += 1
                    counts[7] += abs(phase-period)
                phase = period
            for j in range(4):
                value = int(frames[fi, 2+j])
                coefficients[j*2] = (value & 15)-8
                coefficients[j*2+1] = (value >> 4)-8
        ex = 0
        if period:
            phase = (phase-1) & 255
            if not phase:
                phase = period
                ex = 2*gain
                pulses[t] = 1
            else:
                lag = period-phase
                if lag == 1:
                    ex = gain*(3-(mode & 1))
                elif lag == 2:
                    ex = gain*(2-(mode >> 1))
                elif lag == 3:
                    ex = -gain
        else:
            low = seed & 1
            seed >>= 1
            if low:
                seed ^= 0xb8
            ex = -gain if seed & 1 else gain
        excitation[t] = ex
        for j in range(7, -1, -1):
            old, coefficient = states[j], coefficients[j]
            for which in range(2 if j < 7 else 1):
                value = old if which == 0 else ex
                if value == -128 and coefficient < 0:
                    counts[2] += 1
                product = value*coefficient
                rounded = multiply(value, coefficient)
                counts[3] += int(product % 16 != 0)
                counts[4] += 1
                counts[8] += rounded*16-product
                if which == 0:
                    raw = ex-rounded
                    counts[0] += int(raw < -128 or raw > 127)
                    ex = signed(raw)
                else:
                    raw = old+rounded
                    counts[1] += int(raw < -128 or raw > 127)
                    states[j+1] = signed(raw)
                counts[9] = min(counts[9], raw)
                counts[10] = max(counts[10], raw)
        states[0] = ex
        out[t] = (ex+128) & 255
    return out, excitation, pulses, boundaries, counts


def decode(frames, durations, continuous=True):
    return render(frames, durations, continuous)[0]


def audit(frames, durations, continuous=False):
    pcm, excitation, pulses, boundaries, counts = render(frames, durations, continuous)
    intervals = np.diff(np.flatnonzero(pulses))
    return dict(samples=len(pcm), subtraction_wraps=int(counts[0]), state_addition_wraps=int(counts[1]),
                negative_128_multiplication=int(counts[2]), fractional_products=int(counts[3]),
                multiplication_count=int(counts[4]), quantization_error_mean=float(counts[8]/16/max(1, counts[4])),
                minimum_intermediate=int(counts[9]), maximum_intermediate=int(counts[10]),
                frame_phase_restarts=int(counts[5]), period_changes=int(counts[6]),
                displaced_countdown_samples=int(counts[7]),
                positive_pulse_events=int(np.sum(pulses)),
                pulse_interval_median=float(np.median(intervals)) if len(intervals) else None,
                pulse_interval_minimum=int(np.min(intervals)) if len(intervals) else None,
                pulse_interval_maximum=int(np.max(intervals)) if len(intervals) else None,
                extreme_pwm_samples=int(np.sum((pcm == 0) | (pcm == 255))),
                peak_signed=int(np.max(abs(pcm.astype(np.int16)-128))))

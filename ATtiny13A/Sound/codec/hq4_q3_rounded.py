"""Isolated Q3 lattice with nearest products, ties toward positive infinity.

All byte wrapping, excitation, frame phase resets and T1 rules match hq4_q3.
Only the product rule changes from floor(product/8) to floor((product+4)/8).
The AVR uses the last discarded carry and its already-zero r27 for one ADC.
Signed -128 negation deliberately retains the original AVR byte behavior.
Encoders must still exclude coefficient -8 and reject audited wraps.
"""
import numpy as np
from numba import njit


@njit(cache=True)
def signed(value):
    return ((value+128)&255)-128


@njit(cache=True)
def multiply(value, coefficient):
    a = signed(value)
    if coefficient < 0:
        a = signed(-a)
    return signed((a*abs(coefficient)+4) >> 3)


@njit(cache=True)
def render(frames, durations, tilt_shift=0):
    n = int(np.sum(durations))
    out = np.empty(n, np.uint8)
    states = np.zeros(8, np.int32)
    coefficients = np.zeros(8, np.int32)
    counts = np.zeros(4, np.int64)  # subtraction, state addition, -128 negation, tilt
    seed, phase, fi, next_t = 0xa7, 1, 0, int(durations[0])-1
    period = gain = mode = previous = 0
    for t in range(n):
        if t == 0 or t == next_t:
            if t:
                fi += 1
                if fi == len(frames):
                    fi = 0
                next_t += int(durations[fi])
            period = int(frames[fi, 0])
            gain, mode = int(frames[fi, 1]) & 15, (int(frames[fi, 1]) >> 4) & 3
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
        for j in range(7, -1, -1):
            old, coefficient = states[j], coefficients[j]
            counts[2] += int(old == -128 and coefficient < 0)
            raw = ex-multiply(old, coefficient)
            counts[0] += int(raw < -128 or raw > 127)
            ex = signed(raw)
            if j < 7:
                counts[2] += int(ex == -128 and coefficient < 0)
                raw = old+multiply(ex, coefficient)
                counts[1] += int(raw < -128 or raw > 127)
                states[j+1] = signed(raw)
        states[0] = ex
        if tilt_shift:
            raw = ex+previous-(previous >> tilt_shift)
            counts[3] += int(raw < -128 or raw > 127)
            previous = signed(raw)
            ex = previous
        out[t] = (ex+128) & 255
    return out, counts


def decode(frames, durations, tilt_shift=0):
    return render(frames, durations, tilt_shift)[0]

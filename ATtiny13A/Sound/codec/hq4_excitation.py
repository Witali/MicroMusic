"""Exact integer experiment: dilate the voiced source pulse, retain HQ4 data.

This changes excitation before the lattice, independently of optional output
tilt. Each of the four pulse samples lasts 1, 2 or 4 samples. The unvoiced
LFSR and original frame/phase conventions remain unchanged.
"""
import numpy as np
from numba import njit
from model import mul_q4


@njit(cache=True)
def decode(frames, durations, pulse_shift=0, fourth=-1, tilt_shift=0):
    n = int(np.sum(durations))
    out = np.empty(n, np.uint8)
    state = np.zeros(8, np.int32)
    k = np.zeros(8, np.int32)
    seed = 0xa7
    phase = 1
    fi = 0
    next_t = int(durations[0])-1
    previous = wraps = 0
    for t in range(n):
        if t == 0 or t == next_t:
            if t:
                fi += 1
                if fi >= len(frames):
                    fi = 0
                next_t += int(durations[fi])
            period = int(frames[fi, 0])
            gain = int(frames[fi, 1]) & 15
            mode = (int(frames[fi, 1]) >> 4) & 3
            phase = period
            for j in range(4):
                value = int(frames[fi, 2+j])
                k[j*2] = (value & 15)-8
                k[j*2+1] = (value >> 4)-8
        ex = 0
        if period:
            phase = (phase-1) & 255
            if phase == 0:
                phase = period
                lag = 0
            else:
                lag = (period-phase) >> pulse_shift
            if lag == 0:
                ex = 2*gain
            elif lag == 1:
                ex = gain*(3-(mode & 1))
            elif lag == 2:
                ex = gain*(2-(mode >> 1))
            elif lag == 3:
                ex = fourth*gain
        else:
            low = seed & 1
            seed >>= 1
            if low:
                seed ^= 0xb8
            ex = -gain if seed & 1 else gain
        ex &= 255
        for j in range(7, -1, -1):
            old, coef = state[j], k[j]
            ex = (ex-int(mul_q4(old, coef))) & 255
            if j < 7:
                state[j+1] = (old+int(mul_q4(ex, coef))) & 255
        state[0] = ex
        value = ex if ex < 128 else ex-256
        if tilt_shift:
            value += previous-(previous >> tilt_shift)
            wraps += int(value < -128 or value > 127)
            previous = ((value+128) & 255)-128
            value = previous
        out[t] = (value+128) & 255
    return out, wraps


def code_bytes(pulse_shift=0, fourth=-1, tilt_shift=0):
    """Engineering source-instruction estimate; no candidate was AVR-qualified."""
    # The original decoder is 406. Dilation adds LSR(s) and BREQ first sample.
    # Removing sample four removes CPI/BREQ, MOV/NEG/RJMP: ten bytes.
    return (406+(2*pulse_shift+2 if pulse_shift else 0)
            -(10 if fourth == 0 else 0)+(10+2*tilt_shift if tilt_shift else 0))

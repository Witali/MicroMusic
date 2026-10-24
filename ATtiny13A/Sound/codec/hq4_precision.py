"""Experimental nearest-product rounding for the original eight-bit HQ4 lattice.

The retained decoder floors signed products. This independent variant adds
half a Q4 unit before the shift, reducing its negative rounding bias. It does
not change excitation, pitch, phase conventions or intentional byte wrapping.
"""
import numpy as np
from numba import njit


@njit(cache=True)
def multiply(value, coefficient, nearest):
    sample = ((value+128)&255)-128
    if coefficient < 0:
        sample = ((-sample+128)&255)-128
    return ((sample*abs(coefficient)+(8 if nearest else 0)) >> 4)&255


@njit(cache=True)
def decode_precision(frames, durations, nearest=True):
    n = int(np.sum(durations))
    output = np.empty(n, np.uint8)
    state = np.zeros(8, np.int32)
    coefficients = np.zeros(8, np.int32)
    seed, period, gain, phase, mode = 0xa7, 0, 0, 1, 0
    fi, next_t = 0, int(durations[0])-1
    for t in range(n):
        if t == 0 or t == next_t:
            if t != 0:
                fi += 1
                if fi >= len(frames):
                    fi = 0
                next_t += int(durations[fi])
            period, gain = int(frames[fi, 0]), int(frames[fi, 1])&15
            mode = (int(frames[fi, 1]) >> 4)&3
            phase = period
            for j in range(4):
                data = int(frames[fi, 2+j])
                coefficients[j*2], coefficients[j*2+1] = (data&15)-8, (data >> 4)-8
        excitation = 0
        if period:
            phase = (phase-1)&255
            if phase == 0:
                phase = period
                excitation = (2*gain)&255
            else:
                lag = period-phase
                if lag == 1:
                    excitation = gain*(3-(mode&1))&255
                elif lag == 2:
                    excitation = gain*(2-(mode >> 1))&255
                elif lag == 3:
                    excitation = (-gain)&255
        else:
            low = seed&1
            seed >>= 1
            if low:
                seed ^= 0xb8
            excitation = (-gain if seed&1 else gain)&255
        for j in range(7, -1, -1):
            old, coefficient = state[j], coefficients[j]
            excitation = (excitation-multiply(old, coefficient, nearest))&255
            if j < 7:
                state[j+1] = (old+multiply(excitation, coefficient, nearest))&255
        state[0] = excitation
        output[t] = (excitation+128)&255
    return output

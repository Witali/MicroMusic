"""Exact-byte Q3/T1 lattice with four selectable 16-sample pulse templates.

All 64 signed table entries fit EEPROM. Existing two mode bits select a row;
frame packing, phase resets, noise and filter arithmetic remain unchanged.
This oracle is separate from the approved public profiles.
"""
import numpy as np
from numba import njit
from hq4_core import pack_stream

SCHEMA = 'hq4-q3-pulsebook-v1'


def legacy_tables():
    table = np.zeros((4,16), np.int8)
    for mode in range(4):
        table[mode,:4] = [2,3-(mode & 1),2-(mode >> 1),-1]
    return table


def validate(frames, durations, pulsebook, samples=None, stream_budget=None):
    f, d, book = np.asarray(frames), np.asarray(durations), np.asarray(pulsebook)
    if (f.ndim != 2 or f.shape[1] != 6 or not len(f) or f.dtype.kind not in 'ui'
            or d.shape != (len(f),) or d.dtype.kind not in 'ui' or np.any(f > 255)
            or np.any(f[:,0] > 126) or np.any(f[:,1] > 63)
            or np.any((f[:,2:] & 15) == 0) or np.any((f[:,2:] >> 4) == 0)
            or not np.all(np.isin(d,[64,128,192,256]))):
        raise ValueError('Invalid stable Q3 pulsebook frames/durations')
    if book.shape != (4,16) or book.dtype.kind not in 'iu' or np.any(book < -7) or np.any(book > 7):
        raise ValueError('Pulsebook must contain exactly64 signed entries in−7..7')
    if samples is not None and int(d.sum()) != samples:
        raise ValueError('Pulsebook model must preserve full reference duration')
    payload = pack_stream(f,d)
    if stream_budget is not None and len(payload) > stream_budget:
        raise ValueError('Packed stream exceeds the actual assembler profile budget')
    return payload


@njit(cache=True)
def signed(value):
    return ((value+128)&255)-128


@njit(cache=True)
def multiply(value, coefficient, nearest):
    value = signed(value)
    if coefficient < 0:
        value = signed(-value)
    return signed((value*abs(coefficient)+(4 if nearest else 0)) >> 3)


@njit(cache=True)
def render(frames, durations, pulsebook, tilt_shift=1, nearest=False):
    output = np.empty(int(durations.sum()),np.uint8)
    states, coefficients = np.zeros(8,np.int32),np.zeros(8,np.int32)
    counts = np.zeros(4,np.int64)
    seed, phase, frame, next_t = 0xa7,1,0,int(durations[0])-1
    period = gain = mode = previous = 0
    for t in range(len(output)):
        if t == 0 or t == next_t:
            if t:
                frame += 1
                if frame == len(frames):
                    frame = 0
                next_t += int(durations[frame])
            period = int(frames[frame,0])
            gain, mode = int(frames[frame,1]) & 15,(int(frames[frame,1]) >> 4) & 3
            phase = period
            for j in range(4):
                value = int(frames[frame,2+j])
                coefficients[j*2],coefficients[j*2+1] = (value & 15)-8,(value >> 4)-8
        ex = 0
        if period:
            phase = (phase-1)&255
            if not phase:
                phase = period
                ex = int(pulsebook[mode,0])*gain
            else:
                lag = period-phase
                if lag < 16:
                    ex = int(pulsebook[mode,lag])*gain
        else:
            low = seed & 1
            seed >>= 1
            if low:
                seed ^= 0xb8
            ex = -gain if seed & 1 else gain
        for j in range(7,-1,-1):
            old, coefficient = states[j],coefficients[j]
            counts[2] += int(old == -128 and coefficient < 0)
            raw = ex-multiply(old,coefficient,nearest)
            counts[0] += int(raw < -128 or raw > 127)
            ex = signed(raw)
            if j < 7:
                counts[2] += int(ex == -128 and coefficient < 0)
                raw = old+multiply(ex,coefficient,nearest)
                counts[1] += int(raw < -128 or raw > 127)
                states[j+1] = signed(raw)
        states[0] = ex
        if tilt_shift:
            raw = ex+previous-(previous >> tilt_shift)
            counts[3] += int(raw < -128 or raw > 127)
            previous = signed(raw)
            ex = previous
        output[t] = (ex+128)&255
    return output, counts

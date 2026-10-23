"""Exact Q3 pulsebook with a per-wave binary voiced-noise selector.

Each of the 64 EEPROM bytes stores coefficient+8 in bits0..3 and a
row-constant noise flag in bit4. The original shared LFSR clocks once on
every flagged voiced sample, including gains0/1, or once on unvoiced samples.
This separately tagged research format never reinterprets older EEPROM data.
"""
import numpy as np
from numba import njit
import q3_pulsebook as base

SCHEMA = 'hq4-q3-pulsebook-mixed-v1'


def encode_book(coefficients, noise_flags):
    values, flags = np.asarray(coefficients), np.asarray(noise_flags)
    if (values.shape != (4,16) or values.dtype.kind not in 'iu'
            or np.any(values < -7) or np.any(values > 7)
            or flags.shape != (4,) or not np.all(np.isin(flags,[0,1]))):
        raise ValueError('Expected 4x16 coefficients in -7..7 and four binary noise flags')
    return ((values.astype(np.int16)+8)|(flags.astype(np.int16)[:,None]<<4)).astype(np.int8)


def decode_book(encoded):
    values = np.asarray(encoded)
    if (values.shape != (4,16) or values.dtype.kind not in 'iu'
            or np.any(values < 1) or np.any(values > 31)
            or np.any((values & 15) == 0)
            or np.any((values >> 4) != (values[:,0] >> 4)[:,None])):
        raise ValueError('Expected 64 encoded coefficients and a uniform noise flag per row')
    return ((values & 15)-8).astype(np.int8),(values[:,0] >> 4).astype(np.uint8)


def legacy_tables():
    return encode_book(base.legacy_tables(),np.zeros(4,np.uint8))


def validate(frames, durations, pulsebook, samples=None, stream_budget=None):
    coefficients,_ = decode_book(pulsebook)
    return base.validate(frames,durations,coefficients,samples,stream_budget)


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
            gain,mode = int(frames[frame,1]) & 15,(int(frames[frame,1]) >> 4) & 3
            phase = period
            for j in range(4):
                value = int(frames[frame,2+j])
                coefficients[j*2],coefficients[j*2+1] = (value & 15)-8,(value >> 4)-8
        ex = 0
        if period:
            phase = (phase-1)&255
            if not phase:
                phase = period
                ex = ((int(pulsebook[mode,0]) & 15)-8)*gain
            else:
                lag = period-phase
                if lag < 16:
                    ex = ((int(pulsebook[mode,lag]) & 15)-8)*gain
            if int(pulsebook[mode,0]) & 16:
                low = seed & 1
                seed >>= 1
                if low:
                    seed ^= 0xb8
                ex += -(gain >> 1) if seed & 1 else gain >> 1
        else:
            low = seed & 1
            seed >>= 1
            if low:
                seed ^= 0xb8
            ex = -gain if seed & 1 else gain
        for j in range(7,-1,-1):
            old,coefficient = states[j],coefficients[j]
            counts[2] += int(old == -128 and coefficient < 0)
            raw = ex-base.multiply(old,coefficient,nearest)
            counts[0] += int(raw < -128 or raw > 127)
            ex = base.signed(raw)
            if j < 7:
                counts[2] += int(ex == -128 and coefficient < 0)
                raw = old+base.multiply(ex,coefficient,nearest)
                counts[1] += int(raw < -128 or raw > 127)
                states[j+1] = base.signed(raw)
        states[0] = ex
        if tilt_shift:
            raw = ex+previous-(previous >> tilt_shift)
            counts[3] += int(raw < -128 or raw > 127)
            previous = base.signed(raw)
            ex = previous
        output[t] = (ex+128)&255
    return output,counts

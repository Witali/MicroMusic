"""Exact PC-only Q3 source with selectable two-tap colored voiced noise.

The64-byte EEPROM book encodes coefficient+8 in low4 bits, and a uniform
row noise mode in bits4..5:0 off,1 low-pass,2 high-pass,3 white. Bits6..7
are reserved zero. This module makes no claim about AVR code size/timing.
"""
import numpy as np
from numba import njit
from q3_pulsebook import signed,multiply,validate as validate_base,legacy_tables as legacy_coefficients

SCHEMA = 'hq4-q3-shaped-noise-v1'


def encode_book(coefficients, noise_modes):
    c,m = np.asarray(coefficients),np.asarray(noise_modes)
    if c.shape != (4,16) or c.dtype.kind not in 'iu' or np.any(c < -7) or np.any(c > 7):
        raise ValueError('Expected4x16 integer coefficients in−7..7')
    if m.shape != (4,) or m.dtype.kind not in 'iu' or np.any(m < 0) or np.any(m > 3):
        raise ValueError('Expected four integer noise modes in0..3')
    return ((c.astype(np.int16)+8)|(m.astype(np.int16)[:,None] << 4)).astype(np.uint8)


def decode_book(encoded):
    b = np.asarray(encoded)
    if b.shape != (4,16) or b.dtype.kind not in 'iu' or np.any(b < 0) or np.any(b > 63):
        raise ValueError('Expected4x16 encoded EEPROM bytes with reserved upper bits zero')
    if np.any((b & 15) == 0) or np.any((b >> 4) != (b[:,0] >> 4)[:,None]):
        raise ValueError('Expected nonzero coefficient nibbles and one uniform noise mode per row')
    return ((b & 15).astype(np.int16)-8).astype(np.int8),(b[:,0] >> 4).astype(np.uint8)


def legacy_tables():
    return encode_book(legacy_coefficients(),np.zeros(4,np.uint8))


def pack_book(encoded):
    decode_book(encoded)
    return np.asarray(encoded,dtype=np.uint8).tobytes()


def unpack_book(payload):
    if not isinstance(payload,(bytes,bytearray,memoryview)) or len(payload) != 64:
        raise ValueError('Expected exactly64 packed EEPROM bytes')
    book = np.frombuffer(payload,dtype=np.uint8).reshape(4,16).copy()
    decode_book(book)
    return book


def validate(frames,durations,pulsebook,samples=None,stream_budget=None):
    f = np.asarray(frames)
    if f.dtype.kind not in 'iu' or np.any(f < 0) or np.any(f > 255):
        raise ValueError('Invalid raw integer frames before narrowing')
    coefficients,_ = decode_book(pulsebook)
    return validate_base(f,durations,coefficients,samples,stream_budget)


@njit(cache=True)
def render(frames, durations, pulsebook, tilt_shift=1, nearest=False):
    output = np.empty(int(durations.sum()),np.uint8)
    states, coefficients = np.zeros(8,np.int32),np.zeros(8,np.int32)
    counts = np.zeros(4,np.int64)
    seed, phase, frame, next_t = 0xa7,1,0,int(durations[0])-1
    previous_noise = 0
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
                ex = ((int(pulsebook[mode,0]) & 15)-8)*gain
            else:
                lag = period-phase
                if lag < 16:
                    ex = ((int(pulsebook[mode,lag]) & 15)-8)*gain
            noise_mode = (int(pulsebook[mode,0]) >> 4) & 3
            if noise_mode:
                low = seed & 1
                seed >>= 1
                if low:
                    seed ^= 0xb8
                current_noise = -(gain >> 1) if seed & 1 else gain >> 1
                if noise_mode == 1:
                    ex += (current_noise+previous_noise) >> 1
                elif noise_mode == 2:
                    ex += (current_noise-previous_noise) >> 1
                else:
                    ex += current_noise
                previous_noise = current_noise
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

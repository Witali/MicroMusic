"""Explicit version10 raw-step ramp; old payloads, deliberately new synthesis.

Mode4 carries plain v5/P4 fields; mode15 carries sparse80 fields. A payload
adapter is only a parser convenience, not an arithmetic-equivalent expansion.
"""
from __future__ import annotations

import numpy as np
from numba import njit

import speech_compact as compact
import speech_sparse80 as sparse
from q0_model import clamp, coefficient_trace, table
from wav_lpc import pack_frames


def pack(n, mode, spectra, params, pulses, pre=13926, bright=0):
    if mode == 4:
        ordinary = compact.pack(n, 4, spectra, params, pulses, pre, bright)[0]
    elif mode == 15:
        ordinary = sparse.pack(n, spectra, params, pulses, pre, bright)
    else:
        raise ValueError('Expected scale-ramp mode4 or15')
    return ordinary[:4]+b'\x0a'+ordinary[5:]


def payload_adapter(blob):
    """Return old-syntax bytes for parsing only; their output is different."""
    if len(blob) < 22 or blob[4] != 10 or blob[5] not in (4, 15):
        raise ValueError('Unsupported scale-ramp version or mode')
    return blob[:4]+bytes((5 if blob[5] == 4 else 8,))+blob[5:]


def unpack(blob):
    ordinary = payload_adapter(blob)
    if blob[5] == 4:
        n, profile, spectra, params, pulses, pre, bright, extras = compact.unpack(ordinary)
        if profile != 4 or any(amplitude for _, amplitude in extras):
            raise ValueError('Scale-ramp mode4 has no optional extras')
        return n, 4, spectra, params, pulses, pre, bright
    n, spectra, params, pulses, pre, bright = sparse.unpack(ordinary)
    return n, 15, spectra, params, pulses, pre, bright


def raw_step_trace(blob, stored=False):
    """One exact raw step per20-sample phase, before optional Q4 caching."""
    n, mode, _, params, _, _, _ = unpack(blob)
    per_metadata = 8 if mode == 4 else 16
    steps = table('scale_table.inc')
    result = []
    previous = None
    for scale, _, _ in params:
        target = int(steps[int(scale)*8])
        if previous is None:
            previous = target
        for phase in range(1, per_metadata+1):
            k = min(phase, 8)
            result.append((previous*(8-k)+target*k+4)>>3)
        previous = target
    return np.asarray(result if stored else result[:(n+19)//20], np.int64)


@njit(cache=True)
def synthesize_raw_steps(q, raw_steps, coefficients, pre, bright):
    """Independent Q0 recurrence with the new exact per20 raw-step schedule."""
    history = np.zeros(10, np.int64)
    output = np.empty(len(q), np.int16)
    deemphasis = previous_clip = 0
    for at in range(len(q)):
        accumulator = np.int64(0)
        for k in range(10):
            accumulator += (coefficients[at, k]*history[k])>>12
        predicted = clamp(q[at]*raw_steps[at//20]-accumulator)
        for k in range(9, 0, -1):
            history[k] = history[k-1]
        history[0] = predicted
        deemphasis = clamp(predicted+((pre*deemphasis)>>14))
        clipped = clamp(deemphasis, -16384, 16384)
        value = clamp(clipped-((bright*previous_clip)>>14), -16384, 16384)
        previous_clip = clipped
        output[at] = clamp(value*2, -32768, 32767)
    return output


def decode_model(blob):
    n, mode, spectra, params, pulses, pre, bright = unpack(blob)
    shift, block, group = (5, 160, 20) if mode == 4 else (4, 320, 80)
    vectors = [[(int(value)<<shift)+(1<<(shift-1)) for value in vector]
               for vector in spectra for _ in range(2)]
    coefficients = coefficient_trace(pack_frames(vectors[:(n+159)//160]), n)
    q = np.empty(n, np.int64)
    for at in range(n):
        _, lag, gain = params[at//block]
        position, amplitude = pulses[at//group]
        previous = int(q[at-lag]) if at >= lag else 0
        predicted = min(31, max(-32, (int(gain)*previous+8)>>4))
        q[at] = min(31, max(-32, predicted+(int(amplitude) if at%group == int(position) else 0)))
    return synthesize_raw_steps(q, raw_step_trace(blob), coefficients, pre, bright)

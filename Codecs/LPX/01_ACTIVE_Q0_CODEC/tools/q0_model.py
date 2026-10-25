"""Host arithmetic model of the frozen default LPX4 Q0 decoder.

Ported from src/Lpx4HybridCore.cpp: LPX3_LPC_SEGMENTS=2, no bandwidth
expansion, no PWM. This is an encoder aid, never firmware. Differential
tests must establish PCM16 equality with the original C++ core.
"""
from pathlib import Path
import re
import numpy as np
from numba import njit
from rice_v7 import absolute_lsf10

ROOT = Path(__file__).resolve().parents[1]


def table(name):
    text = (ROOT / 'src' / name).read_text().split('\n', 1)[1]
    return np.asarray([int(v) for v in re.findall(r'-?\b\d+\b', text)], dtype=np.int64)


@njit(cache=True)
def cdiv(a, b):
    return a // b if a >= 0 else -((-a) // b)


@njit(cache=True)
def clamp(v, lo=-32767, hi=32767):
    return min(hi, max(lo, v))


def coefficient_trace(frames, samples):
    """Exact default Q12 interpolation, including C division toward zero."""
    cosine = table('cos_table.inc')

    def poly_mul(v, c):
        if -250000 <= v <= 250000:
            return (v * c) >> 12
        hi = int(cdiv(v, 16))
        return ((hi * c) >> 8) + (((v - hi * 16) * c) >> 12)

    def anchor(prev, cur, t):
        polynomials = [[4096, 4096] + [0] * 10, [4096, -4096] + [0] * 10]
        for i in range(10):
            norm = (prev[i] * (16 - t) + cur[i] * t) >> 2
            idx, frac = norm >> 4, norm & 15
            c = -(int(cosine[idx]) + ((int(cosine[idx + 1] - cosine[idx]) * frac) >> 4))
            p, n = polynomials[i % 2], 2 + (i // 2) * 2
            p[n + 1] = p[n - 1]
            p[n] = p[n - 2] + poly_mul(p[n - 1], c)
            for j in range(n - 1, 1, -1):
                p[j] = p[j - 2] + poly_mul(p[j - 1], c) + p[j]
            p[1] = poly_mul(p[0], c) + p[1]
        return [int(clamp(cdiv(polynomials[0][i + 1] + polynomials[1][i + 1], 2))) for i in range(10)]

    if samples < 1 or len(frames) != (samples + 159) // 160:
        raise ValueError('LPC frame count does not match sample count')
    vectors, cur = [], None
    for frame in frames:
        if frame[0] == 5:
            cur = list(absolute_lsf10(frame[1:]))
        elif frame[0] == 6 and cur is not None:
            cur = [v + (d - 256 if d >= 128 else d) for v, d in zip(cur, frame[1:])]
        elif frame[0] != 0 or cur is None:
            raise ValueError('Invalid LSF frame sequence')
        if len(cur) != 10 or any(v < 0 or v > 1023 for v in cur):
            raise ValueError('LSF out of range')
        vectors.append(cur.copy())
    result = np.empty((samples, 10), dtype=np.int64)
    for fi, cur in enumerate(vectors):
        prev = vectors[max(0, fi - 1)]
        endpoints = [anchor(prev, cur, t) for t in (0, 8, 16)]
        for sub in range(8):
            a, b = endpoints[sub // 4:sub // 4 + 2]
            local = (sub * 2 + 1) % 8
            row = [int(clamp(x + cdiv((y - x) * local, 8))) for x, y in zip(a, b)]
            start = fi * 160 + sub * 20
            result[start:min(start + 20, samples)] = row
    return result


@njit(cache=True)
def synthesize(q, scales, co, steps, pre, bright):
    history = np.zeros(10, np.int64)
    out = np.empty(len(q), np.int16)
    deemph = previous_clip = 0
    for j in range(len(q)):
        acc = 0
        for k in range(10):
            acc += (co[j, k] * history[k]) >> 12
        pred = clamp(q[j] * steps[scales[j // 80]] - acc)
        for k in range(9, 0, -1):
            history[k] = history[k - 1]
        history[0] = pred
        deemph = clamp(pred + ((pre * deemph) >> 14))
        clipped = clamp(deemph, -16384, 16384)
        b = clamp(clipped - ((bright * previous_clip) >> 14), -16384, 16384)
        previous_clip = clipped
        out[j] = clamp(b * 2, -32768, 32767)
    return out


def decode_pcm16(blob):
    from lpx4 import decode
    frames, blocks, q = decode(blob)
    return synthesize(np.asarray(q, dtype=np.int64),
                      np.asarray([b['scale'] for b in blocks], dtype=np.int64),
                      coefficient_trace(frames, len(q)), table('scale_table.inc'),
                      int.from_bytes(blob[12:14], 'little'), int.from_bytes(blob[14:16], 'little'))

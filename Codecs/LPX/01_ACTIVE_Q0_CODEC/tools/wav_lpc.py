"""Automatic LPC/LSF analysis for the host WAV encoder.

Adapted from analyzeLpcWindow, levinsonDurbin, reflectionToLpc, lpcToLsf,
stabilizeLsf in ../../02_HISTORICAL_FOUNDATIONS/
LPX3_Original_Encoder_Decoder/lpc2_v2_reference.html (import manifest).
The same Hamming/autocorrelation, reflection clamp and trigonometric root
scan are retained. No pitch classifier, browser or legacy speech data needed.
"""
import math
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


def load_wav(path):
    audio, rate = sf.read(str(path), dtype='float64', always_2d=True)
    if not len(audio) or rate < 1 or not np.isfinite(audio).all():
        raise ValueError('WAV must contain finite audio samples')
    channels = audio.shape[1]
    audio = np.mean(audio, axis=1)
    if rate != 8000:
        divisor = math.gcd(rate, 8000)
        audio = resample_poly(audio, 8000 // divisor, rate // divisor)
    clipped = int(np.count_nonzero((audio < -1) | (audio > 32767 / 32768)))
    pcm = np.clip(np.rint(audio * 32768), -32768, 32767).astype(np.int16)
    return pcm, {'input_rate': rate, 'input_channels': channels,
                 'output_samples': len(pcm), 'clipped_input_samples': clipped}


def lpc_to_lsf(a):
    p = len(a) - 1
    grid = np.r_[1e-6, np.pi * np.arange(1, 641) / 641]
    values = (np.exp(-1j * grid[:, None] * np.arange(p + 1)) @ a) * np.exp(1j * grid * (p + 1) / 2)
    roots = []
    for component in (np.real, np.imag):
        v = component(values)
        for i in np.flatnonzero(v[:-1] * v[1:] <= 0):
            lo, hi, flo = grid[i], grid[i + 1], v[i]
            for _ in range(24):
                mid = (lo + hi) / 2
                z = component(np.dot(a, np.exp(-1j * mid * np.arange(p + 1))) * np.exp(1j * mid * (p + 1) / 2))
                if flo * z <= 0:
                    hi = mid
                else:
                    lo, flo = mid, z
            w = (lo + hi) / 2
            if 1e-4 < w < np.pi - 1e-4:
                roots.append(w / np.pi)
    return np.sort(roots) if len(roots) == p else None


def analyze(pcm, pre=13926, window=256, bandwidth=1.):
    if not len(pcm) or not 0 <= pre <= 16384 or window < 160 or not 0 < bandwidth <= 1:
        raise ValueError('Invalid LPC analysis parameters')
    x = np.asarray(pcm, dtype=np.float64) / 32768
    emphasized = x - (pre / 16384) * np.r_[0, x[:-1]]
    result, fallbacks = [], 0
    for start in range(0, len(x), 160):
        indices = np.arange(start + 80 - window // 2, start + 80 + (window + 1) // 2)
        buf = np.zeros(window)
        inside = (indices >= 0) & (indices < len(x))
        buf[inside] = emphasized[indices[inside]]
        buf = (buf - np.mean(buf)) * np.hamming(window)
        r = np.asarray([np.dot(buf[lag:], buf[:window - lag]) for lag in range(11)])
        a = np.r_[1., np.zeros(10)]
        error = max(r[0], 1e-10)
        for m in range(1, 11):
            reflection = np.clip(-(r[m] + np.dot(a[1:m], r[m - 1:0:-1])) / max(error, 1e-12), -.98, .98)
            old = a.copy()
            a[1:m] = old[1:m] + reflection * old[m - 1:0:-1]
            a[m] = reflection
            error *= max(1e-4, 1 - reflection * reflection)
        lsf = lpc_to_lsf(a * bandwidth ** np.arange(11))
        if lsf is None:
            fallbacks += 1
            lsf = np.arange(1, 11) / 11
        # Existing LSF10 syntax; stricter-than-decoder 12-code spacing.
        q = np.clip(np.floor(lsf * 1023 + .5), 12, 1011).astype(int)
        for i in range(1, 10):
            q[i] = max(q[i], q[i - 1] + 12)
        if q[-1] > 1011:
            q[-1] = 1011
            for i in range(8, -1, -1):
                q[i] = min(q[i], q[i + 1] - 12)
        result.append(q.tolist())
    return result, {'window_samples': window, 'bandwidth': bandwidth, 'lsf_fallback_frames': fallbacks}


def pack_frames(vectors):
    frames, previous = [], None
    for vec in vectors:
        delta = [a - b for a, b in zip(vec, previous)] if previous is not None else None
        if vec == previous:
            frames.append(b'\x00')
        elif delta is not None and all(-128 <= d <= 127 for d in delta):
            frames.append(b'\x06' + bytes(d & 255 for d in delta))
        else:
            frames.append(b'\x05' + sum(v << (10 * i) for i, v in enumerate(vec)).to_bytes(13, 'little'))
        previous = vec
    return frames

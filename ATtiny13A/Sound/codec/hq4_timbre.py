"""Exact ATtiny13 HQ4-T output stage and level-independent audit metrics."""
import numpy as np
from numba import njit
from scipy.signal import stft
from pystoi import stoi
from model import decode as decode_hq4


@njit(cache=True)
def restore_tilt(pcm):
    """y = s8(x + previous - (previous >> 2)), with an independent output state.

    Seven one-cycle AVR instructions; the LPC lattice keeps its original states.
    Wrap is intentional AVR arithmetic. Training rejects clipping/discontinuities.
    """
    out = np.empty(len(pcm), np.uint8)
    previous = 0
    for i in range(len(pcm)):
        x = int(pcm[i]) - 128
        previous = ((x + previous - (previous >> 2) + 128) & 255) - 128
        out[i] = (previous + 128) & 255
    return out


def decode(frames, durations):
    return restore_tilt(decode_hq4(frames, durations, 0))


def normalized_spectral_error(reference, pcm, sr=7500):
    """Mean absolute log-magnitude error at 128/256/512 samples, RMS matched.

    Natural log, 50% Hann overlap, scipy STFT zero boundary/padding, floor .0005.
    This is a timbre proxy, not a perceptual quality or listening-test score.
    """
    x = (pcm.astype(np.float64) - 128) / 128
    x *= np.sqrt(np.mean(reference * reference)) / (np.sqrt(np.mean(x * x)) + 1e-10)
    errors = []
    for size in (128, 256, 512):
        _, _, a = stft(reference, fs=sr, nperseg=size, noverlap=size // 2)
        _, _, b = stft(x, fs=sr, nperseg=size, noverlap=size // 2)
        errors.append(np.mean(np.abs(np.log(np.maximum(abs(a), .0005)) -
                                     np.log(np.maximum(abs(b), .0005)))))
    return float(np.mean(errors))


def metrics(reference, pcm, sr=7500):
    return {
        'stoi': float(stoi(reference, (pcm.astype(np.float64) - 128) / 128, sr)),
        'spectral_error': normalized_spectral_error(reference, pcm, sr),
        'steps_ge_48': int(np.sum(abs(np.diff(pcm.astype(np.int16))) >= 48)),
        'peak_signed': int(np.max(abs(pcm.astype(np.int16) - 128))),
    }

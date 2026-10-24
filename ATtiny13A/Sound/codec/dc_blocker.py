"""Two-byte integer DC blocker for unsigned 8-bit speech/PWM.

State is carried across chunks and phrase loops. Reset it only when starting a
new playback. After playback feed 128 (signed zero) until the tail settles.
Natural waveform asymmetry is preserved: no rectification or wave mirroring.

AVR contract (signed 16-bit intermediate, arithmetic right shift)::

    estimate = (state + (1 << (shift - 1))) >> shift
    sample = (pwm - 128) - estimate
    state += sample
    pwm = clamp(sample, -128, 127) + 128

Rounding is to nearest with ties toward positive infinity. State integrates
the *unclipped* sample, so output clipping cannot wind up the DC estimate.
At 7500 Hz shifts 5/6/7 have nominal poles at about 37.9/18.8/9.4 Hz.
"""
import numpy as np
from numba import njit


def state_bounds(shift):
    """Tight invariant interval reachable from zero with signed 8-bit input."""
    if shift not in (5, 6, 7):
        raise ValueError('DC shift must be 5, 6 or 7')
    scale = 1 << shift
    return -128*scale+scale//2-1, 127*scale-scale//2


@njit(cache=True)
def dc_block_core(pcm, shift, state):
    """Unchecked integer kernel: (PWM bytes, final state, clipped, peak)."""
    out = np.empty(len(pcm), np.uint8)
    clipped, peak = 0, 0
    half = 1 << (shift-1)
    for i in range(len(pcm)):
        estimate = (state+half) >> shift
        sample = int(pcm[i])-128-estimate
        state += sample
        peak = max(peak, abs(sample))
        if sample < -128:
            out[i] = 0
            clipped += 1
        elif sample > 127:
            out[i] = 255
            clipped += 1
        else:
            out[i] = sample+128
    return out, state, clipped, peak


def block_dc(pcm, shift=7, state=0):
    """Return (uint8 PWM, state, clipped count, pre-clamp absolute peak).

    Keep the returned state for the next chunk/loop. The accepted state bounds
    guarantee every intermediate fits signed 16-bit, including the rounding
    addition; only two persistent bytes are required by a native decoder.
    """
    low, high = state_bounds(shift)
    if not isinstance(state, (int, np.integer)) or not low <= state <= high:
        raise ValueError('Invalid DC state')
    pcm = np.asarray(pcm)
    if pcm.ndim != 1 or pcm.dtype != np.uint8:
        raise ValueError('Expected a one-dimensional uint8 PWM array')
    return dc_block_core(pcm, shift, int(state))

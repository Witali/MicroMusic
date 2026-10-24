"""Constant firmware output scaling selected from exact PCM without clipping."""
import hashlib
import numpy as np


def scale_pcm(pcm, numerator, shift=7, error_feedback=False):
    source = np.asarray(pcm)
    if (source.dtype != np.uint8 or source.ndim != 1 or not len(source)
            or type(numerator) is not int or numerator < 1 or not 0 <= shift <= 15):
        raise ValueError('Expected nonempty unsigned PCM and a positive fixed gain')
    signed = source.astype(np.int64)-128
    half = 1 << (shift-1) if shift else 0
    if error_feedback:
        # Carry the discarded fraction forward instead of rounding each quiet
        # sample independently. This keeps cumulative level error below 1/2 LSB.
        output = np.diff((np.cumsum(signed*numerator)+half) >> shift, prepend=0)
    else:
        output = (signed*numerator+half) >> shift
    if np.any(output < -128) or np.any(output > 127):
        raise ValueError('Output gain would clip the firmware signal')
    return (output+128).astype(np.uint8)


def choose_gain(pcm, mode='q7', error_feedback=False):
    if not np.any(np.asarray(pcm) != 128):
        return (128, 7) if mode == 'q7' else (1, 0)
    choices = ((n, 7) for n in range(255, 127, -1)) if mode == 'q7' else (
        (1 << power, 0) for power in range(7, -1, -1)) if mode == 'shift' else None
    if choices is None:
        raise ValueError('Unknown output gain mode')
    for numerator, shift in choices:
        try:
            scale_pcm(pcm, numerator, shift, error_feedback)
            return numerator, shift
        except ValueError:
            pass
    raise ValueError('No non-clipping output gain')


def describe_level(source, numerator, shift, error_feedback=False):
    output = scale_pcm(source, numerator, shift, error_feedback)
    def describe(pcm):
        raw = pcm.astype(np.int16)-128
        return dict(minimumDuty=int(pcm.min()), maximumDuty=int(pcm.max()),
                    peak=int(abs(raw).max()), mean=float(raw.mean()),
                    pcmSha256=hashlib.sha256(pcm.tobytes()).hexdigest())
    return dict(implementation='firmware-constant-gain', numerator=numerator,
                shift=shift, gain=numerator/(1 << shift), clippedSamples=0,
                rounding='error-feedback' if error_feedback else 'nearest',
                before=describe(source), after=describe(output))

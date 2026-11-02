"""Calibrate constant playback gain from complete unsigned PWM8 output."""
import hashlib
import math


def apply_gain(pcm, numerator=128):
    if type(numerator) is not int or not 128 <= numerator <= 255:
        raise ValueError('Q7 output gain must be 128..255')
    return bytes(max(0, min(255, ((value*numerator+64) >> 7)+128-numerator)) for value in pcm)


def choose_gain(pcm):
    if not pcm:
        raise ValueError('Expected complete nonempty PWM8 output')
    low, high = min(pcm), max(pcm)
    if low == high == 128 or low < 2 or high > 254:
        return 128
    # Keep two PWM codes below/above the digital rails. Existing full-range
    # releases retain unity: amplification cannot repair decoder clipping.
    for numerator in range(255, 127, -1):
        ends = apply_gain(bytes((low, high)), numerator)
        if min(ends) >= 2 and max(ends) <= 254:
            return numerator
    return 128


def describe_level(pcm, numerator):
    def describe(data):
        signed = [value-128 for value in data]
        return dict(minimumDuty=min(data), maximumDuty=max(data),
                    rms=math.sqrt(sum(value*value for value in signed)/len(data)),
                    pcmSha256=hashlib.sha256(data).hexdigest())
    unbounded = [((value*numerator+64) >> 7)+128-numerator for value in pcm]
    if any(not 0 <= value <= 255 for value in unbounded):
        raise ValueError('Calibrated gain would saturate the complete phrase')
    return dict(implementation='producer-constant-q7', numerator=numerator, shift=7,
                gain=numerator/128, gainDb=20*math.log10(numerator/128),
                rounding='nearest-ties-positive', saturatedSamples=0,
                before=describe(pcm), after=describe(apply_gain(pcm, numerator)))

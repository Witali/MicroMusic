"""Declared whole-input gain before final PCM16 quantization for voice encoding.

Floating/24-bit sources must not be rounded to silence before quiet-level
planning. Internal analysis normalization does not alter the source file. The
returned PCM is the explicitly declared coding/playback target.
"""
from __future__ import annotations

import math

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


def prepare_level(reference, policy='preserve'):
    """Return owned PCM16 segment and declared power-of-two playback gain."""
    ref = np.asarray(reference)
    if (ref.ndim != 1 or ref.dtype.kind not in 'iu' or not 1 <= len(ref) <= 64000
            or int(ref.min()) < -32768 or int(ref.max()) > 32767):
        raise ValueError('Expected 1..64000 original PCM16 samples')
    if policy not in ('preserve', 'auto-quiet'):
        raise ValueError('Expected preserve or explicit auto-quiet level policy')
    values = ref.astype(np.int64)
    plan = plan_level(values, policy)
    target, clipped = quantize_target(values, plan)
    if clipped:
        raise AssertionError('Declared quiet gain clipped the input')
    return target, plan


def plan_level(pcm_units, policy='auto-quiet'):
    values = np.asarray(pcm_units, dtype=np.float64)
    if (values.ndim != 1 or not len(values) or not np.isfinite(values).all()
            or policy not in ('preserve', 'auto-quiet')):
        raise ValueError('Expected finite nonempty mono samples and an explicit level policy')
    peak = float(np.max(np.abs(values)))
    # Scale before squaring: a valid very quiet float source can otherwise have
    # zero numerical variance despite retaining its waveform in the input.
    scaled = values / peak if peak else values
    relative_rms = float(np.std(scaled)) if peak else 0.
    # Keep the established integer/ordinary-float threshold decisions exactly;
    # scale first only where direct variance would under/overflow.
    rms = float(np.std(values)) if 1e-140 <= peak <= 1e140 else peak * relative_rms
    log_rms = math.log2(peak) + math.log2(relative_rms) if relative_rms else -math.inf
    exponent = 0
    if policy == 'auto-quiet' and relative_rms:
        if rms:
            if rms < 256:
                while math.ldexp(rms, exponent) < 1024 and math.ldexp(peak, exponent + 1) <= 29490:
                    exponent += 1
        elif log_rms < 8:
            log_peak = math.log2(peak)
            while log_rms + exponent < 10 and log_peak + exponent + 1 <= math.log2(29490):
                exponent += 1
    gain = 1 << exponent if exponent <= 1023 else None
    return dict(policy=policy, gain=gain, gain_power2_exponent=exponent,
                gain_db=exponent * 20 * math.log10(2), input_ac_rms_pcm16=rms,
                input_peak_pcm16=peak,
                target_ac_rms_pcm16=(math.ldexp(rms, exponent) if rms else
                                      2 ** (log_rms + exponent) if relative_rms else 0.),
                output_level_matches_original=exponent == 0,
                scope='One declared whole-input power-of-two gain before PCM16 rounding; no fitted output gain')


def quantize_target(pcm_units, plan):
    values = np.asarray(pcm_units, dtype=np.float64)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
        raise ValueError('Expected finite mono input in PCM16 units')
    scaled = np.ldexp(values, plan['gain_power2_exponent'])
    if not np.isfinite(scaled).all():
        raise ValueError('Declared target is outside finite PCM16 scaling range')
    clipped = int(np.count_nonzero((scaled < -32768) | (scaled > 32767)))
    return np.clip(np.rint(scaled), -32768, 32767).astype(np.int16), clipped


def load_voice_wav(path, policy='auto-quiet'):
    """Read/resample in float, choose ONE gain, then round to PCM16 once.

    A complete long input receives one plan before any codec reset segmentation.
    This is a deliberate playback-level transform, not evaluation gain fitting.
    """
    info = sf.info(path)
    audio, rate = sf.read(path, dtype='float64', always_2d=True)
    if not len(audio) or rate < 1 or not np.isfinite(audio).all():
        raise ValueError('WAV must contain finite nonempty audio')
    channels = audio.shape[1]
    mono = np.mean(audio, axis=1)
    if rate != 8000:
        divisor = math.gcd(rate, 8000)
        mono = resample_poly(mono, 8000 // divisor, rate // divisor)
    pcm_units = mono * 32768
    if not np.isfinite(pcm_units).all():
        raise ValueError('WAV is outside finite PCM16 analysis range')
    plan = plan_level(pcm_units, policy)
    pcm, clipped = quantize_target(pcm_units, plan)
    return pcm, dict(input_rate=rate, input_channels=channels, input_subtype=info.subtype,
                     output_rate=8000, output_samples=len(pcm), clipped_input_samples=clipped,
                     input_level=plan, gain_before_pcm16_rounding=True,
                     input_file_modified=False)

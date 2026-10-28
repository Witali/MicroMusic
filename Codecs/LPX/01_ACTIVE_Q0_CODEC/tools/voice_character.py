"""Host-only pitch/shape diagnostics at original PCM16 level and full length.

The period estimator is an independent direct implementation of the YIN
difference/normalization/first-trough idea (de Cheveigne and Kawahara, 2002,
DOI 10.1121/1.1458024). No third-party implementation is copied. This bounded
diagnostic is not full YIN/pYIN, a VAD, speaker identification or a perceptual
quality model. Missing periodicity remains missing rather than a guessed F0.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
import hashlib
import math

import numpy as np


@dataclass(frozen=True)
class PitchSettings:
    rate: int = 8000
    frame_samples: int = 640
    hop_samples: int = 160
    fmin: float = 50.
    fmax: float = 800.
    trough_threshold: float = .15
    min_rms_pcm16: float = .5
    tolerance_cents: float = 100.

    def __post_init__(self):
        for name in ('rate', 'frame_samples', 'hop_samples'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError('Positive integer rate/frame/hop required')
        numeric = (self.fmin, self.fmax, self.trough_threshold,
                   self.min_rms_pcm16, self.tolerance_cents)
        if not all(np.isfinite(v) for v in numeric):
            raise ValueError('Finite pitch settings required')
        if not 0 < self.fmin < self.fmax < self.rate / 2:
            raise ValueError('Expected 0 < fmin < fmax < Nyquist')
        if not 0 < self.trough_threshold < 1 or self.min_rms_pcm16 <= 0 or self.tolerance_cents <= 0:
            raise ValueError('Invalid threshold, PCM resolution floor or cents tolerance')
        if self.frame_samples < 2 * (math.ceil(self.rate / self.fmin) + 1):
            raise ValueError('Frame must cover twice the maximum tested lag plus interpolation')
        if self.hop_samples > self.frame_samples:
            raise ValueError('Hop must not leave unanalysed gaps between frames')


@dataclass(frozen=True)
class PitchTrack:
    settings: PitchSettings
    samples: int
    frame_start: np.ndarray
    sample_center: np.ndarray
    hz: np.ndarray
    period: np.ndarray
    confidence: np.ndarray
    rms: np.ndarray
    voiced: np.ndarray
    status: np.ndarray
    _source_digest: bytes = field(repr=False)


def _pcm16(value):
    a = np.asarray(value)
    if (a.ndim != 1 or not len(a) or a.dtype.kind not in 'iu' or
            np.any(a < -32768) or np.any(a > 32767)):
        raise ValueError('Nonempty mono PCM16 integer samples required')
    return a


def _owned(values, dtype):
    a = np.array(values, dtype=dtype, copy=True)
    a.setflags(write=False)
    return a


def _period(frame, settings):
    x = frame.astype(np.float64)
    x -= x.mean()
    rms = float(np.sqrt(np.mean(x * x)))
    if rms < settings.min_rms_pcm16:
        return np.nan, 0., rms, 'below_pcm_resolution'
    # Scale only temporary analysis; no audio/output or evaluation gain changes.
    x /= np.max(np.abs(x))
    # Include neighboring integer troughs before fractional interpolation;
    # ceil at the upper-Hz edge would miss a valid noninteger short period.
    first = max(2, math.floor(settings.rate / settings.fmax))
    last = math.ceil(settings.rate / settings.fmin)
    support = len(x) - last - 1
    difference = np.zeros(last + 2)
    base = x[:support]
    for lag in range(1, last + 2):
        delta = base - x[lag:lag + support]
        difference[lag] = np.dot(delta, delta)
    denominator = np.cumsum(difference[1:])
    cmnd = np.ones_like(difference)
    nonzero = denominator > np.finfo(np.float64).tiny
    cmnd[1:] = np.divide(difference[1:] * np.arange(1, last + 2),
                         denominator, out=np.ones_like(denominator), where=nonzero)
    candidates = [lag for lag in range(first, last + 1)
                  if cmnd[lag] <= cmnd[lag - 1] and cmnd[lag] < cmnd[lag + 1]]
    accepted = [lag for lag in candidates if cmnd[lag] < settings.trough_threshold]
    if not accepted:
        confidence = float(np.clip(1 - np.min(cmnd[first:last + 1]), 0, 1))
        return np.nan, confidence, rms, 'aperiodic_or_ambiguous'
    lag = accepted[0]
    # YIN step 5 refines the abscissa with the raw difference to avoid the
    # normalized curve's small period bias. Confidence still uses CMNDF.
    left, middle, right = difference[lag - 1:lag + 2]
    curvature = left - 2 * middle + right
    offset = (left - right) / (2 * curvature) if curvature > 0 else 0.
    period = lag + float(np.clip(offset, -.5, .5))
    hz = settings.rate / period
    confidence = float(np.clip(1 - cmnd[lag], 0, 1))
    if not settings.fmin <= hz <= settings.fmax:
        return np.nan, confidence, rms, 'out_of_range'
    return period, confidence, rms, 'period_candidate'


def track_pitch(pcm, settings=None):
    """Return owned read-only frame arrays; unknown periods/hz are NaN.

    No edge padding, resampling, time alignment or output normalization occurs.
    A period candidate is a measured periodicity, not a guarantee of true F0.
    Confidence is 1-CMNDF, not a calibrated probability of voicing.
    """
    pcm = _pcm16(pcm)
    settings = PitchSettings() if settings is None else settings
    if not isinstance(settings, PitchSettings):
        raise ValueError('PitchSettings required')
    starts = range(0, len(pcm) - settings.frame_samples + 1, settings.hop_samples)
    starts = list(starts)
    estimates = [_period(pcm[at:at + settings.frame_samples], settings) for at in starts]
    period, confidence, rms, status = zip(*estimates) if estimates else ([], [], [], [])
    periods = np.asarray(period, dtype=float)
    return PitchTrack(settings, len(pcm), _owned(starts, np.int64),
                      _owned(np.asarray(starts) + settings.frame_samples // 2, np.int64),
                      _owned(settings.rate / periods, np.float64),
                      _owned(periods, np.float64), _owned(confidence, np.float64),
                      _owned(rms, np.float64), _owned(np.isfinite(periods), np.bool_),
                      _owned(status, 'U32'),
                      hashlib.sha256(pcm.astype('<i2', copy=False).tobytes()).digest())


def fixed_periodicity_error(frame, period_samples):
    """Normalized fractional-period difference on the supplied fixed frame.

    Zero means matching across the tested period; uncorrelated and vanished
    signals return about 1 and 1 respectively; an opposite phase can approach 2.
    Use reference-frozen periods/windows so decoded F0 dropouts cannot evade a
    comparison. This is a numerical diagnostic, not a periodicity probability.
    """
    x = np.asarray(frame, dtype=np.float64)
    if (x.ndim != 1 or not np.all(np.isfinite(x)) or
            not np.isfinite(period_samples) or period_samples < 1 or period_samples + 2 > len(x)):
        raise ValueError('Finite mono frame and an interior positive period required')
    x = x - x.mean()
    lag = math.floor(period_samples)
    fraction = period_samples - lag
    support = len(x) - lag - 1
    a = x[:support]
    b = (1 - fraction) * x[lag:lag + support] + fraction * x[lag + 1:lag + 1 + support]
    denominator = float(np.dot(a, a) + np.dot(b, b))
    if denominator <= np.finfo(np.float64).tiny:
        return 1.
    delta = a - b
    return float(np.clip(np.dot(delta, delta) / denominator, 0, 2))


def spectral_shape_error(reference_frame, decoded_frame, *, bands=24, floor_db=-80.):
    """RMS dB distance between coarse relative-power spectral shapes.

    Equal-width bands of the original-rate Hann periodogram describe shape;
    each spectrum is divided by its own total only inside this analysis. A
    zero candidate retains zero power, then pays the stated relative log floor.
    Gain/level loss is reported separately; this is not a formant estimator.
    """
    a = np.asarray(reference_frame, dtype=float)
    b = np.asarray(decoded_frame, dtype=float)
    if (a.ndim != 1 or a.shape != b.shape or len(a) < 4 or
            not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)) or
            isinstance(bands, bool) or not isinstance(bands, int) or
            not 2 <= bands <= len(a) // 2 or not np.isfinite(floor_db) or floor_db >= 0):
        raise ValueError('Equal finite mono frames and valid spectral settings required')
    shapes = []
    window = np.hanning(len(a))
    for x in (a, b):
        power = abs(np.fft.rfft((x - x.mean()) * window)) ** 2
        # Include DC and Nyquist; no frequency samples are silently discarded.
        index = np.minimum(bands - 1, np.arange(len(power)) * bands // len(power))
        energy = np.bincount(index, weights=power, minlength=bands)
        total = float(energy.sum())
        relative = energy / total if total else energy
        shapes.append(10 * np.log10(np.maximum(relative, 10 ** (floor_db / 10))))
    return float(np.sqrt(np.mean((shapes[0] - shapes[1]) ** 2)))


def _level(pcm):
    a = pcm.astype(float)
    rms = float(np.sqrt(np.mean(a * a)))
    return {'samples': len(a), 'rms_pcm16': rms, 'peak_pcm16': int(np.max(abs(a))),
            'rms_dbfs': float(20 * np.log10(rms / 32768)) if rms else None,
            'nonzero_samples': int(np.count_nonzero(a))}


def compare_voice(reference, decoded, settings=None, *, reference_track=None):
    """Full-length/original-gain diagnostics with explicit missing-pitch penalties.

    PCM and fixed PWM should be passed separately by callers. This function
    neither computes nor changes traditional SSE/STOI quality floors.
    """
    reference, decoded = _pcm16(reference), _pcm16(decoded)
    if reference.shape != decoded.shape:
        raise ValueError('Complete equal-length reference/decoded arrays required')
    settings = PitchSettings() if settings is None else settings
    source = track_pitch(reference, settings) if reference_track is None else reference_track
    if (not isinstance(source, PitchTrack) or source.settings != settings or
            source.samples != len(reference) or source._source_digest !=
            hashlib.sha256(reference.astype('<i2', copy=False).tobytes()).digest()):
        raise ValueError('Reference track source/geometry/settings mismatch')
    # The source binding stays internal and is never emitted in the report.
    result = track_pitch(decoded, settings)
    observed = source.voiced
    matched = observed & result.voiced
    cents = 1200 * np.log2(result.hz[matched] / source.hz[matched])
    within = np.abs(cents) <= settings.tolerance_cents
    missing = int(np.count_nonzero(observed & ~result.voiced))
    count = int(np.count_nonzero(observed))
    active = source.rms >= settings.min_rms_pcm16
    fixed_source, fixed_decoded, shape = [], [], []
    for i, at in enumerate(source.frame_start):
        a = reference[at:at + settings.frame_samples]
        b = decoded[at:at + settings.frame_samples]
        if observed[i]:
            fixed_source.append(fixed_periodicity_error(a, source.period[i]))
            fixed_decoded.append(fixed_periodicity_error(b, source.period[i]))
        if active[i]:
            shape.append(spectral_shape_error(a, b))
    if not count:
        status = 'unassessed_no_reference_periodicity'
    elif missing or not np.all(within):
        status = 'pitch_mismatch_or_missing'
    else:
        status = 'all_observed_periods_within_tolerance'
    return {
        'schema': 'lpx-voice-character-diagnostic-v1',
        'settings': {f.name: getattr(settings, f.name) for f in fields(settings)},
        'reference_level': _level(reference), 'decoded_level': _level(decoded),
        'frames': len(observed), 'active_reference_frames': int(np.count_nonzero(active)),
        'pitch_status': status, 'reference_period_frames': count,
        'paired_period_frames': int(np.count_nonzero(matched)),
        'missing_decoded_period_frames': missing,
        'within_tolerance_frames': int(np.count_nonzero(within)),
        'pitch_failure_fraction': (missing + int(np.count_nonzero(~within))) / count if count else None,
        'reference_hz_median': float(np.median(source.hz[observed])) if count else None,
        'decoded_hz_median_paired': float(np.median(result.hz[matched])) if matched.any() else None,
        'absolute_cents_median_paired': float(np.median(abs(cents))) if len(cents) else None,
        'signed_cents_median_paired': float(np.median(cents)) if len(cents) else None,
        'near_half_pitch_frames': int(np.count_nonzero(abs(cents + 1200) <= settings.tolerance_cents)),
        'near_double_pitch_frames': int(np.count_nonzero(abs(cents - 1200) <= settings.tolerance_cents)),
        'fixed_source_period_error_mean': float(np.mean(fixed_source)) if fixed_source else None,
        'fixed_decoded_period_error_mean': float(np.mean(fixed_decoded)) if fixed_decoded else None,
        'relative_spectral_shape_rms_db_mean': float(np.mean(shape)) if shape else None,
        'spectral_shape_frames': len(shape),
        'decoded_collapsed_active_frames': int(np.count_nonzero(active & (result.rms < settings.min_rms_pcm16))),
        'scope': 'Frame periodicity and coarse spectral proxies, not perceived quality or validated true F0; no gain fitting/resampling/alignment.',
    }

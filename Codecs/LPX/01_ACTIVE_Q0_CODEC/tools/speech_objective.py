"""Host-only v5 waveform and perceptually weighted error objectives.

The weighting recurrence is shared with the established v2/v3 experiment.
It never replaces the clipped integer synthesis or the PCM/PWM quality gate.
Freeze coefficients from one seed stream so changing LPC cannot change the
criterion against which candidates compete. Weighting history spans frames;
only an explicit independent-stream reset starts that history at zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real

import numpy as np
from numba import njit
from perceptual_rate import weight_error


@njit(cache=True)
def _weight_error_state(error, co, gamma1, gamma2, input_history, output_history):
    e = input_history.copy()
    w = output_history.copy()
    out = np.empty(len(error), np.float64)
    for n in range(len(error)):
        value = float(error[n])
        g1 = gamma1
        g2 = gamma2
        for k in range(10):
            a = co[n, k] / 4096.
            value += a * (g1 * e[k] - g2 * w[k])
            g1 *= gamma1
            g2 *= gamma2
        for k in range(9, 0, -1):
            e[k] = e[k - 1]
            w[k] = w[k - 1]
        e[0] = error[n]
        w[0] = value
        out[n] = value
    return out, e, w


def _gammas(gamma1, gamma2):
    if any(isinstance(v, (bool, np.bool_)) or not isinstance(v, Real)
           or not np.isfinite(v) for v in (gamma1, gamma2)):
        raise ValueError('Expected finite weighting coefficients')
    if not 0 < gamma2 < gamma1 < 1:
        raise ValueError('Expected 0 < gamma2 < gamma1 < 1')
    return float(gamma1), float(gamma2)


def _pcm16(pcm, samples=None):
    value = np.asarray(pcm)
    if (value.ndim != 1 or value.dtype.kind not in 'iu'
            or not 1 <= len(value) <= 1000000
            or samples is not None and len(value) != samples
            or np.any(value < -32768) or np.any(value > 32767)):
        raise ValueError('Expected original-length mono integer PCM16')
    return value


def _coefficients(co, samples):
    value = np.asarray(co)
    if (value.shape != (samples, 10) or value.dtype.kind not in 'iu'
            or np.any(value < -32768) or np.any(value > 32767)):
        raise ValueError('Expected signed Q12 LPC coefficient trace')
    return np.array(value, dtype=np.int64, copy=True)


def denominator_gamma(co, requested=.6, bound=.95):
    """One seed-wide damping with a uniform time-varying stability bound.

    Valid decoder LPC is clipped and need not define a stable floating-point
    all-pole filter. Require sum(abs(a_k) * gamma**k) <= bound at every sample.
    Then |w[n]| <= max|numerator_output| / (1 - bound), even when coefficients
    change. This sufficient bound can be conservative; no candidate changes it.
    """
    if (isinstance(requested, (bool, np.bool_)) or not isinstance(requested, Real)
            or not np.isfinite(requested) or not 0 < requested < 1
            or isinstance(bound, (bool, np.bool_)) or not isinstance(bound, Real)
            or not np.isfinite(bound) or not 0 < bound < 1):
        raise ValueError('Expected finite denominator damping and contraction bound')
    values = np.asarray(co)
    if values.ndim != 2 or values.shape[1] != 10 or not len(values):
        raise ValueError('Expected a nonempty LPC trace')
    absolute = np.abs(_coefficients(values, len(values)).astype(np.float64)) / 4096.
    def maximum(gamma):
        # Use the kernel's repeated multiplication rather than a different
        # exponent evaluation when checking the numerical bound.
        powers = np.empty(10)
        value = gamma
        for k in range(10):
            powers[k] = value
            value *= gamma
        return float(np.max(absolute @ powers))
    if maximum(requested) <= bound:
        return float(requested)
    low, high = 0., float(requested)
    for _ in range(64):
        middle = (low + high) / 2
        if maximum(middle) <= np.nextafter(float(bound), 0):
            low = middle
        else:
            high = middle
    return low


@dataclass(frozen=True)
class WeightingState:
    """Independent histories for a weighting continuation or search branch."""
    input_history: np.ndarray
    output_history: np.ndarray

    def __post_init__(self):
        for name in ('input_history', 'output_history'):
            value = np.array(getattr(self, name), dtype=np.float64, copy=True)
            if value.shape != (10,) or not np.all(np.isfinite(value)):
                raise ValueError('Expected ten finite weighting-history values')
            value.flags.writeable = False
            object.__setattr__(self, name, value)

    @classmethod
    def zero(cls):
        return cls(np.zeros(10), np.zeros(10))


def weight_error_chunk(error, co, *, state=None, gamma1=.9, gamma2=.6):
    """Weight one contiguous chunk and return (output, independent new state).

    The caller passes the coefficient rows for this exact interval. Keeping
    the returned state is mandatory at frame/chunk boundaries within a stream;
    omitting state intentionally starts an independent stream. Neither arrays
    nor incoming histories are mutated, so branches may share one checkpoint.
    """
    gamma1, gamma2 = _gammas(gamma1, gamma2)
    error = np.asarray(error, dtype=np.float64)
    if error.ndim != 1 or not np.all(np.isfinite(error)):
        raise ValueError('Expected finite mono error samples')
    coefficients = _coefficients(co, len(error))
    if state is None:
        state = WeightingState.zero()
    if not isinstance(state, WeightingState):
        raise ValueError('Expected an explicit weighting state')
    out, e, w = _weight_error_state(error, coefficients, gamma1, gamma2,
                                   state.input_history, state.output_history)
    if not np.all(np.isfinite(out)):
        raise ValueError('Non-finite weighted error')
    return out, WeightingState(e, w)


class SpeechObjective:
    """Reusable full-waveform score, with reference and seed weights frozen.

    Integer synthesis must precede scoring. The callback receives complete
    clipped PCM16, without gain fitting, trimming or frame-local resets. The
    perceptual mode is an experimental ranking criterion, not an acceptance
    policy or evidence that an audio difference is audible.
    """
    def __init__(self, reference, coefficients, *, mode='perceptual',
                 gamma1=.9, gamma2=.6):
        if mode not in ('sse', 'perceptual'):
            raise ValueError('Expected sse or perceptual objective')
        self.gamma1, self.requested_gamma2 = _gammas(gamma1, gamma2)
        self._reference = np.array(_pcm16(reference), dtype=np.int64, copy=True)
        self._coefficients = _coefficients(coefficients, len(self._reference))
        self.denominator_bound = .95
        self.gamma2 = denominator_gamma(self._coefficients, self.requested_gamma2,
                                       self.denominator_bound)
        self._reference.flags.writeable = False
        self._coefficients.flags.writeable = False
        self.mode = mode
        self.name = 'v5_' + mode + '_pcm16'

    @classmethod
    def from_v5(cls, reference, seed_blob, **settings):
        from q0_model import coefficient_trace
        import speech_compact as compact
        from wav_lpc import pack_frames
        n, profile, spectra, *_ = compact.unpack(seed_blob)
        _pcm16(reference, n)
        shift = 5 if profile == 4 else 4
        vectors = [[(v << shift) + (1 << (shift - 1)) for v in row]
                   for row in spectra for _ in range(2)]
        co = coefficient_trace(pack_frames(vectors[:(n + 159) // 160]), n)
        return cls(reference, co, **settings)

    def score(self, pcm16):
        candidate = _pcm16(pcm16, len(self._reference)).astype(np.int64)
        error = candidate - self._reference
        if self.mode == 'sse':
            return float(np.dot(error, error))
        weighted = weight_error(error, self._coefficients, self.gamma1, self.gamma2)
        result = float(np.dot(weighted, weighted))
        if not np.isfinite(result):
            raise ValueError('Non-finite perceptual objective')
        return result

    __call__ = score

    def describe(self):
        return {'name': self.name, 'mode': self.mode, 'samples': len(self._reference),
                'gamma1': self.gamma1, 'requested_gamma2': self.requested_gamma2,
                'effective_gamma2': self.gamma2, 'denominator_l1_bound': self.denominator_bound,
                'domain': 'original-level clipped PCM16',
                'weighting_coefficients': 'frozen seed v5 interpolated Q12 LPC',
                'weighting_state': 'zero once per complete stream; continuous across frames',
                'automatic_acceptance': 'unchanged external PCM/PWM no_regression gate'}

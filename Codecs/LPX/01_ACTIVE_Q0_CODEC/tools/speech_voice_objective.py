"""Host-only, reference-frozen voice-shape search criterion for unchanged v5.

This is an experimental search objective, not a perceptual quality score or an
automatic replacement for the existing PCM/PWM metric gate. Reference periods
come from a separately confidence-gated source analysis. Decoded pitch tracking
is deliberately not used to decide which windows count: losing periodicity must
not make a difficult candidate disappear from the comparison.
"""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np
from numba import njit


@dataclass(frozen=True)
class VoiceWeights:
    waveform: float = .25
    spectrum: float = 1.
    periodicity: float = 2.

    def __post_init__(self):
        for value in (self.waveform, self.spectrum, self.periodicity):
            if (isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
                    or not np.isfinite(value) or value < 0):
                raise ValueError('Expected finite nonnegative voice weights')
        if not self.waveform + self.spectrum + self.periodicity:
            raise ValueError('At least one voice weight must be positive')


def _pcm(value, count=None):
    array = np.asarray(value)
    if (array.ndim != 1 or array.dtype.kind not in 'iu' or not len(array)
            or count is not None and len(array) != count
            or int(array.min()) < -32768 or int(array.max()) > 32767):
        raise ValueError('Expected original-level mono integer PCM16')
    return array


@njit(cache=True)
def _period_profiles(windows, periods, lengths):
    """Same-support, fractional-delay difference profiles on centered samples.

    The four ratios distinguish a period from its simple octave alternatives.
    Zero energy returns difference 1, rather than a perfect-period score. This
    batched arithmetic is separate from the independent diagnostic estimator.
    """
    result = np.ones((len(windows), 4), np.float64)
    for index in range(len(windows)):
        period = periods[index]
        if not np.isfinite(period):
            continue
        support = lengths[index] - int(np.ceil(2 * period))
        for column in range(4):
            lag = period * (.5 + .5 * column)
            whole = int(lag)
            fraction = lag - whole
            difference = energy = 0.
            for at in range(support):
                first = windows[index, at]
                second = windows[index, at + whole]
                if fraction:
                    second += fraction * (windows[index, at + whole + 1] - second)
                delta = first - second
                difference += delta * delta
                energy += first * first + second * second
            if energy:
                result[index, column] = difference / energy
    return result


class VoiceObjective:
    """Owned frozen source features; no output gain fitting or resampling.

    ``period_samples`` covers the complete 80-ms windows at the supplied hop;
    NaN means the source analyzer could not establish a reliable voiced period.
    Short terminal windows still contribute waveform/spectral losses. A one
    PCM16-count RMS floor limits noise sensitivity where source quantization
    already dominates. It is never an amplitude threshold for deleting input.
    """
    def __init__(self, reference, period_samples=None, *, frame_samples=640,
                 hop_samples=160, bands=32, weights=VoiceWeights()):
        for value, minimum, maximum in ((frame_samples, 80, 4096),
                                        (hop_samples, 1, frame_samples),
                                        (bands, 2, frame_samples // 2)):
            if (isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral)
                    or not minimum <= value <= maximum):
                raise ValueError('Invalid voice analysis geometry')
        if not isinstance(weights, VoiceWeights):
            raise ValueError('Expected frozen VoiceWeights')
        self.reference = np.array(_pcm(reference), dtype=np.int16, copy=True)
        self.reference.flags.writeable = False
        self.frame, self.hop, self.bands = int(frame_samples), int(hop_samples), int(bands)
        self.weights = weights
        self.starts = np.arange(0, len(self.reference), self.hop)
        self.lengths = np.minimum(self.frame, len(self.reference) - self.starts)
        complete = int(np.count_nonzero(self.lengths == self.frame))
        self.periods = np.full(len(self.starts), np.nan)
        if period_samples is not None:
            values = np.asarray(period_samples, dtype=np.float64)
            if (values.shape != (complete,) or np.any(np.isinf(values))
                    or np.any(np.isfinite(values) & ((values < 2) | (values > self.frame / 3)))):
                raise ValueError('Expected one reliable period or NaN per complete source window')
            self.periods[:complete] = values
        self.voiced = np.isfinite(self.periods)
        self._hann = {int(length): np.hanning(int(length)) for length in set(self.lengths)}
        self._energy = np.empty(len(self.starts))
        self._spectra = np.empty((len(self.starts), self.bands))
        self._profiles = np.ones((len(self.starts), 4))
        for begin in range(0, len(self.starts), 64):
            indices = np.arange(begin, min(begin + 64, len(self.starts)))
            raw, centered = self._windows(self.reference, 0, indices)
            self._energy[indices] = np.maximum(np.sum(raw * raw, axis=1), self.lengths[indices])
            self._spectra[indices] = self._shape(centered, indices)
            self._profiles[indices] = _period_profiles(centered, self.periods[indices], self.lengths[indices])
        for value in (self.starts, self.lengths, self.periods, self.voiced,
                      self._energy, self._spectra, self._profiles):
            value.flags.writeable = False
        self.name = 'v5_reference_voice_shape_v1'

    def _windows(self, data, offset, indices):
        raw = np.zeros((len(indices), self.frame), np.float64)
        centered = raw.copy()
        for row, index in enumerate(indices):
            start = int(self.starts[index]) - offset
            length = int(self.lengths[index])
            samples = np.asarray(data[start:start + length], np.float64)
            raw[row, :length] = samples
            centered[row, :length] = samples - samples.mean()
        return raw, centered

    def _shape(self, centered, indices):
        windowed = centered.copy()
        for row, index in enumerate(indices):
            length = int(self.lengths[index])
            windowed[row, :length] *= self._hann[length]
        power = abs(np.fft.rfft(windowed, axis=1)[:, 1:]) ** 2
        grouped = np.stack([part.sum(axis=1) for part in np.array_split(power, self.bands, axis=1)], axis=1)
        totals = grouped.sum(axis=1, keepdims=True)
        return np.sqrt(grouped / np.where(totals > 0, totals, 1))

    def components(self, pcm, *, start=0):
        candidate = _pcm(pcm)
        if (isinstance(start, (bool, np.bool_)) or not isinstance(start, Integral)
                or start < 0 or start + len(candidate) > len(self.reference)):
            raise ValueError('Candidate does not cover an original reference interval')
        stop = start + len(candidate)
        indices = np.flatnonzero((self.starts >= start) & (self.starts + self.lengths <= stop))
        if not len(indices):
            error = candidate.astype(np.float64) - self.reference[start:stop]
            target = self.reference[start:stop].astype(np.float64)
            return dict(waveform=float(error @ error / max(float(target @ target), len(target))),
                        spectrum=0., periodicity=0., windows=0, voiced_windows=0)
        waveform = spectrum = periodicity = 0.
        voiced = int(np.count_nonzero(self.voiced[indices]))
        for begin in range(0, len(indices), 64):
            chunk = indices[begin:begin + 64]
            raw, centered = self._windows(candidate, start, chunk)
            original, _ = self._windows(self.reference, 0, chunk)
            waveform += float(np.sum(np.sum((raw - original) ** 2, axis=1) / self._energy[chunk]))
            spectrum += float(np.sum((self._shape(centered, chunk) - self._spectra[chunk]) ** 2))
            selected = self.voiced[chunk]
            if np.any(selected):
                profiles = _period_profiles(centered, self.periods[chunk], self.lengths[chunk])
                periodicity += float(np.sum(np.mean((profiles[selected] - self._profiles[chunk][selected]) ** 2, axis=1)))
        return dict(waveform=waveform / len(indices), spectrum=spectrum / len(indices),
                    periodicity=periodicity / max(1, voiced), windows=len(indices), voiced_windows=voiced)

    def score(self, pcm, *, start=0):
        if start == 0 and len(pcm) != len(self.reference):
            raise ValueError('Use score_range for a partial candidate')
        values = self.components(pcm, start=start)
        return float(self.weights.waveform * values['waveform']
                     + self.weights.spectrum * values['spectrum']
                     + self.weights.periodicity * values['periodicity'])

    def score_range(self, pcm, start):
        values = self.components(pcm, start=start)
        return float(self.weights.waveform * values['waveform']
                     + self.weights.spectrum * values['spectrum']
                     + self.weights.periodicity * values['periodicity'])

    __call__ = score

    def describe(self):
        return dict(name=self.name, frame_samples=self.frame, hop_samples=self.hop,
                    spectral_bands=self.bands, source_voiced_windows=int(self.voiced.sum()),
                    weights=dict(waveform=self.weights.waveform, spectrum=self.weights.spectrum,
                                 periodicity=self.weights.periodicity),
                    waveform_domain='original-level PCM16; frame-relative error with one-count RMS floor',
                    spectral_domain='unit-energy square-root band powers; analysis only',
                    periodicity_domain='source-frozen period ratios 0.5/1/1.5/2; missing output is penalized',
                    decoder_or_format_changes=False, automatic_metric_gate_changed=False)

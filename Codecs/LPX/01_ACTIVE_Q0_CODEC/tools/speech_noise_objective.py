"""Source-frozen harmonic/off-harmonic shape criterion for host-only search.

Natural source noise is a target, not something to minimize. Source period
windows and harmonic groups never depend on the candidate's pitch tracker.
This is a bounded spectral proxy, not calibrated roughness, HNR or true F0.
Pair it with waveform/periodicity objectives and the existing quality gates.
"""
from __future__ import annotations

import numpy as np

from speech_voice_objective import VoiceObjective, _pcm


class NoiseObjective:
    """Owned source/mask; finite scalar in [0,1], without audio gain fitting.

    ``source_periods`` has one source period or NaN per complete 640-sample
    window at 160-sample hops, exactly as VoiceObjective. None means no source
    pitch assessment. Unknown windows still compare fine spectral shape;
    source silence penalizes newly injected AC power at a one-count RMS floor.
    Reuse ``voice_objective`` as the accompanying voice scorer if desired.
    """
    def __init__(self, reference, source_periods):
        self.voice_objective = VoiceObjective(reference, source_periods)
        context = self.voice_objective
        self.reference = context.reference
        self.periods = context.periods
        self.starts = context.starts
        self.lengths = context.lengths
        self.frame, self.hop = context.frame, context.hop
        self._labels, self._shapes = [], []
        self._harmonics = np.zeros(len(self.starts), np.int64)
        self._power = np.zeros(len(self.starts), np.float64)
        self._off_harmonic = np.full(len(self.starts), np.nan)
        frequencies = np.fft.rfftfreq(self.frame, 1 / 8000)[1:]
        for first in range(0, len(self.starts), 64):
            indices = np.arange(first, min(first + 64, len(self.starts)))
            _, centered = context._windows(self.reference, 0, indices)
            powers = context._periodograms(centered, indices)
            for row, index in enumerate(indices):
                period = self.periods[index]
                groups = 0 if not np.isfinite(period) else int(3800 // (8000 / period))
                labels = groups + np.arange(len(frequencies))
                if groups:
                    fundamental = 8000 / period
                    nearest = np.rint(frequencies / fundamental).astype(np.int64)
                    width = min(1.5 * 8000 / self.frame, fundamental / 4)
                    harmonic = ((nearest >= 1) & (nearest <= groups)
                                & (abs(frequencies - nearest * fundamental) <= width))
                    labels[harmonic] = nearest[harmonic] - 1
                labels.flags.writeable = False
                self._labels.append(labels)
                self._harmonics[index] = groups
                self._power[index] = powers[row].sum()
                length = int(self.lengths[index])
                shape = self._feature(powers[row], labels, groups)
                shape.flags.writeable = False
                self._shapes.append(shape)
                if groups and self._power[index] > 0 and length >= 4:
                    self._off_harmonic[index] = np.sum(shape[groups:] ** 2)
        self._labels = tuple(self._labels)
        self._shapes = tuple(self._shapes)
        for value in (self._harmonics, self._power, self._off_harmonic):
            value.flags.writeable = False
        self.name = 'v5_source_harmonic_noise_balance_v1'

    @staticmethod
    def _feature(power, labels, harmonics):
        energy = np.bincount(labels, weights=power, minlength=len(power) + harmonics)
        total = energy.sum()
        return np.sqrt(energy / total) if total > 0 else energy

    def summary(self, pcm):
        candidate = _pcm(pcm, len(self.reference))
        context = self.voice_objective
        costs, shape_losses, balance_losses = [], [], []
        source_noise, candidate_noise = [], []
        silent_source = collapsed = injected = spectral_only = missing_balance = short = 0
        source_pitch = int(np.isfinite(self.periods).sum())
        for first in range(0, len(self.starts), 64):
            indices = np.arange(first, min(first + 64, len(self.starts)))
            _, centered = context._windows(candidate, 0, indices)
            powers = context._periodograms(centered, indices)
            for row, index in enumerate(indices):
                length = int(self.lengths[index])
                if length < 4:
                    short += 1
                    continue
                power = float(powers[row].sum())
                if self._power[index] <= 0:
                    silent_source += 1
                    ac = float(np.mean(centered[row, :length] ** 2))
                    costs.append(min(1., ac))
                    injected += int(ac > 0)
                    continue
                groups = int(self._harmonics[index])
                voiced = bool(groups and np.isfinite(self._off_harmonic[index]))
                if voiced:
                    source_noise.append(float(self._off_harmonic[index]))
                else:
                    spectral_only += 1
                if power <= 0:
                    collapsed += 1
                    costs.append(1.)
                    shape_losses.append(1.)
                    if voiced:
                        missing_balance += 1
                        balance_losses.append(1.)
                    continue
                shape = self._feature(powers[row], self._labels[index], groups)
                # Squared Hellinger distance between probability vectors.
                # Harmonic lobes are grouped; off-harmonic bins stay separate.
                shape_loss = float(np.clip(.5 * np.sum((shape - self._shapes[index]) ** 2), 0, 1))
                shape_losses.append(shape_loss)
                if voiced:
                    noise = float(np.sum(shape[groups:] ** 2))
                    candidate_noise.append(noise)
                    balance = abs(noise - self._off_harmonic[index])
                    balance_losses.append(float(balance))
                    costs.append(.5 * (shape_loss + balance))
                else:
                    costs.append(shape_loss)
        score = float(np.clip(np.mean(costs), 0, 1)) if costs else 0.
        if not costs:
            status = 'unassessed_short_signal'
        elif not source_pitch:
            status = 'spectral_only_no_source_pitch'
        elif not source_noise:
            status = 'no_usable_source_harmonic_balance'
        elif collapsed:
            status = 'source_frozen_balance_with_collapsed_output'
        else:
            status = 'source_frozen_harmonic_noise_balance'
        mean = lambda values: float(np.mean(values)) if values else None
        return dict(schema='lpx-source-noise-balance-summary-v1', score=score, status=status,
                    frames=len(self.starts), assessed_frames=len(costs), short_unassessed_frames=short,
                    source_pitch_mask_frames=source_pitch, voiced_balance_frames=len(source_noise),
                    unclassified_spectrum_frames=spectral_only, source_silent_frames=silent_source,
                    candidate_collapsed_active_frames=collapsed, injected_silent_source_frames=injected,
                    missing_candidate_balance_frames=missing_balance,
                    source_off_harmonic_fraction_mean=mean(source_noise),
                    candidate_off_harmonic_fraction_mean_observed=mean(candidate_noise),
                    balance_absolute_error_mean_with_missing_penalty=mean(balance_losses),
                    fine_shape_hellinger_mean=mean(shape_losses),
                    scope='Source-frozen spectral proxy only; no candidate pitch tracking, gain fitting or perceptual/F0 guarantee. Missing output balance is penalized, never omitted from score.')

    def __call__(self, pcm):
        return self.summary(pcm)['score']

    score = __call__

    def describe(self):
        return dict(name=self.name, frame_samples=self.frame, hop_samples=self.hop,
                    rate_hz=8000, harmonic_upper_hz=3800,
                    harmonic_half_width='min(1.5 FFT bins, source F0/4)',
                    source_pitch_mask_frozen=True, score_bounds=[0., 1.], suggested_external_weight=1.,
                    voiced_score='mean of absolute source-noise balance error and squared Hellinger feature distance',
                    unknown_pitch_score='fine positive-frequency spectral Hellinger distance; no guessed F0',
                    silence_score='injected AC power, capped at 1, with one-PCM-count RMS floor',
                    output_collapse_score=1., short_windows='fewer than 4 samples are unassessed; waveform scorer retains them',
                    level_and_phase='not assessed by normalized shape; retain VoiceObjective and PCM/PWM gates',
                    source_noise_is_target=True, decoder_or_format_changes=False)

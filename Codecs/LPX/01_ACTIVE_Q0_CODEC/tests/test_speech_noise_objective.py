"""Source-noise preservation, fixed-mask and explicit unknown/collapse oracles."""
import json
import unittest
from unittest.mock import patch

import numpy as np

from speech_noise_objective import NoiseObjective
from speech_voice_objective import VoiceObjective
from standard_metrics import pwm_pcm16
from test_speech_voice_objective import tone


def periods(source, value=40.):
    return np.full(max(0, (len(source) - 640) // 160 + 1), value)


class NoiseObjectiveTests(unittest.TestCase):
    def test_self_is_zero_and_quiet_families_remain_finite(self):
        for amplitude in (1, 4, 32, 2000):
            source = tone(amplitude=amplitude, samples=1920)
            objective = NoiseObjective(source, periods(source))
            self.assertEqual(objective(source), 0.)
            for candidate in (tone(100, amplitude, samples=1920),
                              tone(400, amplitude, samples=1920), np.zeros_like(source)):
                value = objective(candidate)
                self.assertGreater(value, 0.)
                self.assertLessEqual(value, 1.)
            json.dumps(objective.describe(), allow_nan=False)
            json.dumps(objective.summary(source), allow_nan=False)

    def test_breathy_source_noise_is_preserved_instead_of_minimized(self):
        rng = np.random.default_rng(145)
        harmonic = tone(amplitude=3000, samples=1920).astype(np.int64)
        breath = np.rint(rng.normal(0, 1000, len(harmonic))).astype(np.int64)
        source = (harmonic + breath).astype(np.int16)
        removed = harmonic.astype(np.int16)
        added = (harmonic + 3 * breath).astype(np.int16)
        objective = NoiseObjective(source, periods(source))
        reference = objective.summary(source)
        dry = objective.summary(removed)
        noisy = objective.summary(added)
        self.assertEqual(reference['score'], 0.)
        self.assertGreater(dry['score'], 0.)
        self.assertGreater(noisy['score'], 0.)
        original_noise = reference['source_off_harmonic_fraction_mean']
        self.assertGreater(original_noise, .01)
        self.assertLess(dry['candidate_off_harmonic_fraction_mean_observed'], original_noise)
        self.assertGreater(noisy['candidate_off_harmonic_fraction_mean_observed'], original_noise)
        self.assertGreater(dry['balance_absolute_error_mean_with_missing_penalty'], 0.)
        self.assertGreater(noisy['balance_absolute_error_mean_with_missing_penalty'], 0.)

    def test_source_mask_cannot_be_evaded_by_output_pitch_disappearance(self):
        source = tone(amplitude=32, samples=1920)
        objective = NoiseObjective(source, periods(source))
        with patch('voice_character.track_pitch', side_effect=AssertionError('No candidate tracker permitted')):
            result = objective.summary(np.zeros_like(source))
        self.assertEqual(result['score'], 1.)
        self.assertEqual(result['voiced_balance_frames'], len(periods(source)))
        self.assertEqual(result['missing_candidate_balance_frames'], result['voiced_balance_frames'])
        self.assertIsNone(result['candidate_off_harmonic_fraction_mean_observed'])
        self.assertEqual(result['balance_absolute_error_mean_with_missing_penalty'], 1.)
        self.assertGreater(result['candidate_collapsed_active_frames'], 0)

    def test_silence_injection_unknown_pitch_and_short_intervals_are_explicit(self):
        silence = np.zeros(1920, np.int16)
        rng = np.random.default_rng(77)
        injected = rng.integers(-3, 4, len(silence), dtype=np.int16)
        objective = NoiseObjective(silence, None)
        self.assertEqual(objective(silence), 0.)
        result = objective.summary(injected)
        self.assertGreater(result['score'], 0.)
        self.assertEqual(result['status'], 'spectral_only_no_source_pitch')
        self.assertEqual(result['voiced_balance_frames'], 0)
        self.assertIsNone(result['source_off_harmonic_fraction_mean'])
        self.assertGreater(result['injected_silent_source_frames'], 0)
        for count in (1, 2, 3):
            source = np.zeros(count, np.int16)
            short = NoiseObjective(source, []).summary(source)
            self.assertEqual(short['status'], 'unassessed_short_signal')
            self.assertEqual(short['assessed_frames'], 0)
            self.assertEqual(short['score'], 0.)
            json.dumps(short, allow_nan=False)

    def test_unknown_source_pitch_compares_spectrum_without_guessing_harmonics(self):
        rng = np.random.default_rng(165)
        source = rng.integers(-1000, 1001, 1920, dtype=np.int16)
        objective = NoiseObjective(source, None)
        smoothed = np.rint(np.convolve(source.astype(float), np.ones(7) / 7, mode='same')).astype(np.int16)
        self.assertEqual(objective(source), 0.)
        self.assertGreater(objective(smoothed), 0.)
        result = objective.summary(smoothed)
        self.assertEqual(result['source_pitch_mask_frames'], 0)
        self.assertEqual(result['voiced_balance_frames'], 0)
        self.assertGreater(result['unclassified_spectrum_frames'], 0)
        self.assertIsNone(result['balance_absolute_error_mean_with_missing_penalty'])
        self.assertEqual(objective(np.zeros_like(source)), 1.)

    def test_pcm_and_pwm_collapse_do_not_claim_sub_lsb_pitch_preservation(self):
        source = tone(amplitude=2, samples=1920)
        pwm = pwm_pcm16(source)
        self.assertFalse(np.any(pwm))
        pcm_objective = NoiseObjective(source, periods(source))
        self.assertEqual(pcm_objective(source), 0.)
        self.assertEqual(pcm_objective(pwm), 1.)
        pwm_objective = NoiseObjective(pwm, periods(source))
        report = pwm_objective.summary(pwm)
        self.assertEqual(report['score'], 0.)
        self.assertEqual(report['voiced_balance_frames'], 0)
        self.assertEqual(report['status'], 'no_usable_source_harmonic_balance')
        self.assertIsNone(report['source_off_harmonic_fraction_mean'])
        json.dumps(report, allow_nan=False)

    def test_owned_inputs_and_analysis_only_gain_invariance(self):
        source = tone(amplitude=200, samples=1920)
        saved = source.copy()
        source_periods = periods(source)
        original_periods = source_periods.copy()
        objective = NoiseObjective(source, source_periods)
        source[:] = 0
        source_periods[:] = 80
        self.assertEqual(objective(saved), 0.)
        self.assertFalse(objective.reference.flags.writeable)
        self.assertFalse(objective.periods.flags.writeable)
        with self.assertRaises(ValueError):
            objective.periods[0] = 80
        rng = np.random.default_rng(90)
        candidate = saved + rng.integers(-5, 6, len(saved), dtype=np.int16)
        louder = NoiseObjective(saved.astype(np.int32) * 8, original_periods)
        self.assertAlmostEqual(objective(candidate), louder(candidate.astype(np.int32) * 8), places=12)
        self.assertLess(objective(saved * 2), 1e-20)
        self.assertGreater(objective.voice_objective(saved * 2), 0.)
        self.assertLess(objective(-saved), 1e-20)
        self.assertGreater(objective.voice_objective(-saved), 0.)

    def test_shared_periodogram_matches_direct_formula_including_partial_tail(self):
        source = tone(amplitude=1000, samples=803)
        voice = VoiceObjective(source)
        indices = np.arange(len(voice.starts))
        _, centered = voice._windows(source, 0, indices)
        actual = voice._periodograms(centered, indices)
        for index, start in enumerate(voice.starts):
            length = int(voice.lengths[index])
            frame = source[start:start + length].astype(float)
            expected = abs(np.fft.rfft((frame - frame.mean()) * np.hanning(length), n=640)[1:]) ** 2
            np.testing.assert_array_equal(actual[index], expected)

    def test_bad_sources_periods_candidates_and_lengths_are_rejected(self):
        source = tone(samples=1920)
        for invalid in (np.array([], np.int16), source.astype(float), source.reshape(2, -1),
                        np.array([32768]), np.array([True])):
            with self.assertRaises(ValueError):
                NoiseObjective(invalid, None)
        for invalid in ([40], np.full(9, 0.), np.full(9, np.inf), np.full(9, 999.)):
            with self.assertRaises(ValueError):
                NoiseObjective(source, invalid)
        objective = NoiseObjective(source, periods(source))
        for invalid in (source[:-1], source.astype(float), np.array([], np.int16)):
            with self.assertRaises(ValueError):
                objective(invalid)


if __name__ == '__main__':
    unittest.main()

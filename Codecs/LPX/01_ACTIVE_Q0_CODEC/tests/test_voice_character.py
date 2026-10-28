"""Known-period/quiet-quantization oracles and missing-output regressions."""
from dataclasses import FrozenInstanceError
import json
import unittest

import numpy as np

from standard_metrics import pwm_pcm16
from voice_character import (PitchSettings, compare_voice, fixed_periodicity_error,
                             spectral_shape_error, track_pitch)


def tone(hz, amplitude=1000, samples=8000):
    return np.rint(amplitude * np.sin(2 * np.pi * hz * np.arange(samples) / 8000)).astype(np.int16)


class VoiceCharacterTests(unittest.TestCase):
    def test_known_period_survives_quiet_pcm16_quantization(self):
        # These amplitudes are chosen independently of any corpus recording.
        for amplitude in (1, 2, 4, 16, 256, 4096):
            pcm = tone(200, amplitude)
            track = track_pitch(pcm)
            self.assertTrue(np.all(track.voiced), amplitude)
            np.testing.assert_allclose(track.hz, 200, rtol=.003)
            report = compare_voice(pcm, pcm, reference_track=track)
            self.assertEqual(report['pitch_failure_fraction'], 0)
            self.assertEqual(report['relative_spectral_shape_rms_db_mean'], 0)
            self.assertLess(report['fixed_decoded_period_error_mean'], .001)
        for hz in (80, 110, 203, 400, 600):
            track = track_pitch(tone(hz, 4000))
            self.assertTrue(np.all(track.voiced), hz)
            np.testing.assert_allclose(track.hz, hz, rtol=.006)
        # Fractional periods need the integer trough on either side of a bound.
        track = track_pitch(tone(599, 4000), PitchSettings(fmax=600))
        self.assertTrue(np.all(track.voiced))
        np.testing.assert_allclose(track.hz, 599, rtol=.006)

    def test_octave_errors_are_not_hidden_by_pair_medians(self):
        source = tone(200)
        for frequency, field in ((100, 'near_half_pitch_frames'), (400, 'near_double_pitch_frames')):
            report = compare_voice(source, tone(frequency))
            self.assertEqual(report[field], report['reference_period_frames'])
            self.assertEqual(report['pitch_failure_fraction'], 1)
            self.assertGreater(report['absolute_cents_median_paired'], 1190)
        mixed = np.r_[tone(100, samples=4000), tone(400, samples=4000)]
        report = compare_voice(source, mixed)
        self.assertGreater(report['near_half_pitch_frames'], 10)
        self.assertGreater(report['near_double_pitch_frames'], 10)
        self.assertGreater(report['pitch_failure_fraction'], .8)

    def test_silent_or_aperiodic_output_cannot_evade_reference_periods(self):
        source = tone(200, 2)
        rng = np.random.default_rng(1445)
        for candidate in (np.zeros_like(source), rng.integers(-3, 4, len(source), dtype=np.int16)):
            report = compare_voice(source, candidate)
            self.assertGreater(report['missing_decoded_period_frames'], 0)
            self.assertGreater(report['pitch_failure_fraction'], .9)
            self.assertIsNone(report['decoded_hz_median_paired'])
            self.assertGreater(report['fixed_decoded_period_error_mean'], .8)
            self.assertEqual(report['pitch_status'], 'pitch_mismatch_or_missing')
            json.dumps(report, allow_nan=False)
        # The fixed 8-bit PWM transfer erases this representable PCM16 tone.
        pwm = pwm_pcm16(source)
        self.assertFalse(np.any(pwm))
        report = compare_voice(source, pwm)
        self.assertEqual(report['pitch_failure_fraction'], 1)
        self.assertEqual(report['decoded_collapsed_active_frames'], report['frames'])

    def test_source_silence_and_subresolution_are_unassessed(self):
        silence = np.zeros(8000, np.int16)
        constant = np.full_like(silence, 2)
        for source in (silence, constant):
            report = compare_voice(source, source)
            self.assertEqual(report['pitch_status'], 'unassessed_no_reference_periodicity')
            self.assertIsNone(report['pitch_failure_fraction'])
            self.assertIsNone(report['reference_hz_median'])
            self.assertEqual(report['reference_period_frames'], 0)
            json.dumps(report, allow_nan=False)
        subresolution = np.zeros(8000, np.int16)
        subresolution[::100] = 1
        self.assertFalse(np.any(track_pitch(subresolution).voiced))
        self.assertEqual(fixed_periodicity_error(silence[:640], 40), 1)
        self.assertEqual(fixed_periodicity_error(constant[:640], 40), 1)

    def test_fractional_period_oracle_and_shape_gain_invariance(self):
        # Independent analytic sine has a known period even between samples.
        source = tone(203, 4000)
        self.assertLess(fixed_periodicity_error(source[:640], 8000 / 203), .0001)
        self.assertGreater(fixed_periodicity_error(source[:640], 4000 / 203), 1.9)
        self.assertAlmostEqual(spectral_shape_error(source[:640], -source[:640]), 0)
        quiet = tone(200, 8)
        louder = quiet.astype(np.int32) * 64
        report = compare_voice(quiet, louder)
        self.assertEqual(report['pitch_failure_fraction'], 0)
        self.assertLess(report['relative_spectral_shape_rms_db_mean'], 1e-10)
        self.assertGreater(report['decoded_level']['rms_pcm16'], report['reference_level']['rms_pcm16'])
        # Same pulse repetition, intentionally changed spectral envelope.
        time = np.arange(8000) / 8000
        a = np.rint(2000 * (np.sin(2*np.pi*200*time) + .2*np.sin(2*np.pi*600*time))).astype(np.int16)
        b = np.rint(2000 * (np.sin(2*np.pi*200*time) + .8*np.sin(2*np.pi*600*time))).astype(np.int16)
        report = compare_voice(a, b)
        self.assertEqual(report['pitch_failure_fraction'], 0)
        self.assertGreater(report['relative_spectral_shape_rms_db_mean'], 1)

    def test_owned_frozen_snapshot_and_exact_reference_binding(self):
        source = tone(200)
        track = track_pitch(source)
        old = track.hz.copy()
        source[:] = 0
        np.testing.assert_array_equal(track.hz, old)
        for array in (track.hz, track.period, track.frame_start, track.sample_center,
                      track.confidence, track.rms, track.voiced, track.status):
            self.assertFalse(array.flags.writeable)
        with self.assertRaises(FrozenInstanceError):
            track.samples = 3
        with self.assertRaises(FrozenInstanceError):
            track.settings.fmin = 10
        with self.assertRaises(ValueError):
            compare_voice(source, source, reference_track=track)
        np.testing.assert_array_equal(track.sample_center, track.frame_start + 320)
        self.assertEqual(track.frame_start[0], 0)
        self.assertLessEqual(track.frame_start[-1] + 640, 8000)

    def test_short_inputs_and_invalid_geometry_do_not_get_fabricated_frames(self):
        source = tone(200, samples=639)
        report = compare_voice(source, source)
        self.assertEqual(report['frames'], 0)
        self.assertEqual(report['reference_level']['samples'], 639)
        self.assertEqual(report['pitch_status'], 'unassessed_no_reference_periodicity')
        for bad in (np.array([], np.int16), np.zeros((2, 3), np.int16),
                    np.array([32768]), np.array([1.5]), np.array([True])):
            with self.assertRaises(ValueError):
                track_pitch(bad)
        with self.assertRaises(ValueError):
            compare_voice(tone(200), tone(200, samples=7999))
        for kwargs in ({'rate': True}, {'frame_samples': 160}, {'fmin': np.nan},
                       {'fmax': 5000}, {'hop_samples': 1000}, {'min_rms_pcm16': 0},
                       {'trough_threshold': 1}):
            with self.assertRaises(ValueError):
                PitchSettings(**kwargs)
        for period in (0, np.nan, 640):
            with self.assertRaises(ValueError):
                fixed_periodicity_error(np.zeros(640), period)


if __name__ == '__main__':
    unittest.main()

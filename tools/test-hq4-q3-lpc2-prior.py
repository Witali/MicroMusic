"""Soft-prior contracts: stable LPC projection, bounded moves and honest fallback."""
import importlib.util
import json
from pathlib import Path
import random
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('q3_lpc2_prior_tested', ROOT/'tools/probe-hq4-q3-lpc2-prior.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def forward(reflections):
    a = np.array([1.])
    for k in reflections:
        a = np.r_[a, 0.]+k*np.r_[0., a[::-1]]
    return a[1:]


def metrics():
    return dict(stoi=.84, estoi=.65, fine_log_error=.49, envelope_error=.60,
        unsupported_energy=.20, missing_energy=.20, harmonic_track_loss=.95,
        missing_reference_energy=.10, extra_candidate_energy=.16,
        weighted_match_rate=.90, continuity_break_rate=.02, difference_loss=.73)


class SoftPriorTests(unittest.TestCase):
    def setUp(self):
        self.frames = np.array([[30, 4, 0x88, 0x88, 0x88, 0x88],
                                [30, 4, 0x88, 0x88, 0x88, 0x88],
                                [0, 2, 0x99, 0x88, 0x88, 0x88]], np.uint8)
        self.durations = np.array([64, 64, 64], np.uint16)
        reflections = [.2, -.1, .15, -.2, .1, -.05, .1, -.15, .05, -.1]
        self.native = dict(meta=dict(sr=7500, H=64, samples=192),
            frameCoefficients=[forward(reflections).tolist()]*3,
            frameF0=[150., 200., 0.], frameGain=[.04, .02, .01])
        self.prior = probe.Prior(self.native, self.frames, self.durations)

    def test_full_polynomial_step_down_recovers_first_eight_without_ar_truncation(self):
        k = np.array([.2, -.1, .3, -.2, .1, -.05, .2, -.15, .1, -.2])
        np.testing.assert_allclose(probe.step_down(forward(k)), k, atol=1e-12)
        # The final two stages alter the leading AR terms. Truncating those
        # terms before step-down would be a different eight-pole predictor.
        self.assertGreater(np.max(abs(probe.step_down(forward(k)[:8])-k[:8])), .01)
        for invalid in ([1.], [np.nan], []):
            with self.assertRaises(ValueError):
                probe.step_down(invalid)

    def test_prior_remaps_new_boundaries_and_preserves_sample_descriptor(self):
        _, periods, gains = self.prior.mapped(self.durations)
        np.testing.assert_array_equal(periods, [50, 38, 0])
        _, merged_periods, _ = self.prior.mapped(np.array([128, 64]))
        np.testing.assert_array_equal(merged_periods, [38, 0])
        self.assertTrue(np.all((gains >= 0) & (gains <= 15)))
        with self.assertRaises(ValueError):
            self.prior.mapped(np.array([64, 64]))

    def test_reflection_moves_one_step_and_preserves_shared_update_run(self):
        for seed in range(30):
            f, d, _ = probe.soft_proposal(self.frames, self.durations, self.prior,
                                          random.Random(seed), 'reflection')
            np.testing.assert_array_equal(f[:, :2], self.frames[:, :2])
            np.testing.assert_array_equal(d, self.durations)
            original = np.c_[self.frames[:, 2:] & 15, self.frames[:, 2:] >> 4].astype(int)
            changed = np.c_[f[:, 2:] & 15, f[:, 2:] >> 4].astype(int)
            self.assertLessEqual(np.max(abs(changed-original)), 1)
            self.assertLessEqual(len(probe.pack_stream(f, d)), len(probe.pack_stream(self.frames, self.durations)))
            # Equal original first halves remain equal after a group mutation.
            np.testing.assert_array_equal(f[0, 2:4], f[1, 2:4])

    def test_pitch_step_does_not_silently_toggle_voicing(self):
        for seed in range(30):
            f, d, _ = probe.soft_proposal(self.frames, self.durations, self.prior,
                                          random.Random(seed), 'pitch')
            self.assertLessEqual(np.max(abs(f[:, 0].astype(int)-self.frames[:, 0].astype(int))), 1)
            np.testing.assert_array_equal(f[:, 0] > 0, self.frames[:, 0] > 0)
            np.testing.assert_array_equal(f[:, 1:], self.frames[:, 1:])

    def test_fields_allow_a_valid_eeprom_sized_stream_above_flash_only_cap(self):
        f = np.tile(self.frames[:1], (106, 1))
        f[1::2, 2:] = 0x99
        d = np.full(106, 64, np.uint16)
        payload = probe.validate_fields(f, d, 106*64)
        self.assertEqual(len(payload), 636)
        self.assertGreater(len(payload), 617)
        self.assertLessEqual(len(payload), 639)
        with self.assertRaises(ValueError):
            probe.validate_fields(f, d, 106*64-1)

    def test_global_screen_has_48_controls_and_does_not_select_scalar_only_gain(self):
        base = metrics()
        class Objective:
            def evaluate(self, f, d):
                return dict(base, difference_loss=np.float64(.1), stoi=.7)
        screen = probe.whole_transfer_screen(Objective(), self.frames, self.durations, self.prior, base)
        self.assertEqual(len(screen), 48)
        self.assertFalse(any(row['eligible'] or row['improved'] for row in screen))
        json.dumps(screen)
        class PassingObjective:
            def evaluate(self, f, d):
                return dict(base, difference_loss=np.float64(.1))
        passing = probe.whole_transfer_screen(PassingObjective(), self.frames, self.durations, self.prior, base)
        self.assertTrue(all(row['improved'] for row in passing))
        json.dumps(passing)

    def test_bad_or_nonfinite_candidate_cannot_replace_incumbent(self):
        base = metrics()
        self.assertIsInstance(probe.eligible(dict(base, harmonic_track_loss=np.float64(.9)), base), bool)
        for key in probe.GUARDED_KEYS:
            invalid = dict(base)
            invalid[key] = float('nan')
            self.assertFalse(probe.eligible(invalid, base))
            del invalid[key]
            self.assertFalse(probe.eligible(invalid, base))
        original = self.frames
        class Objective:
            def evaluate(self, f, d):
                return base.copy() if np.array_equal(f, original) else dict(base, difference_loss=.1, stoi=.7)
        best, report = probe.fit(Objective(), self.frames, self.durations, self.prior, proposals=100, seed=17)
        np.testing.assert_array_equal(best[0], self.frames)
        np.testing.assert_array_equal(best[1], self.durations)
        self.assertEqual(best[2], base)
        self.assertEqual(report['accepted_elites'], 0)
        self.assertGreater(report['counts']['evaluated'], 0)
        with self.assertRaises(ValueError):
            probe.fit(Objective(), self.frames, self.durations, self.prior, proposals=2001)


if __name__ == '__main__':
    unittest.main()

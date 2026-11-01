"""Characterize legacy bytes and explicitly enable zero-step proposals."""
import unittest
from unittest.mock import patch

import numpy as np

from batch_decoder import BatchSession
from q0_model import table
import speech_compact as compact
import speech_v4 as speech
from standard_metrics import pwm_duties


def triangle(count, peak):
    phase = np.arange(count) % 40
    return np.rint(((20 - abs(phase - 20)) / 10 - 1) * peak).astype(np.int16)


class SpeechZeroScaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.common_session = BatchSession('batch', speech=True, speech_compact=True)
        cls.common = cls.common_session.__enter__()
        cls.only_session = BatchSession('batch', speech=True, speech_compact=True, compact_only=True)
        cls.only = cls.only_session.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.only_session.__exit__()
        cls.common_session.__exit__()

    def test_normal_level_default_bytes_match_prechange_synthetic_goldens(self):
        # Captured before the option was added, from a synthetic 200-Hz integer
        # triangle at peak6000. These are codec fixtures, never corpus audio.
        expected = {
            4: '4c3448590404401f40010000663600004001a000619cd4e0b499570bb4c946175da6e5f9f8d0c183',
            6: '4c3448590406401f40010000663600004001a00083e14c1a78b6730e54cbd9ad041f3b087421e8abe59242839f0f02c00cf0',
        }
        reference = triangle(320, 6000)
        for profile in (4, 6):
            default, pcm, report = speech.encode(reference, profile, self.common)
            explicit, actual, _ = speech.encode(reference, profile, self.common, allow_zero_scale=False)
            self.assertEqual(default.hex(), expected[profile])
            self.assertEqual(explicit, default)
            np.testing.assert_array_equal(actual, pcm)
            self.assertFalse(report['allow_zero_scale'])

    def test_opt_in_true_silence_is_exact_in_both_layouts_at_tail_boundaries(self):
        for profile in (4, 6):
            for pre in (0, 13926):
                for count in (1, 19, 20, 39, 40, 159, 160, 319, 320, 321, 641):
                    reference = np.zeros(count, np.int16)
                    blob, pcm, report = speech.encode(reference, profile, self.common,
                                                      pre=pre, allow_zero_scale=True)
                    np.testing.assert_array_equal(pcm, reference)
                    np.testing.assert_array_equal(speech.decode_model(blob), reference)
                    params = speech.unpack(blob)[4]
                    if profile == 4:
                        self.assertTrue(all(scale == 0 for scale, lag, gain in params))
                    # Profile6 can keep a tied legacy scale with amp0; actual
                    # silence is the contract, not rewriting equal-cost fields.
                    packed = compact.repack(blob)[0]
                    for decoder in (self.common, self.only):
                        np.testing.assert_array_equal(decoder.decode_one_s16(packed, count), reference)
                        np.testing.assert_array_equal(decoder.decode_one(packed, count),
                                                      np.full(count, 128, np.uint8))
                    self.assertEqual(len(blob), 20 + ((count + 319) // 320) * (20 if profile == 4 else 30))
                    self.assertTrue(report['allow_zero_scale'])

    def test_profile_specific_legacy_silence_behavior_is_not_changed_by_default(self):
        for profile in (4, 6):
            reference = np.zeros(320, np.int16)
            old, pcm, _ = speech.encode(reference, profile, self.common)
            new, zero, _ = speech.encode(reference, profile, self.common, allow_zero_scale=True)
            if profile == 4:
                self.assertGreater(np.count_nonzero(pcm), 0)
            else:
                self.assertEqual(np.count_nonzero(pcm), 0)
                self.assertEqual(old, new)
            self.assertEqual(np.count_nonzero(zero), 0)
            self.assertEqual(len(old), len(new))

    def test_expanded_scale_set_retains_neighborhood_and_adds_minimum_step(self):
        reference = np.full(160, 5000, np.int64)
        co = np.zeros((160, 10), np.int64)
        steps = table('scale_table.inc')
        minimum = next(int(steps[code * 8]) for code in range(32) if steps[code * 8])
        calls = []

        def trial(target, coefficients, history, dd, cc, ring, cursor, pre, step, lag, gain, profile):
            calls.append(int(step))
            return (float((step - minimum) ** 2), history, dd, cc, ring,
                    np.zeros((8, 2), np.int64), np.zeros(160, np.int16))

        with patch('speech_v4.search_block', side_effect=trial):
            params, _, _ = speech.search.py_func(reference, co, steps, 0, 4,
                                                 allow_zero_scale=True)
        self.assertEqual(params[0, 0], 6)  # Canonical first nonzero step code.
        self.assertIn(0, calls)
        self.assertIn(minimum, calls)
        # This deliberately high residual has legacy center29; all its old
        # candidates must survive addition of the two new canonical options.
        self.assertTrue(set(int(steps[code * 8]) for code in range(27, 32)).issubset(calls))

    def test_quiet_harmonic_first_block_can_use_expanded_set_without_gain_fitting(self):
        for profile in (4, 6):
            for peak in (1, 3, 25, 806):
                reference = triangle(160, peak)
                before = reference.copy()
                _, old, _ = speech.encode(reference, profile, self.common)
                blob, pcm, _ = speech.encode(reference, profile, self.common, allow_zero_scale=True)
                old_error = sum((int(a) - int(b)) ** 2 for a, b in zip(reference, old))
                new_error = sum((int(a) - int(b)) ** 2 for a, b in zip(reference, pcm))
                self.assertLessEqual(new_error, old_error)
                np.testing.assert_array_equal(reference, before)
                packed = compact.repack(blob)[0]
                np.testing.assert_array_equal(self.only.decode_one_s16(packed, 160), pcm)
                np.testing.assert_array_equal(self.only.decode_one(packed, 160), pwm_duties(pcm))
                # This is integer correctness/error evidence, not a claim that
                # sub-LSB pitch survives native PCM or physical8-bit output.

    def test_flag_requires_an_explicit_boolean(self):
        reference = triangle(160, 100)
        for flag in (0, 1, 'yes', None, []):
            with self.assertRaises(ValueError):
                speech.encode(reference, 4, self.common, allow_zero_scale=flag)


if __name__ == '__main__':
    unittest.main()

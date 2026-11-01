"""Exactness and proposal-policy tests, including low-level/tail boundaries."""
import unittest

import numpy as np

from batch_decoder import BatchSession
import speech_compact as compact
from reseed_speech_excitation import reseed, _local_cost
from standard_metrics import pwm_duties
from test_speech_v4 import fixture


class ReseedExcitationTests(unittest.TestCase):
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

    def test_perfect_control_stays_identical_at_audible_and_stored_tail_boundaries(self):
        for profile in (4, 6):
            for count in (1, 19, 20, 39, 40, 159, 160, 319, 320, 321, 641):
                blob = compact.repack(fixture(profile, count))[0]
                reference = compact.decode_model(blob)
                result, pcm, report = reseed(reference, blob, self.common,
                    source_lags=np.zeros((count + 159) // 160, np.int64), gain=None, horizon=40)
                self.assertEqual(result, blob)
                np.testing.assert_array_equal(pcm, reference)
                np.testing.assert_array_equal(self.only.decode_one_s16(result, count), pcm)
                np.testing.assert_array_equal(self.only.decode_one(result, count), pwm_duties(pcm))
                self.assertEqual(report['changed_parameter_blocks'], 0)
                self.assertEqual(report['changed_base_pulses'], 0)
                self.assertFalse(report['quality_adopted'])
                self.assertLessEqual(report['candidate_evaluations'],
                    ((count + 19) // 20) * (33 if profile == 4 else 321))

    def test_known_source_period_recovers_reachable_target_without_scale_or_spectral_change(self):
        for profile in (4, 6):
            fields = list(compact.unpack(compact.repack(fixture(profile, 160))[0]))
            fields[3] = [(20, 80, 8), (22, 73, 6)]
            blob = compact.pack(*fields[:7], extras=fields[7])[0]
            target = list(fields)
            target[3] = [(20, 40, 14), fields[3][1]]
            reference = compact.decode_model(compact.pack(*target[:7], extras=target[7])[0])
            result, pcm, report = reseed(reference, blob, self.common,
                                         source_lags=[40], gain=14, horizon=160)
            np.testing.assert_array_equal(pcm, reference)
            after = compact.unpack(result)
            self.assertEqual(after[:3], tuple(fields[:3]))
            self.assertEqual(after[3], target[3])
            self.assertEqual(after[4:], tuple(fields[4:]))
            self.assertEqual(report['changed_parameter_blocks'], 1)
            self.assertEqual(report['changed_base_pulses'], 0)

    def test_existing_gain_can_be_retained_for_a_supplied_source_period(self):
        fields = list(compact.unpack(compact.repack(fixture(4, 160))[0]))
        fields[3] = [(20, 80, 8), (22, 73, 6)]
        blob = compact.pack(*fields[:7], extras=fields[7])[0]
        target = list(fields)
        target[3] = [(20, 40, 8), fields[3][1]]
        reference = compact.decode_model(compact.pack(*target[:7], extras=target[7])[0])
        result, pcm, report = reseed(reference, blob, self.common,
                                     source_lags=[40], gain=None, horizon=160)
        np.testing.assert_array_equal(pcm, reference)
        self.assertEqual(compact.unpack(result)[3][0], (20, 40, 8))
        self.assertIsNone(report['forced_gain'])

    def test_periodicity_proposal_penalizes_collapse_and_is_relative_to_level(self):
        reference = np.tile(np.r_[np.arange(10), np.arange(10, 0, -1)], 8).astype(np.int64)
        reference -= 5
        self.assertEqual(_local_cost(reference, reference, 20, 8.), 0.)
        zero = np.zeros_like(reference)
        self.assertAlmostEqual(_local_cost(reference, zero, 20, 8.), 9.)
        small = reference * 2
        loud = reference * 64
        self.assertAlmostEqual(_local_cost(reference, small, 20, 8.),
                               _local_cost(loud, small * 64, 20, 8.))
        # The legacy proposal path is exactly plain integer SSE when disabled.
        expected = int(sum(int(value) ** 2 for value in reference))
        self.assertEqual(_local_cost(reference, zero, 20, 0.), expected)

    def test_reseed_is_owned_deterministic_and_preserves_forced_extras_and_tails(self):
        blob = compact.repack(fixture(4, 641), extras=[(i % 40, -8 if i & 1 else 7)
                                for i in range(24)])[0]
        original = bytearray(blob)
        reference = compact.decode_model(blob)
        reference = (reference.astype(np.int64) // 64).astype(np.int16)
        reference_before = reference.copy()
        lags = np.array([40, 40, 0, 39, 0], np.int64)
        before = lags.copy()
        first = reseed(reference, original, self.common, source_lags=lags,
                       gain=14, horizon=320, periodicity_weight=8.)
        second = reseed(reference, original, self.common, source_lags=lags,
                        gain=14, horizon=320, periodicity_weight=8.)
        self.assertEqual(first[0], second[0])
        np.testing.assert_array_equal(first[1], second[1])
        np.testing.assert_array_equal(reference, reference_before)
        np.testing.assert_array_equal(lags, before)
        self.assertEqual(original, blob)
        self.assertIsInstance(first[0], bytes)
        fields, output = compact.unpack(blob), compact.unpack(first[0])
        self.assertEqual(output[5:], fields[5:])
        self.assertEqual(output[3][5:], fields[3][5:])
        self.assertEqual(output[4][33:], fields[4][33:])
        self.assertLessEqual(len(first[0]), len(blob))
        np.testing.assert_array_equal(self.only.decode_one_s16(first[0], 641), first[1])

    def test_invalid_pitch_settings_and_inputs_are_rejected(self):
        blob = compact.repack(fixture(4, 160))[0]
        reference = compact.decode_model(blob)
        bad = [dict(source_lags=[17]), dict(source_lags=[146]), dict(source_lags=[40.]),
               dict(source_lags=[True]), dict(source_lags=[]), dict(source_lags=[40, 40]),
               dict(source_lags=[0], horizon=True), dict(source_lags=[0], horizon=80.),
               dict(source_lags=[0], gain=True), dict(source_lags=[0], gain=7),
               dict(source_lags=[0], gain=-2), dict(source_lags=[0], gain=16),
               dict(source_lags=[0], periodicity_weight=True),
               dict(source_lags=[0], periodicity_weight=float('nan')),
               dict(source_lags=[0], periodicity_weight=float('inf')),
               dict(source_lags=[0], periodicity_weight=-1.)]
        for settings in bad:
            with self.subTest(settings=settings):
                with self.assertRaises(ValueError):
                    reseed(reference, blob, self.common, **settings)
        for invalid_reference in (reference[:-1], reference.astype(float), np.array([[0]])):
            with self.assertRaises(ValueError):
                reseed(invalid_reference, blob, self.common, source_lags=[0])
        with self.assertRaises(ValueError):
            reseed(reference, 160, self.common, source_lags=[0])

    def test_native_disagreement_is_never_a_valid_reseed(self):
        class IncorrectDecoder:
            def decode_one_s16(self, blob, n):
                return np.full(n, 32767, np.int16)
        blob = compact.repack(fixture(4, 160))[0]
        with self.assertRaises(AssertionError):
            reseed(compact.decode_model(blob), blob, IncorrectDecoder(), source_lags=[40])


if __name__ == '__main__':
    unittest.main()

import unittest
from unittest.mock import patch

import numpy as np

from batch_decoder import BatchSession
import speech_compact as compact
from encode_speech_voice import encode, prepare_level, _voice_gate, _quality
from voice_character import compare_voice


def tone(n=8000, amplitude=32, frequency=200):
    t = np.arange(n) / 8000
    return np.rint(amplitude * (.7*np.sin(2*np.pi*frequency*t)
                   + .2*np.sin(4*np.pi*frequency*t) + .1*np.sin(6*np.pi*frequency*t))).astype(np.int16)


class VoiceEncoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.common_context = BatchSession('batch', speech=True, speech_compact=True)
        cls.only_context = BatchSession('batch', speech=True, speech_compact=True, compact_only=True)
        cls.common = cls.common_context.__enter__()
        cls.only = cls.only_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.only_context.__exit__()
        cls.common_context.__exit__()

    def test_true_silence_finds_zero_without_amplification_or_extra_bytes(self):
        ref = np.zeros(640, np.int16)
        blob, pcm, report, raw = encode(ref, 4, self.common, compact_decoder=self.only)
        self.assertIsNotNone(blob)
        np.testing.assert_array_equal(pcm, ref)
        self.assertLessEqual(len(blob), report['complete_byte_cap'])
        self.assertEqual(report['level']['gain'], 1)
        self.assertEqual(report['selected']['voice']['reference_period_frames'], 0)
        self.assertTrue(report['native_v5_only_checked'])
        self.assertIn('pwm_voice', report['selected'])
        self.assertIn('target_pwm_voice', report)
        self.assertIn('pwm_voice_proxy_floors_passed', report['trials'][0])
        self.assertIsNotNone(raw)

    def test_no_fit_is_none_instead_of_oversized_fallback(self):
        ref = tone(320)
        blob, pcm, report, raw = encode(ref, 4, self.common, max_bytes=22,
                                       pre_values=(0,), compact_decoder=self.only)
        self.assertIsNone(blob)
        self.assertIsNone(pcm)
        self.assertIsNone(raw)
        self.assertIsNone(report['selected_bytes'])
        self.assertFalse(report['trials'][0]['fits_complete_cap'])

    def test_original_control_cap_and_partial_tail_remain_exact(self):
        for profile in (4, 6):
            ref = tone(641)
            first, _, _, _ = encode(ref, profile, self.common, pre_values=(0,), compact_decoder=self.only)
            result, pcm, report, _ = encode(ref, profile, self.common, baseline=first,
                                            pre_values=(0,), compact_decoder=self.only)
            self.assertEqual(len(pcm), len(ref))
            self.assertEqual(report['complete_byte_cap'], len(first))
            self.assertEqual(report['control_kind'], 'existing_original_level_v5')
            self.assertLessEqual(len(result), len(first))
            np.testing.assert_array_equal(compact.decode_model(result), pcm)

    def test_original_gain_is_preserved_unless_explicitly_requested(self):
        ref = tone(amplitude=4)
        saved = ref.copy()
        target, info = prepare_level(ref)
        np.testing.assert_array_equal(target, ref)
        self.assertEqual(info['gain'], 1)
        self.assertTrue(info['output_level_matches_original'])
        boosted, gain = prepare_level(ref, 'auto-quiet')
        self.assertGreater(gain['gain'], 1)
        self.assertFalse(gain['output_level_matches_original'])
        self.assertEqual(gain['gain'] & (gain['gain'] - 1), 0)
        np.testing.assert_array_equal(boosted.astype(np.int64), ref.astype(np.int64)*gain['gain'])
        np.testing.assert_array_equal(ref, saved)
        for data in (tone(amplitude=2000), np.zeros(100, np.int16), np.full(100, 100, np.int16)):
            _, unchanged = prepare_level(data, 'auto-quiet')
            self.assertEqual(unchanged['gain'], 1)

    def test_auto_level_declares_fresh_control_and_caps_do_not_change(self):
        ref = tone(640, amplitude=4)
        result, _, report, _ = encode(ref, 6, self.common, level_policy='auto-quiet',
                                     pre_values=(0,), compact_decoder=self.only)
        self.assertGreater(report['level']['gain'], 1)
        self.assertEqual(report['control_kind'], 'fresh_legacy_at_declared_target_level')
        self.assertIsNotNone(result)
        self.assertLessEqual(len(result), report['complete_byte_cap'])

    def test_proxy_gate_rejects_octave_and_missing_voice(self):
        ref = tone(amplitude=1024)
        exact = compare_voice(ref, ref)
        self.assertTrue(_voice_gate(exact, exact))
        self.assertFalse(_voice_gate(compare_voice(ref, tone(amplitude=1024, frequency=100)), exact))
        self.assertFalse(_voice_gate(compare_voice(ref, np.zeros_like(ref)), exact))

    def test_nonfinite_external_intelligibility_is_unavailable(self):
        # Fault injection represents a failed optional external metric, which
        # must not compare as an apparently non-regressing numerical score.
        with patch('refine_speech_compact.error_metrics',
                   return_value=dict(error_energy=0., stoi=float('nan'))):
            measured = _quality(tone(640), tone(640), True)
        self.assertIsNone(measured['pcm16']['stoi'])
        self.assertIsNone(measured['pwm8']['stoi'])

    def test_invalid_settings_rejected_before_encoding(self):
        ref = tone(320)
        for settings in (dict(profile=True), dict(profile=5), dict(profile=4, max_bytes=True),
                         dict(profile=4, pre_values=(True,)), dict(profile=4, pre_values=()),
                         dict(profile=4, level_policy='hidden-gain')):
            with self.assertRaises(ValueError):
                encode(ref, decoder=self.common, **settings)
        for data in ([], [32768], np.zeros(64001, np.int16), ref.astype(float)):
            with self.assertRaises(ValueError):
                prepare_level(data)


if __name__ == '__main__':
    unittest.main()

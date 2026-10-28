from pathlib import Path
import tempfile
import unittest

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from voice_character import track_pitch
from voice_input import load_voice_wav, plan_level, quantize_target
from wav_lpc import load_wav


class VoiceInputTests(unittest.TestCase):
    def test_gain_precedes_quantization_for_quiet_float_and_24bit(self):
        time = np.arange(8000) / 8000
        for subtype, amplitude in [('FLOAT', 1e-7), ('PCM_24', 2 ** -22)]:
            with self.subTest(subtype=subtype), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'quiet.wav'
                sf.write(path, amplitude * np.sin(2*np.pi*200*time), 8000, subtype=subtype)
                old, _ = load_wav(path)
                self.assertFalse(np.any(old))
                target, report = load_voice_wav(path)
                self.assertTrue(np.any(target))
                self.assertGreater(report['input_level']['gain'], 1)
                self.assertTrue(report['gain_before_pcm16_rounding'])
                self.assertEqual(report['clipped_input_samples'], 0)
                track = track_pitch(target)
                self.assertEqual(int(track.voiced.sum()), 47)
                self.assertLess(abs(float(np.nanmedian(track.hz)) - 200), 1)
                retained, _ = load_voice_wav(path, 'preserve')
                np.testing.assert_array_equal(retained, old)

    def test_one_whole_record_gain_preserves_quiet_dynamics(self):
        time = np.arange(96000) / 8000
        wave = np.sin(2*np.pi*200*time) * np.r_[np.full(48000, 1e-6), np.full(48000, 8e-6)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'dynamics.wav'
            sf.write(path, wave, 8000, subtype='FLOAT')
            target, report = load_voice_wav(path)
        self.assertEqual(len(target), len(wave))
        ratio = np.std(target[48000:].astype(float)) / np.std(target[:48000].astype(float))
        self.assertAlmostEqual(ratio, 8, delta=.01)
        self.assertGreater(report['input_level']['gain'], 1)
        self.assertEqual(report['clipped_input_samples'], 0)

    def test_pcm16_target_is_exact_declared_integer_multiplier(self):
        rng = np.random.default_rng(81)
        for amplitude in (1, 4, 32, 128, 2048):
            original = rng.integers(-amplitude, amplitude+1, 8000, dtype=np.int16)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'integer.wav'
                sf.write(path, original, 8000, subtype='PCM_16')
                target, report = load_voice_wav(path)
            gain = report['input_level']['gain']
            np.testing.assert_array_equal(target.astype(np.int64), original.astype(np.int64)*gain)
            if amplitude == 2048:
                self.assertEqual(gain, 1)

    def test_silence_and_constant_dc_are_not_amplified(self):
        for values in (np.zeros(320), np.full(320, 100.)):
            plan = plan_level(values)
            self.assertEqual(plan['gain'], 1)
            target, clips = quantize_target(values, plan)
            np.testing.assert_array_equal(target, values)
            self.assertEqual(clips, 0)

    def test_exact_level_boundaries_keep_legacy_decisions(self):
        for amplitude, expected in ((128., 8), (256., 1), (1024., 1)):
            values = np.tile([-amplitude, amplitude], 40)
            self.assertEqual(plan_level(values)['gain'], expected)

    def test_very_quiet_double_variance_does_not_underflow(self):
        wave = 1e-195 * np.sin(2*np.pi*np.arange(8000)/40)
        self.assertEqual(float(np.std(wave)), 0.)
        plan = plan_level(wave)
        target, clips = quantize_target(wave, plan)
        self.assertGreater(float(np.std(target.astype(float))), 1000)
        self.assertEqual(clips, 0)

    def test_quiet_stereo_resamples_before_one_declared_gain(self):
        time = np.arange(4800) / 48000
        channels = np.column_stack((1e-7*np.sin(2*np.pi*200*time),
                                    2e-7*np.sin(2*np.pi*200*time+.25)))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stereo.wav'
            sf.write(path, channels, 48000, subtype='FLOAT')
            original, _ = sf.read(path, dtype='float64', always_2d=True)
            target, report = load_voice_wav(path)
        gain = report['input_level']['gain']
        independent = np.rint(resample_poly(original.mean(axis=1), 1, 6)*32768*gain).astype(np.int16)
        np.testing.assert_array_equal(target, independent)
        self.assertEqual(len(target), 800)
        self.assertEqual(report['input_channels'], 2)
        self.assertEqual(report['input_rate'], 48000)
        self.assertEqual(report['output_rate'], 8000)
        self.assertGreater(gain, 1)
        self.assertEqual(report['clipped_input_samples'], 0)

    def test_invalid_or_nonfinite_input_rejected(self):
        for values in ([], [[1, 2]], [np.nan], [np.inf]):
            with self.assertRaises(ValueError):
                plan_level(values)
        with self.assertRaises(ValueError):
            plan_level([1, 2], 'hidden-gain')


if __name__ == '__main__':
    unittest.main()

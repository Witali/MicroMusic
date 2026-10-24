"""Firmware constant gain preserves midpoint and rejects every clipped sample."""
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from output_level import choose_gain, scale_pcm, describe_level


class OutputLevelTests(unittest.TestCase):
    def test_tiny_phrase_extremes_reach_full_scale_without_clipping(self):
        for raw, gain, expected in (([35, 128, 241], 144, [23, 128, 255]),
                                    ([25, 128, 242], 143, [13, 128, 255])):
            source = np.array(raw, np.uint8)
            self.assertEqual(choose_gain(source), (gain, 7))
            self.assertEqual(scale_pcm(source, gain).tolist(), expected)
            with self.assertRaisesRegex(ValueError, 'clip'):
                scale_pcm(source, gain+1)
            self.assertEqual(describe_level(source, gain, 7)['clippedSamples'], 0)

    def test_byte_lattice_shift_preserves_center_and_exact_waveform(self):
        source = np.array([90, 128, 190], np.uint8)
        self.assertEqual(choose_gain(source, 'shift'), (2, 0))
        self.assertEqual(scale_pcm(source, 2, 0).tolist(), [52, 128, 252])
        with self.assertRaisesRegex(ValueError, 'clip'):
            scale_pcm(source, 4, 0)

    def test_full_scale_and_silence_retain_unity_gain(self):
        for source in (np.array([0, 128, 255], np.uint8), np.full(32, 128, np.uint8)):
            self.assertEqual(choose_gain(source), (128, 7))
            self.assertEqual(choose_gain(source, 'shift'), (1, 0))
            np.testing.assert_array_equal(scale_pcm(source, 128), source)

    def test_fractional_remainder_preserves_quiet_samples_over_time(self):
        source = np.array([127]*4+[128]+[129]*4, np.uint8)
        actual = scale_pcm(source, 192, error_feedback=True)
        self.assertEqual(actual.tolist(), [127, 126, 127, 126, 128, 130, 129, 130, 129])
        error = actual.astype(float)-128-(source.astype(float)-128)*1.5
        self.assertLessEqual(float(abs(np.cumsum(error)).max()), .5)


if __name__ == '__main__':
    unittest.main()

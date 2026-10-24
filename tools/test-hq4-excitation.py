"""Excitation compatibility and actual pulse-width behavior."""
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_core import unpack_stream
from model import decode as legacy
from hq4_excitation import decode


class ExcitationTests(unittest.TestCase):
    def test_original_profile_is_exact_for_all_retained_clips(self):
        for clip in ('chego', 'otvechaesh', 'vinni'):
            f, d = unpack_stream((ROOT/f'ATtiny13A/Sound/codec/release/{clip}/speech.hq').read_bytes())
            np.testing.assert_array_equal(decode(f, d)[0], legacy(f, d, 0))

    def test_dilation_repeats_source_samples_not_pitch_period(self):
        f = np.array([[40, 3, 0x88, 0x88, 0x88, 0x88]], dtype=np.uint8)
        d = np.array([128])
        x = decode(f, d, 1, -1)[0].astype(int)-128
        np.testing.assert_array_equal(x[39:47], [6, 6, 9, 9, 6, 6, -3, -3])
        np.testing.assert_array_equal(x[79:87], x[39:47])

    def test_unvoiced_output_is_unchanged(self):
        f = np.array([[0, 7, 0x88, 0x88, 0x88, 0x88]], dtype=np.uint8)
        d = np.array([128])
        np.testing.assert_array_equal(decode(f, d, 2, 0)[0], legacy(f, d, 0))


if __name__ == '__main__':
    unittest.main()

"""Q3 byte arithmetic and relation to the independently retained Q4 oracle."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_q3 import decode, multiply, render
from model import decode as decode_q4


class Q3Tests(unittest.TestCase):
    def test_every_signed_product_matches_avr_arithmetic_shift(self):
        for x in range(-128, 128):
            for k in range(-8, 8):
                a = x if k >= 0 else ((-x+128)&255)-128
                expected = (((a*abs(k))//8+128)&255)-128
                self.assertEqual(multiply(x, k), expected)

    def test_double_even_q4_coefficients_match_q3_sample_for_sample(self):
        rng = np.random.default_rng(23073)
        f3 = np.empty((13, 6), np.uint8)
        f3[:, 0] = rng.integers(0, 127, len(f3))
        f3[::3, 0] = 0
        f3[:, 1] = rng.integers(0, 64, len(f3))
        low = rng.integers(-4, 4, (len(f3), 4))
        high = rng.integers(-4, 4, (len(f3), 4))
        f3[:, 2:] = (low+8) | ((high+8) << 4)
        f4 = f3.copy()
        f4[:, 2:] = (2*low+8) | ((2*high+8) << 4)
        d = rng.choice(np.array([64, 128, 192, 256], np.uint16), len(f3))
        np.testing.assert_array_equal(decode(f3, d), decode_q4(f4, d, 0))

    def test_wrap_audit_counts_intermediate_failure_even_without_pwm_clipping(self):
        f = np.array([[18, 15, 255, 255, 255, 255]], np.uint8)
        _, counts = render(f, np.array([256], np.uint16), 1)
        self.assertGreater(int(counts.sum()), 0)


if __name__ == '__main__':
    unittest.main()

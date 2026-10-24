"""Rounding oracle at signed boundaries and original HQ4 equivalence."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_precision import decode_precision, multiply
from hq4_core import unpack_stream
from model import decode


class PrecisionTests(unittest.TestCase):
    def test_every_signed_product_and_tie_convention(self):
        for x in range(-128, 128):
            for k in range(-8, 8):
                a = x if k >= 0 else ((-x+128)&255)-128
                self.assertEqual(multiply(x, k, True), ((a*abs(k)+8)//16)&255)
                self.assertEqual(multiply(x, k, False), ((a*abs(k))//16)&255)

    def test_disabled_rounding_matches_all_retained_streams(self):
        for clip in ('chego','otvechaesh','vinni'):
            f, d = unpack_stream((ROOT/'ATtiny13A/Sound/codec/release'/clip/'speech.hq').read_bytes())
            np.testing.assert_array_equal(decode_precision(f, d, False), decode(f, d, 0))


if __name__ == '__main__':
    unittest.main()

"""Explicit raw-step interpolation, old payloads and constant-scale identity."""
from pathlib import Path
import sys
import unittest

import numpy as np

ACTIVE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ACTIVE/'tools'))
import speech_scale_ramp as ramp
import speech_sparse80 as sparse
import speech_compact as compact
from q0_model import table


class ScaleRampContracts(unittest.TestCase):
    def test_exact_eight_phases_zero_endpoint_and_sparse_hold(self):
        steps = table('scale_table.inc')
        for mode in (4, 15):
            n = 960
            frames = 3
            count = frames*2 if mode == 4 else frames
            scales = ([0, 31, 0, 31, 0, 31] if mode == 4 else [0, 31, 0])
            params = [(value, 33, 10) for value in scales]
            pulses = [(0, -8)]*(frames*(16 if mode == 4 else 4))
            blob = ramp.pack(n, mode, [list(range(10))]*frames, params, pulses)
            actual = ramp.raw_step_trace(blob, stored=True)
            expected = []
            for index, code in enumerate(scales):
                target = int(steps[code*8])
                previous = int(steps[scales[max(0, index-1)]*8])
                expected += [(previous*(8-min(k, 8))+target*min(k, 8)+4)//8
                             for k in range(1, 9 if mode == 4 else 17)]
            np.testing.assert_array_equal(actual, expected)
            self.assertGreater(int(actual.max()), 0)
            self.assertLessEqual(int(actual.max()), 4016)
            self.assertEqual(len(actual), count*(8 if mode == 4 else 16))
            if mode == 15:
                self.assertTrue(np.all(actual[24:32] == steps[31*8]))

    def test_constant_scale_matches_old_native_model_semantics(self):
        for mode in (4, 15):
            n = 641
            frames = (n+319)//320
            spectra = [list(range(2, 22, 2))]*frames
            for scale in (0, 8, 16, 31):
                params = [(scale, 31, 12)]*(frames*(2 if mode == 4 else 1))
                pulses = [(0, -8)]*(frames*(16 if mode == 4 else 4))
                blob = ramp.pack(n, mode, spectra, params, pulses, 11469, 4096)
                old = ramp.payload_adapter(blob)
                expected = compact.decode_model(old) if mode == 4 else sparse.decode_model(old)
                np.testing.assert_array_equal(ramp.decode_model(blob), expected)
                self.assertEqual(blob[:4]+old[4:5]+blob[5:], old)
                self.assertEqual(len(ramp.raw_step_trace(blob)), (n+19)//20)

    def test_new_syntax_stays_explicit(self):
        blob = ramp.pack(321, 4, [list(range(10))]*2, [(0, 18, 0)]*4, [(0, -8)]*32)
        with self.assertRaises(ValueError):
            compact.unpack(blob)
        for malformed in (blob[:4]+b'\5'+blob[5:], blob[:5]+b'\x84'+blob[6:], blob[:-1], blob+b'\0'):
            with self.assertRaises((ValueError, EOFError)):
                ramp.unpack(malformed)


if __name__ == '__main__':
    unittest.main()

"""Version9 syntax, exact v5 reference expansion and terminal packets."""
from pathlib import Path
import random
import sys
import unittest

import numpy as np

ACTIVE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ACTIVE/'tools'))
import speech_compact as compact
import speech_meta320 as meta


class Meta320Contracts(unittest.TestCase):
    def test_fixed_fields_and_independent_expansion(self):
        rng = random.Random(90320)
        for n in (1, 19, 20, 159, 160, 319, 320, 321, 639, 640, 641, 19200, 63999):
            count = (n+319)//320
            spectra = [sorted(rng.sample(range(32), 10)) for _ in range(count)]
            params = [(rng.randrange(32), rng.randrange(18, 146), rng.randrange(8)*2) for _ in range(count)]
            pulses = [(rng.choice(meta.POSITIONS), rng.choice((-8, 8))) for _ in range(count*16)]
            pre, bright = rng.randrange(16385), rng.randrange(11470)
            blob = meta.pack(n, spectra, params, pulses, pre, bright)
            self.assertEqual(meta.unpack(blob), (n, spectra, params, pulses, pre, bright))
            expected = compact.pack(n, 4, spectra, [value for value in params for _ in range(2)],
                                    pulses, pre, bright)[0]
            self.assertEqual(meta.expand(blob), expected)
            expanded = compact.unpack(expected)
            self.assertEqual(expanded[2], spectra)
            self.assertEqual(expanded[3], [value for value in params for _ in range(2)])
            self.assertEqual(expanded[4], pulses)

    def test_header_flags_size_and_padding_rejection(self):
        blob = meta.pack(321, [list(range(10))]*2, [(1, 18, 0)]*2, [(0, -8)]*32)
        malformed = [blob[:21], blob[:-1], blob+b'\0', blob[:4]+b'\5'+blob[5:],
            blob[:5]+b'\x83'+blob[6:], blob[:6]+b'\xff\xff'+blob[8:]]
        for data in malformed:
            with self.assertRaises((ValueError, EOFError)):
                meta.unpack(data)
        # The canonical writer pads high unused bits with zero.
        for n in range(1, 6):
            valid = meta.pack(n, [list(range(10))], [(0, 18, 0)], [(0, -8)]*16)
            damaged = valid[:-1]+bytes((valid[-1] | 128,))
            if damaged != valid:
                with self.assertRaises((ValueError, EOFError)):
                    meta.unpack(damaged)

    def test_complete_model_matches_ordinary_v5(self):
        fields = 641, [list(range(10))]*3, [(12, 31, 10), (9, 45, 14), (0, 18, 0)], \
                 [(meta.POSITIONS[(i*7)%16], -8 if i%3 else 8) for i in range(48)]
        blob = meta.pack(*fields)
        np.testing.assert_array_equal(meta.decode_model(blob), compact.decode_model(meta.expand(blob)))


if __name__ == '__main__':
    unittest.main()

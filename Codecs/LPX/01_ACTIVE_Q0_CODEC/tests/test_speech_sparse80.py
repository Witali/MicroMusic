"""Canonical host sparse80 syntax agrees with the separate original oracle."""
import importlib.util
from pathlib import Path
import random
import sys
import unittest

ACTIVE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ACTIVE/'tools'))
import speech_sparse80 as sparse

spec = importlib.util.spec_from_file_location('sparse_original_format',
    ACTIVE.parent/'research/lpx-s15-2026-11-01/s15_format.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)


class SparseHostContracts(unittest.TestCase):
    def test_old_format_bytes_expansion_and_tails(self):
        rng = random.Random(8042)
        for n in (1, 19, 20, 79, 80, 159, 160, 319, 320, 321, 639, 640, 641, 63999):
            frames = (n+319)//320
            spectra = [sorted(rng.sample(range(64), 10)) for _ in range(frames)]
            params = [(rng.randrange(32), rng.randrange(18, 146), 2*rng.randrange(8)) for _ in range(frames)]
            pulses = [(rng.choice(sparse.POSITIONS), rng.choice((-8, 7))) for _ in range(frames*4)]
            fields = n, spectra, params, pulses, rng.randrange(16385), rng.randrange(11470)
            blob = sparse.pack(*fields)
            self.assertEqual(blob, original.pack(*fields)[0])
            self.assertEqual(sparse.unpack(blob), original.unpack(blob))
            self.assertEqual(sparse.expand(blob), original.expand(blob))

    def test_invalid_and_nonzero_tail_rejected(self):
        fields = 321, [list(range(10))]*2, [(1, 18, 0)]*2, [(0, -8)]*8, 13926, 0
        blob = sparse.pack(*fields)
        for malformed in (blob[:21], blob[:-1], blob+b'\0', blob[:4]+b'\5'+blob[5:],
                          blob[:5]+b'\x8f'+blob[6:]):
            with self.assertRaises((ValueError, EOFError)):
                sparse.unpack(malformed)


if __name__ == '__main__':
    unittest.main()

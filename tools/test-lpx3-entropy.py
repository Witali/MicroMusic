"""LPX3 lossless storage: exact bytes, padding, expansion and corruption checks."""
from pathlib import Path
import random
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from lpx3_entropy import LPX, WRAP, MAX_BYTES, pack, unpack, transform, restore, pack_codes


def fixture(bits=3, samples=401, random_codes=False):
    base = bytearray(36)
    base[:4] = b'LPC2'
    base[4] = 2
    struct.pack_into('<H', base, 6, 7500)
    struct.pack_into('<I', base, 16, samples)
    blocks = (samples+74)//75
    rng = random.Random(23240)
    codes = [rng.randrange(1 << bits) if random_codes else (1 << (bits-1)) for _ in range(samples)]
    return LPX.pack(b'LPX3', 1, bits, 7500, samples, len(base), 75, 0, blocks)+bytes(base)+bytes(range(blocks))+bytes(pack_codes(codes,bits))


class LPX3EntropyTests(unittest.TestCase):
    def test_all_transforms_restore_every_byte_including_unused_tail(self):
        for bits in (2, 3, 4):
            for samples in (1, 7, 401, 512):
                raw = bytearray(fixture(bits, samples, True))
                used = samples*bits % 8
                if used:
                    raw[-1] |= 255 ^ ((1 << used)-1)
                for method in (0, 1, 2):
                    self.assertEqual(restore(transform(raw,method),method), raw)

    def test_compressible_codes_save_real_bytes_with_no_audio_change(self):
        raw = fixture(samples=5000)
        encoded, info = pack(raw)
        self.assertLess(len(encoded), len(raw)//3)
        self.assertEqual(unpack(encoded), raw)
        self.assertEqual(info['stored_bytes'],len(encoded))

    def test_arbitrary_codes_never_expand_chosen_storage(self):
        for bits in (2, 3, 4):
            raw = fixture(bits, 3073, True)
            encoded, info = pack(raw)
            self.assertLessEqual(len(encoded), len(raw))
            self.assertEqual(unpack(encoded), raw)

    def test_corruption_truncation_trailing_bytes_and_oversized_header_reject(self):
        encoded, _ = pack(fixture(samples=5000))
        for damaged in (encoded[:-1], encoded+b'x', encoded[:20]+b'broken'+encoded[26:]):
            with self.assertRaises(ValueError):
                unpack(damaged)
        with self.assertRaises(ValueError):
            unpack(WRAP.pack(b'LPZ1',0,MAX_BYTES+1,64,0)+b'x')
        with self.assertRaises(ValueError):
            pack(fixture()+b'junk')


if __name__ == '__main__':
    unittest.main()

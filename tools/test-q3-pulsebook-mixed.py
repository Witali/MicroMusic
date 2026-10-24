"""Mixed-source encoding, legacy compatibility and independent LFSR timing."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q3_pulsebook as base
import q3_pulsebook_mixed as mixed


class MixedPulsebookTests(unittest.TestCase):
    def test_zero_flags_preserve_both_rounding_profiles_and_noise_transitions(self):
        rng = np.random.default_rng(23144)
        frames = np.full((12,6),0x88,np.uint8)
        frames[:,0] = [64,0,18,2,1,126,0,25,64,8,0,30]
        frames[:,1] = rng.integers(0,64,12,dtype=np.uint8)
        durations = np.full(12,64,np.uint16)
        book = rng.integers(-4,5,(4,16),dtype=np.int8)
        encoded = mixed.encode_book(book,[0,0,0,0])
        for nearest in (False,True):
            for tilt in (0,1):
                actual = mixed.render(frames,durations,encoded,tilt,nearest)
                expected = base.render(frames,durations,book,tilt,nearest)
                for a,b in zip(actual,expected):
                    np.testing.assert_array_equal(a,b)

    def test_lfsr_clocks_even_at_zero_and_one_gain_and_bypasses_unvoiced_mix(self):
        frames = np.array([[64,0,0x88,0x88,0x88,0x88],
                           [64,1,0x88,0x88,0x88,0x88],
                           [64,6,0x88,0x88,0x88,0x88],
                           [0,6,0x88,0x88,0x88,0x88]],np.uint8)
        durations = np.full(4,64,np.uint16)
        book = mixed.encode_book(np.zeros((4,16),np.int8),[1,0,0,0])
        pcm,counts = mixed.render(frames,durations,book,0,False)
        seed,expected = 0xa7,[]
        for t in range(256):
            # The firmware's existing frame boundary precedes nominal time by1.
            index = 0 if t < 63 or t == 255 else (t+1)//64
            gain = (0,1,6,6)[index]
            low = seed & 1
            seed >>= 1
            if low: seed ^= 0xb8
            amplitude = gain if index == 3 else gain >> 1
            expected.append(128+(-amplitude if seed & 1 else amplitude))
        np.testing.assert_array_equal(pcm,expected)
        np.testing.assert_array_equal(counts,np.zeros(4))

    def test_flag_is_mode_specific_and_noise_continues_after_pulse_ends(self):
        book = mixed.encode_book(np.zeros((4,16),np.int8),[1,0,0,0])
        d = np.array([256],np.uint16)
        for mode in range(4):
            f = np.array([[64,mode*16+6,0x88,0x88,0x88,0x88]],np.uint8)
            pcm,_ = mixed.render(f,d,book,0,False)
            self.assertEqual(set(pcm[20:60]),{125,131} if mode == 0 else {128})

    def test_exact_eeprom_roundtrip_bounds_and_uniform_row_flag(self):
        coefficients = (np.arange(64).reshape(4,16)%15-7).astype(np.int8)
        encoded = mixed.encode_book(coefficients,[0,1,0,1])
        decoded,flags = mixed.decode_book(encoded)
        np.testing.assert_array_equal(decoded,coefficients)
        np.testing.assert_array_equal(flags,[0,1,0,1])
        self.assertEqual(len(encoded.tobytes()),64)
        for value in (0,16,32,-1):
            invalid = encoded.copy();invalid[0,0] = value
            with self.assertRaises(ValueError): mixed.decode_book(invalid)
        invalid = encoded.copy();invalid[0,0] |= 16
        with self.assertRaises(ValueError): mixed.decode_book(invalid)

    def test_original_stream_budget_and_stable_coefficient_contract_remain(self):
        f = np.array([[64,3,0x88,0x88,0x88,0x88]],np.uint8)
        d = np.array([256],np.uint16)
        payload = mixed.validate(f,d,mixed.legacy_tables(),256)
        self.assertEqual(payload,base.validate(f,d,base.legacy_tables(),256))
        with self.assertRaisesRegex(ValueError,'budget'):
            mixed.validate(f,d,mixed.legacy_tables(),256,len(payload)-1)
        f[0,2] = 0x80
        with self.assertRaisesRegex(ValueError,'stable'):
            mixed.validate(f,d,mixed.legacy_tables())


if __name__ == '__main__': unittest.main()

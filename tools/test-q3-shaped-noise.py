"""Exact shaped-noise semantics, zero-flag compatibility and packed row modes."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q3_pulsebook as base
from q3_shaped_noise import encode_book,decode_book,pack_book,unpack_book,validate,render


def frames(rows):
    return np.asarray([[period,gain+16*row,0x88,0x88,0x88,0x88]
                       for period,gain,row in rows],np.uint8)


class ShapedNoiseTests(unittest.TestCase):
    def test_all_off_preserves_pcm_and_all_counts_for_both_roundings(self):
        rng = np.random.default_rng(231040)
        f = rng.integers(1,256,(12,6),dtype=np.uint8)
        f[:,0] = [0,1,4,16,17,31,32,33,40,64,100,126]
        f[:,1] &= 63
        f[:,2:] |= 0x11
        d = rng.choice([64,128,192,256],12).astype(np.uint16)
        book = rng.integers(-7,8,(4,16),dtype=np.int8)
        for nearest in (False,True):
            for tilt in (0,1,2):
                expected = base.render(f,d,book,tilt,nearest)
                actual = render(f,d,encode_book(book,np.zeros(4,int)),tilt,nearest)
                np.testing.assert_array_equal(actual[0],expected[0])
                np.testing.assert_array_equal(actual[1],expected[1])

    def test_low_high_white_known_lfsr_vector_and_signed_shift(self):
        expected = {1:[-2,-3,0,0,-3,-3,-3,-3,-3,0],
                    2:[-2,0,3,-3,0,0,0,0,0,3],
                    3:[-3,-3,3,-3,-3,-3,-3,-3,-3,3]}
        for mode in (1,2,3):
            book = encode_book(np.zeros((4,16),int),np.full(4,mode,int))
            pcm,counts = render(frames([(64,6,0)]),np.array([256],np.uint16),book,0,False)
            np.testing.assert_array_equal(pcm[:10].astype(int)-128,expected[mode])
            np.testing.assert_array_equal(counts,0)

    def test_flagged_gain_zero_and_one_still_advance_lfsr(self):
        book = encode_book(np.zeros((4,16),int),np.array([3,0,0,0]))
        expected = [-7,-7,-7,-7,-7,7,7,7,7,-7,7,-7]
        for gain in (0,1):
            f = frames([(64,gain,0),(0,7,1)])
            pcm,_ = render(f,np.array([64,64],np.uint16),book,0,False)
            np.testing.assert_array_equal(pcm[:63],128)
            np.testing.assert_array_equal(pcm[63:75].astype(int)-128,expected)

    def test_previous_noise_is_frozen_in_unvoiced_and_off_voiced_frames(self):
        book = encode_book(np.zeros((4,16),int),np.array([1,0,2,0]))
        for middle_period in (0,64):
            f = frames([(64,6,0),(middle_period,7,1),(64,6,2)])
            pcm,_ = render(f,np.array([64,64,64],np.uint16),book,0,False)
            self.assertEqual(int(pcm[127])-128,0)
        # A flagged gain0 frame updates the stored noise to0 after its first
        # colored sample; the preceding signed memory is not silently cleared.
        f = frames([(64,6,0),(64,0,0)])
        pcm,_ = render(f,np.array([64,64],np.uint16),book,0,False)
        self.assertEqual(int(pcm[63])-128,-2)
        np.testing.assert_array_equal(pcm[64:127],128)

    def test_old_pulse_is_added_to_noise_and_noise_flags_ignore_unvoiced(self):
        coefficients = np.full((4,16),2,int)
        modes = np.full(4,3,int)
        f,d = frames([(64,6,0)]),np.array([256],np.uint16)
        pcm,_ = render(f,d,encode_book(coefficients,modes),0,False)
        self.assertEqual(int(pcm[0])-128,12-3)
        f = frames([(0,6,0)])
        np.testing.assert_array_equal(render(f,d,encode_book(coefficients,modes),1,True)[0],
            base.render(f,d,coefficients.astype(np.int8),1,True)[0])

    def test_encoded_bytes_roundtrip_and_uniform_modes(self):
        coefficients = (np.arange(64).reshape(4,16)%15-7).astype(np.int8)
        modes = np.arange(4,dtype=np.uint8)
        book = encode_book(coefficients,modes)
        raw = pack_book(book)
        self.assertEqual(len(raw),64)
        self.assertEqual(raw[0],1)
        self.assertEqual(raw[16],0x12)
        c,m = decode_book(unpack_book(raw))
        np.testing.assert_array_equal(c,coefficients)
        np.testing.assert_array_equal(m,modes)
        bad = book.copy();bad[0,1] |= 16
        with self.assertRaises(ValueError): decode_book(bad)
        bad = book.copy();bad[0,0] |= 64
        with self.assertRaises(ValueError): decode_book(bad)
        bad = book.copy();bad[0,0] &= 0xf0
        with self.assertRaises(ValueError): decode_book(bad)

    def test_raw_values_cannot_wrap_and_real_stream_cap_is_enforced(self):
        book = encode_book(np.zeros((4,16),int),np.zeros(4,int))
        f,d = frames([(40,3,0)]),np.array([256],np.uint16)
        payload = validate(f,d,book,256)
        with self.assertRaises(ValueError): validate(f,d,book,256,len(payload)-1)
        for bad in (f.astype(int)+256,-f.astype(int),f.astype(float)):
            with self.assertRaises(ValueError): validate(bad,d,book)
        with self.assertRaises(ValueError): encode_book(np.full((4,16),249),np.zeros(4,int))
        with self.assertRaises(ValueError): encode_book(np.zeros((4,16),int),np.full(4,4))


if __name__ == '__main__':
    unittest.main()

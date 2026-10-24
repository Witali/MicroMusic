"""Sparse parity escapes, frame reuse and high gain/mode/pitch fields."""
import itertools
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q4_sparse_stream as codec


class SparseQ4Tests(unittest.TestCase):
    def test_half_uses_two_even_bytes_or_three_with_odd_residuals(self):
        for values in itertools.product((-15,-14,-1,0,1,14,15),repeat=4):
            k=np.array(values,np.int8);payload=codec.pack_half(k);got,used=codec.unpack_half(payload)
            self.assertEqual(len(payload),3 if np.any(k%2) else 2)
            self.assertEqual(used,len(payload));np.testing.assert_array_equal(got,k)
        for bad in (b'',b'\x00\x88',b'\x10\x88',b'\x20\x80\x88'):
            with self.assertRaises(ValueError):codec.unpack_half(bad)

    def test_every_gain_mode_duration_and_pitch_boundary_survives_reuse(self):
        fields=[(p,g,d,m,h) for p,g,d,m,h in itertools.product((0,1,63,64,126),range(31),
            (64,128,192,256),range(8),(0,1)) if p or not h]
        p,g,d,m,h=(np.asarray(a,np.int16) for a in zip(*fields))
        k=np.zeros((len(p),8),np.int8)
        k[::3,0]=-15;k[::5,7]=15
        payload=codec.pack(p,g,d,k,m,h);decoded=codec.unpack(payload)
        for before,after in zip((p,g,d,k,m,h),decoded):np.testing.assert_array_equal(before,after)

    def test_half_updates_and_repeats_have_the_documented_cost(self):
        p=np.full(5,40,np.int16);g=np.full(5,10,np.int16);d=np.full(5,64,np.int16)
        m=np.zeros(5,np.int16);h=np.zeros(5,np.int16);k=np.zeros((5,8),np.int8)
        k[1:,0]=-15;k[2:,5]=3;k[4:,1]=2
        # Full even=6, low odd=5, high odd=5, repeat=2, low odd=5.
        self.assertEqual(len(codec.pack(p,g,d,k,m,h)),23)

    def test_rejects_missing_initial_coefficients_unknown_headers_and_overflow(self):
        for bad in (b'',b'\xff',b'\xd0\x01\x00',b'\x40\x30',b'\xc0\x7f\x00'):
            with self.assertRaises(ValueError):codec.unpack(bad)
        for value in (-16,16,np.iinfo(np.int64).min):
            with self.assertRaises(ValueError):codec.pack_half(np.array([value,0,0,0],np.int64))


if __name__=='__main__':unittest.main()

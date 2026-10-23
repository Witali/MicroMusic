"""32-tap byte oracle: compatibility, EEPROM packing and exact timing."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q3_pulsebook as old
from q3_pulsebook32 import legacy_tables,pack_book,unpack_book,render,validate


class Pulsebook32Tests(unittest.TestCase):
    def test_zero_padded_arbitrary_old_book_is_byte_exact(self):
        rng = np.random.default_rng(20261023)
        for nearest in (False,True):
            for tilt in (0,1,2):
                f = rng.integers(1,256,(12,6),dtype=np.uint8)
                f[:,0] = [0,1,4,16,17,31,32,33,40,64,100,126]
                f[:,1] &= 63
                f[:,2:] |= 0x11
                d = rng.choice([64,128,192,256],12).astype(np.uint16)
                book16 = rng.integers(-7,8,(4,16),dtype=np.int8)
                book32 = np.pad(book16,((0,0),(0,16)))
                a,b = old.render(f,d,book16,tilt,nearest),render(f,d,book32,tilt,nearest)
                np.testing.assert_array_equal(a[0],b[0])
                np.testing.assert_array_equal(a[1],b[1])
        np.testing.assert_array_equal(legacy_tables()[:,:16],old.legacy_tables())
        self.assertFalse(np.any(legacy_tables()[:,16:]))

    def test_offset_nibble_order_and_independent_roundtrip(self):
        book = (np.arange(128).reshape(4,32)%15-7).astype(np.int8)
        packed = pack_book(book)
        self.assertEqual(len(packed),64)
        self.assertEqual(packed[0],0x21)  # −7 then−6 => low1/high2
        expected = np.array([((packed[i//2] >> (4*(i%2))) & 15)-8 for i in range(128)])
        np.testing.assert_array_equal(expected.reshape(4,32),book)
        np.testing.assert_array_equal(unpack_book(packed),book)

    def test_all_rows_new_lags_phase_and_final_frame_reset(self):
        book = (np.arange(128).reshape(4,32)%15-7).astype(np.int8)
        for mode in range(4):
            f = np.array([[64,16*mode+1,0x88,0x88,0x88,0x88]],np.uint8)
            pcm,counts = render(f,np.array([256],np.uint16),book,0,False)
            x = pcm.astype(int)-128
            np.testing.assert_array_equal(x[:31],book[mode,1:32])
            self.assertEqual(x[31],0)
            np.testing.assert_array_equal(x[63:95],book[mode])
            self.assertEqual(x[95],0)
            self.assertEqual(x[-1],book[mode,1])
            np.testing.assert_array_equal(counts,0)

    def test_noise_ignores_table_and_nearest_changes_only_arithmetic(self):
        f = np.array([[0,7,0x89,0x98,0x78,0x99]]*2,np.uint8)
        d = np.array([64,128],np.uint16)
        for nearest in (False,True):
            a = render(f,d,np.full((4,32),-7,np.int8),1,nearest)
            b = old.render(f,d,old.legacy_tables(),1,nearest)
            np.testing.assert_array_equal(a[0],b[0])
            np.testing.assert_array_equal(a[1],b[1])

    def test_validate_before_narrowing_and_reject_reserved_nibbles(self):
        f = np.array([[40,3,0x88,0x88,0x88,0x88]],int)
        d = np.array([256],int)
        book = legacy_tables()
        payload = validate(f,d,book,256)
        self.assertGreater(len(payload),0)
        with self.assertRaises(ValueError): validate(f,d,book,256,len(payload)-1)
        for frames in (f.astype(float),f+256,-f):
            with self.assertRaises(ValueError): validate(frames,d,book)
        for bad in (np.full((4,32),249),np.full((4,32),-8),book.astype(float),np.zeros((4,16),int)):
            with self.assertRaises(ValueError): pack_book(bad)
        for raw in (b'\x88'*63,b'\x80'*64,b'\x08'*64):
            with self.assertRaises(ValueError): unpack_book(raw)


if __name__ == '__main__':
    unittest.main()

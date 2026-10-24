"""Exact legacy compatibility, source-table timing and arithmetic guards."""
import json
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_q3 import render as floor
from hq4_q3_rounded import render as rounded
from q3_pulsebook import legacy_tables,render,multiply,validate


class Q3PulsebookTests(unittest.TestCase):
    def test_legacy_book_exact_floor_and_nearest_pcm_and_all_guard_counts(self):
        model = json.loads((ROOT/'ATtiny13A/Sound/research/q3-rounded-eeprom/qualified/model.json').read_text())
        f,d = np.asarray(model['frames'],np.uint8),np.asarray(model['durations'],np.uint16)
        for nearest,original in ((False,floor),(True,rounded)):
            expected = original(f,d,1)
            actual = render(f,d,legacy_tables(),1,nearest)
            np.testing.assert_array_equal(actual[0],expected[0])
            np.testing.assert_array_equal(actual[1],expected[1])

    def test_noise_path_does_not_read_or_mix_the_pulsebook(self):
        f = np.array([[0,5,0x89,0x98,0x78,0x99]]*2,np.uint8)
        d = np.array([64,128],np.uint16)
        book = np.full((4,16),7,np.int8)
        for nearest,original in ((False,floor),(True,rounded)):
            np.testing.assert_array_equal(render(f,d,book,0,nearest)[0],original(f,d,0)[0])

    def test_all_four_mode_rows_and_sixteen_sample_lags_then_zero(self):
        book = np.arange(64).reshape(4,16)%15-7
        for mode in range(4):
            f = np.array([[64,mode*16+1,0x88,0x88,0x88,0x88]],np.uint8)
            pcm,counts = render(f,np.array([256],np.uint16),book.astype(np.int8),0,False)
            signed = pcm.astype(int)-128
            np.testing.assert_array_equal(signed[63:79],book[mode])
            self.assertEqual(int(signed[79]),0)
            np.testing.assert_array_equal(signed[127:143],book[mode])
            np.testing.assert_array_equal(counts,np.zeros(4))

    def test_rounding_ties_and_real_output_tilt_overflow_are_visible(self):
        self.assertEqual(multiply(3,4,False),1)
        self.assertEqual(multiply(3,4,True),2)
        self.assertEqual(multiply(-3,4,False),-2)
        self.assertEqual(multiply(-3,4,True),-1)
        f = np.array([[64,15,0x88,0x88,0x88,0x88]],np.uint8)
        _,counts = render(f,np.array([256],np.uint16),np.full((4,16),7,np.int8),1,False)
        self.assertGreater(int(counts[3]),0)

    def test_signed_eeprom_bounds_stable_coefficients_and_real_stream_cap(self):
        f = np.array([[40,3,0x88,0x88,0x88,0x88]],np.uint8)
        d = np.array([256],np.uint16)
        book = legacy_tables()
        payload = validate(f,d,book,256)
        self.assertEqual(len(book.tobytes()),64)
        self.assertEqual(book.tobytes()[3],255)
        with self.assertRaisesRegex(ValueError,'budget'):
            validate(f,d,book,256,len(payload)-1)
        bad = book.copy();bad[0,0] = -8
        with self.assertRaisesRegex(ValueError,'signed'):
            validate(f,d,bad)
        f[0,2] = 0x80
        with self.assertRaisesRegex(ValueError,'stable'):
            validate(f,d,book)


if __name__ == '__main__':
    unittest.main()

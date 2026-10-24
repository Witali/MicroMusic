"""Coefficient-map compatibility, EEPROM packing and scalar Q7 boundaries."""
import json
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q3_pulsebook as base
import q3_kmap as codec


class KmapTests(unittest.TestCase):
    def test_all_signed_samples_and_uniform_coefficients_match_old_arithmetic(self):
        for nearest in (False,True):
            for value in range(-128,128):
                for coefficient in range(-7,8):
                    self.assertEqual(codec.multiply(value,coefficient*16,nearest),
                                     base.multiply(value,coefficient,nearest))

    def test_full_q7_range_matches_independent_integer_formula(self):
        for nearest in (False,True):
            for value in range(-128,128):
                for coefficient in range(-127,128):
                    operand = ((-value+128)&255)-128 if coefficient < 0 else value
                    product = (operand*abs(coefficient)+(64 if nearest else 0))//128
                    expected = ((product+128)&255)-128
                    self.assertEqual(codec.multiply(value,coefficient,nearest),expected)

    def test_original_waveforms_and_uniform_maps_preserve_full_frozen_pcm(self):
        model = json.loads((ROOT/'ATtiny13A/Sound/research/q3-rounded-eeprom/qualified/model.json').read_text())
        f,d = np.asarray(model['frames'],np.uint8),np.asarray(model['durations'],np.uint16)
        for nearest in (False,True):
            for tilt in (0,1):
                for a,b in zip(codec.render(f,d,codec.legacy_tables(),tilt,nearest),
                               base.render(f,d,base.legacy_tables(),tilt,nearest)):
                    np.testing.assert_array_equal(a,b)

    def test_eeprom_roundtrip_uses32_wave_bytes_and32_map_bytes(self):
        table = codec.legacy_tables()
        table[:4] = (np.arange(64).reshape(4,16)%15-7).astype(np.int8)
        table[4:] = np.linspace(-127,127,32).reshape(2,16).astype(np.int8)
        data = codec.pack_eeprom(table)
        self.assertEqual(len(data),64)
        self.assertEqual(data[0],1|(2<<4))
        self.assertEqual(data[32:],table[4:].tobytes())
        np.testing.assert_array_equal(codec.unpack_eeprom(data),table)
        for invalid in (data[:-1],data+b'\0',b'\0'+data[1:],data[:32]+b'\x80'+data[33:]):
            with self.assertRaises(ValueError): codec.unpack_eeprom(invalid)

    def test_only_first_two_indices_allow_nibble_zero_with_stable_maps(self):
        f = np.array([[40,3,0,0x88,0x88,0x88]],np.uint8)
        d = np.array([256],np.uint16)
        table = codec.legacy_tables()
        payload = codec.validate(f,d,table,256)
        with self.assertRaisesRegex(ValueError,'budget'):
            codec.validate(f,d,table,256,len(payload)-1)
        table[4,0] = -128
        with self.assertRaises(ValueError): codec.validate(f,d,table)
        table[4,0] = -127
        f[0,3] = 0x80
        with self.assertRaisesRegex(ValueError,'fixed-Q3'): codec.validate(f,d,table)


if __name__ == '__main__': unittest.main()

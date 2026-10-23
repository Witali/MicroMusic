#!/usr/bin/env python3
"""Check arbitrary-reference initialization, exact packing and rate anchors."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from fixed_period import validate, decode_fixed
from new_tiny_encoder import (pad_reference, analyze_reference, initialize_model,
                              simplify_regions, attenuate, lossless_roundtrip)
from tiny_period import validate_tiny


class NewTinyEncoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t = np.arange(4096)/7500
        cls.original = .3*np.sin(2*np.pi*(130*t+10*t*t))+.035*np.sin(2*np.pi*1100*t)
        cls.reference, cls.base, cls.analysis = analyze_reference(cls.original, starts=1)

    def test_padding_preserves_all_samples_and_rejects_excess_duration(self):
        original = self.original[:4003]
        padded = pad_reference(original)
        np.testing.assert_array_equal(padded[:len(original)], original)
        self.assertEqual(len(padded)%64, 0)
        self.assertTrue(np.all(padded[len(original):]==0))
        self.assertLess(len(padded)-len(original),64)
        with self.assertRaisesRegex(ValueError, '1023'):
            pad_reference(np.zeros(65473))
        with self.assertRaises(ValueError):
            pad_reference(np.zeros((4096,2)))

    def test_all_dictionary_sizes_use_existing_exact_decoder_features(self):
        for words in (1,2,4,8):
            with self.subTest(words=words):
                model = initialize_model(self.reference,self.base,self.analysis,words,starts=1)
                validate_tiny(model)
                self.assertEqual(model['samples'],len(self.original))
                self.assertTrue(all(header&128 for _,header,_ in model['frames']))
                self.assertTrue(all((header&15)<words for _,header,_ in model['frames']))
                self.assertTrue(all((header>>4)&7!=6 for _,header,_ in model['frames']))
                self.assertTrue(all(0<=residual<=15 for _,_,residual in model['frames']))
                self.assertTrue(all(not any(word) for word in model['codebook'][words:]))
                packed = lossless_roundtrip(model)
                self.assertEqual(len(packed['eeprom']),64)
                self.assertLessEqual(packed['constants']['EEPROM_USED_BYTES'],64)

    def test_region_phase_sum_and_no_mutation(self):
        model = initialize_model(self.reference,self.base,self.analysis,4,starts=1)
        original = deepcopy(model)
        for width in (1,3,16,31):
            candidate = simplify_regions(model,width,preserve_phase=True)
            self.assertEqual(sum(frame[0] for frame in candidate['frames']),
                             sum(frame[0] for frame in model['frames']))
            validate_tiny(candidate)
            self.assertEqual(candidate['samples'],model['samples'])
        self.assertEqual(original,model)

    def test_rate_anchors_remain_valid_at_extreme_pitch(self):
        model = initialize_model(self.reference,self.base,self.analysis,4,starts=1)
        for index,frame in enumerate(model['frames']):
            frame[0] = 255 if index%2 else 0
        for preserve in (False,True):
            candidate = simplify_regions(model,6,preserve_phase=preserve)
            validate(candidate)
            self.assertEqual(candidate['samples'],model['samples'])
            lossless_roundtrip(candidate)

    def test_attenuation_keeps_timing_and_feature_contract(self):
        model = initialize_model(self.reference,self.base,self.analysis,4,starts=1)
        candidate = attenuate(model)
        self.assertEqual([frame[0] for frame in candidate['frames']],
                         [frame[0] for frame in model['frames']])
        self.assertEqual(candidate['codebook'],model['codebook'])
        self.assertTrue(all(((after[1]>>4)&7)<=((before[1]>>4)&7) and after[2]<=before[2]
                            for before,after in zip(model['frames'],candidate['frames'])))
        validate_tiny(candidate)

    def test_deterministic_initialization(self):
        first = initialize_model(self.reference,self.base,self.analysis,4,starts=1,seed=55)
        second = initialize_model(self.reference,self.base,self.analysis,4,starts=1,seed=55)
        self.assertEqual(first,second)
        np.testing.assert_array_equal(decode_fixed(first),decode_fixed(second))


if __name__=='__main__':
    unittest.main()

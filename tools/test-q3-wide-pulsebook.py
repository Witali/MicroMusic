"""Wide-state arithmetic diagnostic controls and complete finite grid."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from q3_wide_pulsebook import render
from q3_pulsebook import legacy_tables,render as byte_render
from q3_pulsebook_pole import render as pole_render
spec = importlib.util.spec_from_file_location('q3_wide_probe',ROOT/'tools/probe-q3-wide-pulsebook.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class WidePulsebookTests(unittest.TestCase):
    def test_zero_fraction_controls_match_clean_floor_and_nearest_byte_models(self):
        cases = [('hq4-q3/public-vinni/model.json',False),('q3-rounded-eeprom/qualified/model.json',True)]
        for path,nearest in cases:
            model = json.loads((ROOT/'ATtiny13A/Sound/research'/path).read_text())
            f,d = np.asarray(model['frames'],np.uint8),np.asarray(model['durations'],np.uint16)
            expected,old_counts = byte_render(f,d,legacy_tables(),1,nearest)
            actual,counts,_ = render(f,d,legacy_tables(),0,nearest,False)
            self.assertTrue(np.all(old_counts == 0))
            self.assertTrue(np.all(counts == 0))
            np.testing.assert_array_equal(actual,expected)

    def test_special_pole_mapping_zero_fraction_matches_separate_pole_oracle(self):
        f = np.array([[30,2,0x80,0x88,0x88,0x88]],np.uint8)
        d = np.array([256],np.uint16)
        for nearest in (False,True):
            expected,old_counts = pole_render(f,d,legacy_tables(),1,nearest)
            actual,counts,_ = render(f,d,legacy_tables(),0,nearest,True)
            self.assertTrue(np.all(old_counts == 0))
            self.assertTrue(np.all(counts == 0))
            np.testing.assert_array_equal(actual,expected)

    def test_fractional_t1_and_pwm_rounding_match_independent_scalar_recurrence(self):
        f = np.array([[16,1,0x88,0x88,0x88,0x88]],np.uint8)
        d = np.array([64],np.uint16)
        book = np.zeros((4,16),np.int8);book[0,0] = 1
        actual,counts,_ = render(f,d,book,2,False,False)
        previous,expected = 0,[]
        for sample in range(64):
            excitation = 4 if sample in (15,31,47) else 0
            previous = excitation+previous-(previous >> 1)
            expected.append(((previous+2) >> 2)+128)
        np.testing.assert_array_equal(actual,np.asarray(expected,np.uint8))
        self.assertTrue(np.all(counts == 0))

    def test_signed16_and_pwm_guards_expose_unsafe_trial_without_saturation(self):
        f = np.array([[64,15,0xff,0xff,0xff,0xff]],np.uint8)
        d = np.array([256],np.uint16)
        _,counts,maximum = render(f,d,np.full((4,16),7,np.int8),8,True,False)
        self.assertGreater(int(counts[0]),0)
        self.assertGreater(int(counts[3]),0)
        self.assertGreater(int(maximum[0]),32767)

    def test_full_grid_gain_rounding_clamp_mode_preservation_and_no_mutation(self):
        configs = probe.configurations()
        self.assertEqual(len(configs),12)
        self.assertEqual(len(set(configs)),12)
        f = np.array([[30,0x2f,0x88,0x88,0x88,0x88],[30,0x12,0x88,0x88,0x88,0x88]],np.uint8)
        original = f.copy()
        enlarged = probe.scaled_frames(f,1.35)
        quiet = probe.scaled_frames(f,.65)
        np.testing.assert_array_equal(enlarged[:,1] & 48,f[:,1] & 48)
        self.assertEqual(int(enlarged[0,1] & 15),15)
        self.assertEqual(int(quiet[1,1] & 15),1)
        np.testing.assert_array_equal(f,original)


if __name__ == '__main__':
    unittest.main()

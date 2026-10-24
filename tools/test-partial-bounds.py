#!/usr/bin/env python3
"""Strict bounds never turn missing original peaks into zero-error matches."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from partial_bounds import check_partial_bounds


def fixture():
    reference = dict(times=np.array([0.,.1,.2]),track_id=np.array([[0,1]]*3),
                     amplitude=np.array([[1.,.5]]*3),frequency_hz=np.array([[500.,1000.]]*3))
    candidate = deepcopy(reference)
    matches = []
    for frame in range(3):
        for column in range(2):
            matches.append(dict(frame=frame,reference_id=column,candidate_id=column,
                level_error_db=0.,frequency_error_cents=0.,frequency_error_hz=0.))
    return dict(reference_tracks=reference,candidate_tracks=candidate,matches=matches,metrics={})


class PartialBoundsTests(unittest.TestCase):
    def test_exact_bound_passes_and_every_peak_is_checked(self):
        detail = fixture()
        detail['matches'][0]['level_error_db'] = 5.
        result = check_partial_bounds(detail)
        self.assertTrue(result['passed'])
        self.assertEqual(result['selected_reference_peaks'],6)
        self.assertEqual(result['matched_reference_peaks'],6)
        self.assertEqual(result['max_matched_level_error_db'],5.)
        detail['matches'][0]['level_error_db'] = 5.01
        result = check_partial_bounds(detail)
        self.assertFalse(result['passed'])
        self.assertEqual(result['matched_level_violations'],1)
        self.assertAlmostEqual(result['violating_reference_power_fraction'],1/3.75)
        self.assertTrue(result['worst_intervals'])

    def test_missing_peaks_are_violations_including_all_missing(self):
        detail = fixture()
        detail['matches'] = detail['matches'][1:]
        result = check_partial_bounds(detail)
        self.assertFalse(result['passed'])
        self.assertEqual(result['missing_reference_peaks'],1)
        self.assertEqual(result['violating_reference_peaks'],1)
        self.assertEqual(result['matched_level_violations'],0)
        detail['matches'] = []
        result = check_partial_bounds(detail)
        self.assertFalse(result['passed'])
        self.assertEqual(result['missing_reference_peaks'],6)
        self.assertIsNone(result['max_matched_level_error_db'])
        self.assertAlmostEqual(result['violating_reference_power_fraction'],1.)

    def test_optional_frequency_caps_and_no_double_count(self):
        detail = fixture()
        detail['matches'][0].update(level_error_db=7.,frequency_error_cents=30.,frequency_error_hz=9.)
        result = check_partial_bounds(detail,max_frequency_error_cents=20.,max_frequency_error_hz=5.)
        self.assertFalse(result['passed'])
        self.assertEqual(result['matched_level_violations'],1)
        self.assertEqual(result['matched_frequency_violations'],1)
        self.assertEqual(result['violating_reference_peaks'],1)

    def test_duplicate_assignments_and_invalid_bounds_rejected(self):
        detail = fixture()
        detail['matches'].append(deepcopy(detail['matches'][0]))
        with self.assertRaises(ValueError):
            check_partial_bounds(detail)
        with self.assertRaises(ValueError):
            check_partial_bounds(fixture(),max_level_error_db=-1.)


if __name__ == '__main__':
    unittest.main()

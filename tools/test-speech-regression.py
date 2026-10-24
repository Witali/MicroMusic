#!/usr/bin/env python3
"""Recording-specific gates cannot hide harm behind another clip's gains."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from speech_regression import compare_recording_metrics,guard_recordings


def metrics(**changes):
    value = dict(stoi=.9,estoi=.8,fine_log_error=.5,envelope_error=.6,
                 unsupported_energy=.1,missing_energy=.2)
    value.update(changes)
    return value


class SpeechRegressionTests(unittest.TestCase):
    def test_identical_and_tiny_numeric_differences_pass(self):
        self.assertTrue(compare_recording_metrics(metrics(),metrics())['candidate_passed'])
        candidate = metrics(stoi=.9-5e-10,estoi=.8-5e-10,fine_log_error=.5+5e-10,
                            envelope_error=.6+5e-10,unsupported_energy=.1+5e-10,missing_energy=.2+5e-10)
        self.assertTrue(compare_recording_metrics(metrics(),candidate)['candidate_passed'])
        self.assertFalse(compare_recording_metrics(metrics(),metrics(stoi=.9-2e-9))['candidate_passed'])

    def test_each_metric_is_independently_protected(self):
        for metric in metrics():
            with self.subTest(metric=metric):
                candidate = metrics(stoi=.95,estoi=.85,fine_log_error=.4,envelope_error=.5,
                                    unsupported_energy=.05,missing_energy=.1)
                candidate[metric] = metrics()[metric]+(-.01 if metric in ('stoi','estoi') else .01)
                result = compare_recording_metrics(metrics(),candidate)
                self.assertFalse(result['candidate_passed'])
                self.assertEqual(result['violations'][0]['metric'],metric)

    def test_gain_on_another_recording_cannot_hide_regression(self):
        baseline = {'first':metrics(),'second':metrics()}
        candidate = {'first':metrics(stoi=.899),'second':metrics(stoi=.99,estoi=.95,fine_log_error=.1)}
        result = guard_recordings(baseline,candidate,['first','second'])
        self.assertFalse(result['candidate_passed'])
        self.assertFalse(result['selection_passed'])
        self.assertFalse(result['recordings']['first']['candidate_passed'])
        self.assertTrue(result['recordings']['second']['candidate_passed'])

    def test_missing_nonfinite_and_nonnumeric_metrics_fail(self):
        for value in (float('nan'),float('inf'),-float('inf'),True,'0.9',None):
            with self.subTest(value=value):
                self.assertFalse(compare_recording_metrics(metrics(),metrics(stoi=value))['candidate_passed'])
        candidate = metrics()
        del candidate['estoi']
        self.assertFalse(compare_recording_metrics(metrics(),candidate)['candidate_passed'])
        self.assertFalse(guard_recordings({'first':metrics()},{},['first'])['candidate_passed'])
        self.assertFalse(compare_recording_metrics(metrics(stoi=float('nan')),metrics())['baseline_valid'])

    def test_fallback_selection_never_reports_rejected_candidate_as_passed(self):
        baseline = {'first':metrics(),'second':metrics()}
        candidate = {'first':metrics(stoi=.85),'second':metrics(stoi=.95)}
        saved = deepcopy((baseline,candidate))
        result = guard_recordings(baseline,candidate,['first','second'],fallback_to_baseline=True)
        self.assertFalse(result['candidate_passed'])
        self.assertTrue(result['selection_passed'])
        self.assertTrue(result['baseline_fallback_used'])
        self.assertEqual(result['recordings']['first']['selected_source'],'baseline')
        self.assertFalse(result['recordings']['first']['candidate_passed'])
        self.assertEqual(result['recordings']['second']['selected_source'],'candidate')
        self.assertEqual((baseline,candidate),saved)
        invalid = guard_recordings({'first':metrics(stoi=float('nan'))},{'first':metrics()},
                                   ['first'],fallback_to_baseline=True)
        self.assertFalse(invalid['selection_passed'])
        self.assertIsNone(invalid['recordings']['first']['selected_source'])

    def test_unprotected_recordings_are_explicitly_unchecked(self):
        result = guard_recordings({'protected':metrics(),'other':metrics()},
                                  {'protected':metrics(),'other':metrics(stoi=.1)},['protected'])
        self.assertTrue(result['candidate_passed'])
        self.assertEqual(result['unchecked_ids'],['other'])
        self.assertNotIn('other',result['recordings'])
        with self.assertRaises(ValueError):
            guard_recordings({}, {}, [])


if __name__ == '__main__':
    unittest.main()

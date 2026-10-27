"""Unavailable short-utterance STOI is distinct from a valid low score."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import warnings
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from standard_metrics import error_metrics


class ShortStoiTests(unittest.TestCase):
    def setUp(self):
        self.rng=np.random.default_rng(20261027)

    def test_tiny_nonzero_tails_skip_pystoi_without_changing_pcm_metrics(self):
        for n in (1,19,80,161,205,256,319,321):
            x=np.full(n,123,np.int16)
            with self.subTest(samples=n),patch('pystoi.stoi',side_effect=AssertionError('Too short for STOI')):
                result=error_metrics(x,x,speech=True)
            self.assertIsNone(result['stoi'])
            self.assertEqual(result['samples'],n)
            self.assertEqual(result['ser_status'],'perfect')

    def test_resampled_frame_lower_bound_preserves_first_possible_score(self):
        # Minimum 4097 samples at pystoi's internal 10 kHz. Rational
        # resampling uses ceiling, so 8/7.5 kHz reach it at3277/3073.
        for rate,first in ((10000,4097),(8000,3277),(7500,3073)):
            for n in (first-1,first):
                x=np.full(n,123,np.int16)
                with self.subTest(rate=rate,samples=n),patch('pystoi.stoi',return_value=.75) as measured:
                    result=error_metrics(x,x,speech=True,rate=rate)
                self.assertEqual(result['stoi'],.75 if n==first else None)
                self.assertEqual(measured.call_count,int(n==first))

    def test_first_possible_real_scores_match_pystoi(self):
        from pystoi import stoi
        for rate,n in ((10000,4097),(8000,3277),(7500,3073)):
            x=self.rng.integers(-4000,4000,n,dtype=np.int16)
            with self.subTest(rate=rate),warnings.catch_warnings():
                warnings.simplefilter('error')
                expected=float(stoi(x.astype(float)/32768,x.astype(float)/32768,rate))
                self.assertEqual(error_metrics(x,x,speech=True,rate=rate)['stoi'],expected)

    def test_short_active_recording_has_no_stoi_but_retains_pcm_metrics(self):
        x=self.rng.integers(-4000,4000,2185,dtype=np.int16)
        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter('always')
            result=error_metrics(x,x,speech=True)
        self.assertIsNone(result['stoi'])
        self.assertEqual(result['samples'],len(x))
        self.assertEqual(result['ser_status'],'perfect')
        self.assertEqual(result['error_energy'],0)
        self.assertEqual(seen,[])

    def test_long_recording_with_insufficient_active_frames_is_unavailable(self):
        x=np.zeros(16000,np.int16)
        x[7000:7800]=self.rng.integers(-4000,4000,800,dtype=np.int16)
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            self.assertIsNone(error_metrics(x,x,speech=True)['stoi'])

    def test_long_recording_preserves_exact_pystoi_result(self):
        from pystoi import stoi
        x=self.rng.integers(-8000,8000,16000,dtype=np.int16)
        y=(x.astype(np.int32)//2+self.rng.integers(-500,500,len(x))).astype(np.int16)
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            expected=float(stoi(x.astype(float)/32768,y.astype(float)/32768,8000))
            actual=error_metrics(x,y,speech=True)['stoi']
        self.assertEqual(actual,expected)

    def test_valid_low_scores_are_not_treated_as_missing(self):
        x=np.resize(np.asarray([100,-200,300,-400],np.int16),4000)
        for score in (1e-5,0.,-.2):
            with self.subTest(score=score),patch('pystoi.stoi',return_value=score):
                self.assertEqual(error_metrics(x,x,speech=True)['stoi'],score)

    def test_unrelated_warning_remains_visible(self):
        x=np.resize(np.asarray([100,-200,300,-400],np.int16),4000)
        def measured(*args):
            warnings.warn('Independent metric warning',RuntimeWarning)
            return .75
        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter('always')
            with patch('pystoi.stoi',side_effect=measured):
                self.assertEqual(error_metrics(x,x,speech=True)['stoi'],.75)
        self.assertEqual([str(w.message) for w in seen],['Independent metric warning'])

    def test_errors_and_promoted_unrelated_warnings_propagate(self):
        x=np.resize(np.asarray([100,-200,300,-400],np.int16),4000)
        with patch('pystoi.stoi',side_effect=ValueError('Invalid metric input')):
            with self.assertRaisesRegex(ValueError,'Invalid metric input'):
                error_metrics(x,x,speech=True)
        def measured(*args):
            warnings.warn('Invalid numeric operation',RuntimeWarning)
        with warnings.catch_warnings():
            warnings.simplefilter('error',RuntimeWarning)
            with patch('pystoi.stoi',side_effect=measured):
                with self.assertRaisesRegex(RuntimeWarning,'Invalid numeric operation'):
                    error_metrics(x,x,speech=True)

    def test_matching_exception_from_other_source_is_not_suppressed(self):
        from pystoi import stoi
        x=self.rng.integers(-4000,4000,16000,dtype=np.int16)
        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter('always')
            stoi(x[:2185].astype(float)/32768,x[:2185].astype(float)/32768,8000)
        self.assertEqual(len(seen),1)
        with patch('pystoi.stoi',side_effect=RuntimeWarning(str(seen[0].message))):
            with self.assertRaises(RuntimeWarning):
                error_metrics(x,x,speech=True)

    def test_zero_reference_does_not_call_pystoi(self):
        with patch('pystoi.stoi',side_effect=AssertionError('Unexpected metric call')):
            self.assertIsNone(error_metrics([0,0],[1,-1],speech=True)['stoi'])


if __name__=='__main__':unittest.main()

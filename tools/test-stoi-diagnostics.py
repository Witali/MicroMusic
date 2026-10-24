"""Band scores reproduce installed STOI, including gating and resampling."""
from pathlib import Path
import sys
import unittest
import numpy as np
from pystoi import stoi

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from stoi_diagnostics import band_scores


class StoiDiagnosticTests(unittest.TestCase):
    def test_correlations_and_gap_contributions_reconstruct_the_actual_metric(self):
        rng=np.random.default_rng(371)
        x=rng.normal(0,.1,22500);y=x+rng.normal(0,.03,len(x))
        for sr in (7500,10000):
            result=band_scores(x,y,sr)
            self.assertAlmostEqual(np.mean([b['correlation'] for b in result['bands']]),stoi(x,y,sr),places=12)
            self.assertAlmostEqual(sum(b['contribution_to_unit_gap'] for b in result['bands']),1-result['stoi'],places=12)
            self.assertEqual(len(result['bands']),15)

    def test_silence_removal_and_array_inputs_do_not_change_the_scalar(self):
        rng=np.random.default_rng(372);x=np.r_[np.zeros(10000),rng.normal(0,.1,20000)]
        result=band_scores(x.tolist(),x.tolist(),10000)
        self.assertAlmostEqual(result['stoi'],1.,places=10)
        self.assertLess(result['retained_stft_frames'],len(x)//128)
        self.assertEqual(result['segments'],len(result['segment_correlations']))

    def test_invalid_or_too_short_inputs_are_not_given_an_artificial_band_score(self):
        for x,y in ((np.zeros(10),np.zeros(9)),(np.ones(100),np.ones(100)),
                (np.array([np.nan]),np.array([0.]))):
            with self.assertRaises(ValueError):band_scores(x,y,7500)


if __name__=='__main__':unittest.main()

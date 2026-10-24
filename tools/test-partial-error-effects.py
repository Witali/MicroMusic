#!/usr/bin/env python3
"""Independent signal controls for the PC partial-perturbation experiment."""
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from harmonic_tracks import HarmonicTrackObjective
spec = importlib.util.spec_from_file_location('partial_error_effects',ROOT/'tools/probe-partial-error-effects.py')
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


class PartialErrorEffectsTests(unittest.TestCase):
    def setUp(self):
        self.sr = 7500
        self.t = np.arange(12032)/self.sr

    def test_identity_and_zero_controls_preserve_all_samples(self):
        source = .2*np.sin(2*np.pi*500*self.t)+np.random.default_rng(4).normal(0,.02,len(self.t))
        objective = HarmonicTrackObjective(source)
        partials,residual,identity = experiment.components(source,objective)
        self.assertEqual(len(identity),len(source))
        self.assertLess(float(np.max(abs(identity-source))),1e-12)
        self.assertLess(float(np.max(abs(experiment.perturb(partials,residual,self.sr)-source))),1e-12)

    def test_frequency_control_detunes_a_single_tone_without_large_level_error(self):
        source = .2*np.sin(2*np.pi*500*self.t)
        objective = HarmonicTrackObjective(source,max_tracks=1)
        partials,residual,_ = experiment.components(source,objective)
        perturbed = experiment.perturb(partials,residual,self.sr,cents=10)
        score = objective.evaluate(perturbed)
        self.assertAlmostEqual(score['frequency_error_cents'],10,delta=2.)
        self.assertLess(score['level_error_db'],.3)

    def test_level_control_changes_levels_without_detuning_resolved_tones(self):
        source = .2*np.sin(2*np.pi*500*self.t)+.2*np.sin(2*np.pi*1400*self.t)
        objective = HarmonicTrackObjective(source,max_tracks=2)
        partials,residual,_ = experiment.components(source,objective)
        perturbed = experiment.perturb(partials,residual,self.sr,db=3)
        score = objective.evaluate(perturbed)
        self.assertGreater(score['level_error_db'],2.)
        self.assertLess(score['frequency_error_cents'],1.)


if __name__ == '__main__':
    unittest.main()

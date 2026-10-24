"""Controlled-ablation tests: isolated factors and an acceptance-independent plan."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('q3_influence', ROOT/'tools/probe-hq4-q3-influence.py')
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


class InfluenceTests(unittest.TestCase):
    def setUp(self):
        self.baseline = dict(spectrogram_loss=1., frequency_trajectory_error=1.,
            level_error=1., missing_reference_energy=.1, extra_candidate_energy=.2,
            continuity_break_rate=.1, weighted_match_rate=.9, stoi=.84, estoi=.65,
            fine_log_error=.5, envelope_error=.6, unsupported_energy=.2, missing_energy=.2,
            harmonic_track_loss=1.)

    def test_weights_isolate_frequency_and_amplitude_at_equal_spectral_weight(self):
        candidate = dict(self.baseline, frequency_trajectory_error=.5, level_error=1.5)
        frequency = study.difference(candidate, self.baseline, (1., 0.))
        amplitude = study.difference(candidate, self.baseline, (0., 1.))
        balanced = study.difference(candidate, self.baseline, (.5, .5))
        self.assertLess(frequency, 1.)
        self.assertGreater(amplitude, 1.)
        self.assertAlmostEqual(balanced, (frequency+amplitude)/2)

    def test_combined_loss_is_not_frozen_but_coverage_and_speech_still_are(self):
        candidate = dict(self.baseline, harmonic_track_loss=100.)
        self.assertTrue(study.feasible(candidate, self.baseline))
        self.assertFalse(study.feasible(dict(candidate, weighted_match_rate=.899), self.baseline))
        self.assertFalse(study.feasible(dict(candidate, stoi=.839), self.baseline))

    def test_proposal_random_recipe_is_identical_when_weighted_acceptance_diverges(self):
        recipes = []
        baseline = self.baseline
        class Objective:
            def evaluate(self, frames, durations):
                mode = int(frames[0, 1])
                if mode == 1:
                    return dict(baseline, frequency_trajectory_error=.8, level_error=1.4)
                return dict(baseline, frequency_trajectory_error=1.2, level_error=.6)
        def proposal(frames, durations, rng):
            value = rng.random()
            recipes.append(value)
            f = frames.copy()
            f[0, 1] = 1 if value < .5 else 2
            return f, durations.copy()
        frames = np.array([[20, 0, 136, 136, 136, 136]], np.uint8)
        durations = np.array([64], np.uint16)
        plan = study.schedule(23213, 20)
        with patch.object(study, 'proposal', proposal):
            frequency, _ = study.fit(Objective(), frames, durations, baseline, (1., 0.), plan)
            first = recipes.copy()
            recipes.clear()
            amplitude, _ = study.fit(Objective(), frames, durations, baseline, (0., 1.), plan)
        self.assertEqual(first, recipes)
        self.assertNotEqual(int(frequency[0][0, 1]), int(amplitude[0][0, 1]))


if __name__ == '__main__':
    unittest.main()

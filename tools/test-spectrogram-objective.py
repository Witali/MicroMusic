"""Reference-driven fitting distinguishes spectral structure from global gain."""
from pathlib import Path
import importlib.util
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from spectrogram_objective import SpectrogramObjective

spec = importlib.util.spec_from_file_location('spectrogram_refiner', ROOT/'tools/refine-hq4-spectrogram.py')
refiner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refiner)


class SpectrogramTests(unittest.TestCase):
    def setUp(self):
        t = np.arange(8192)/7500
        self.reference = (.25*np.sin(2*np.pi*220*t)+.1*np.sin(2*np.pi*660*t))*(.6+.4*np.sin(2*np.pi*3*t))
        self.objective = SpectrogramObjective(self.reference)

    def test_identical_gain_and_sign_are_neutral(self):
        for factor in (1., .2, -3.):
            self.assertLess(self.objective.evaluate(self.reference*factor)['spectrogram_loss'], 1e-10)

    def test_added_unrelated_harmonic_is_penalized(self):
        t = np.arange(len(self.reference))/7500
        score = self.objective.evaluate(self.reference+.2*np.sin(2*np.pi*1700*t))
        self.assertGreater(score['unsupported_energy'], .1)
        self.assertGreater(score['envelope_error'], .1)

    def test_wrong_time_envelope_is_penalized(self):
        candidate = np.roll(self.reference, 1200)
        self.assertGreater(self.objective.evaluate(candidate)['spectrogram_loss'], .05)

    def test_duration_rate_and_nonfinite_input_are_rejected(self):
        for candidate in (self.reference[:-1], np.full(8192, np.nan), np.zeros((8192, 2))):
            with self.assertRaises(ValueError):
                self.objective.evaluate(candidate)
        with self.assertRaises(ValueError):
            SpectrogramObjective(self.reference, 8000)
        with self.assertRaises(ValueError):
            SpectrogramObjective(np.zeros(8192))

    def test_scalar_gain_cannot_hide_worse_component(self):
        # This reproduces the pulse experiment's failure mode: a lower mean
        # score concealed extra energy between the original spectral ridges.
        search = refiner.Search.__new__(refiner.Search)
        search.baseline = dict(fine_log_error=.7, envelope_error=.6,
                               unsupported_energy=.2, missing_energy=.3)
        search.config = dict(stoi_floor=.8, estoi_floor=.7,
                             spectral_ceiling=.9, log_spectral_ceiling=.9)
        good = dict(loss=.5, stoi=.81, estoi=.71, spectral_loss=.8,
                    log_spectral_error=.8, **search.baseline)
        self.assertTrue(search.feasible(good))
        for component in search.components:
            worse = dict(good, loss=.1)
            worse[component] += .01
            self.assertFalse(search.feasible(worse), component)


if __name__ == '__main__':
    unittest.main()

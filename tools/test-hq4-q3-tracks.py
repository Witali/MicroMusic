"""Track-fit guard tests: a better aggregate cannot hide missing speech."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('q3_track_fit', ROOT/'tools/probe-hq4-q3-tracks.py')
fit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fit)


class TrackFitGuards(unittest.TestCase):
    def setUp(self):
        self.baseline = dict(stoi=.84, estoi=.65, fine_log_error=.49,
            envelope_error=.60, unsupported_energy=.20, missing_energy=.20,
            harmonic_track_loss=.95, missing_reference_energy=.10,
            extra_candidate_energy=.16, weighted_match_rate=.90,
            continuity_break_rate=.02,
            difference_loss=.73)

    def test_each_frozen_floor_and_ceiling_survives_a_better_aggregate(self):
        self.assertTrue(fit.feasible(self.baseline, self.baseline))
        for key in fit.FLOORS+fit.TRACK_FLOORS+fit.COMPONENTS+fit.TRACK_CEILINGS+('harmonic_track_loss',):
            score = dict(self.baseline, difference_loss=.50)
            score[key] += -.0001 if key in fit.FLOORS+fit.TRACK_FLOORS else .0001
            with self.subTest(guard=key):
                self.assertFalse(fit.feasible(score, self.baseline))

    def test_a_matching_gain_cannot_be_obtained_by_dropping_hard_tracks(self):
        score = dict(self.baseline, harmonic_track_loss=.8,
                     missing_reference_energy=.11, weighted_match_rate=.89,
                     difference_loss=.65)
        self.assertFalse(fit.feasible(score, self.baseline))
        # Annealing may inspect this state, but its penalty is separate from
        # eligibility and cannot turn it into a valid exported elite.
        self.assertGreater(fit.working_energy(score, self.baseline), score['difference_loss'])


if __name__ == '__main__':
    unittest.main()

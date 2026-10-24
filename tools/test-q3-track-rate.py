"""Real stream reduction, hard partial-error bounds and monotonic tolerances."""
import argparse
import importlib.util
from pathlib import Path
import random
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from harmonic_tracks import HarmonicTrackObjective
from hq4_core import pack_stream, unpack_stream
from hq4_q3 import render
from q3_track_rate import TrackLimits, byte_saving_candidates, refitted_candidates, reduce_rate

spec = importlib.util.spec_from_file_location('rate_cli', ROOT/'tools/compress-hq4-q3-tracks.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class TrackRateTests(unittest.TestCase):
    def frames(self, count=8):
        f = np.tile(np.array([40, 0, 0x88, 0x88, 0x88, 0x88], np.uint8), (count, 1))
        f[1::2, 2] = 0x89
        return f, np.full(count, 64, np.uint16)

    def score(self):
        return dict(frequency_error_p95_cents=70., frequency_error_p95_hz=20.,
                    level_error_p95_db=10., missing_reference_energy=.2,
                    extra_candidate_energy=.3, weighted_match_rate=.8, continuity_break_rate=.1)

    def test_candidates_are_actually_smaller_and_preserve_complete_time(self):
        f, d = self.frames()
        snapshot = f.copy(), d.copy()
        before = len(pack_stream(f, d))
        candidates = byte_saving_candidates(f, d)
        self.assertTrue(candidates)
        self.assertTrue(any(c['operation'].startswith('merge-') for c in candidates))
        self.assertTrue(any(c['operation'].startswith('share-') for c in candidates))
        for candidate in candidates:
            self.assertLess(len(candidate['payload']), before)
            self.assertEqual(int(candidate['durations'].sum()), int(d.sum()))
            self.assertTrue(set(candidate['durations']).issubset({64, 128, 192, 256}))
            actual_f, actual_d = unpack_stream(candidate['payload'])
            np.testing.assert_array_equal(actual_f, candidate['frames'])
            np.testing.assert_array_equal(actual_d, candidate['durations'])
        np.testing.assert_array_equal(f, snapshot[0])
        np.testing.assert_array_equal(d, snapshot[1])

    def test_joint_refits_never_introduce_unstable_minus_eight(self):
        f, d = self.frames()
        candidate = byte_saving_candidates(f, d)[0]
        self.assertEqual(refitted_candidates(candidate, random.Random(1), 0), [])
        for variant in refitted_candidates(candidate, random.Random(1), 16):
            self.assertFalse(np.any((variant['frames'][:, 2:] & 15) == 0))
            self.assertFalse(np.any((variant['frames'][:, 2:] >> 4) == 0))

    def test_looser_frequency_amplitude_cannot_hide_missing_extra_or_broken_tracks(self):
        baseline = self.score()
        limits = TrackLimits.create(baseline, 100., 5., relative=True)
        self.assertFalse(limits.failures(baseline))
        for component in ('missing_reference_energy', 'extra_candidate_energy', 'continuity_break_rate'):
            wrong = dict(baseline, **{component:baseline[component]+.01})
            self.assertIn(component, limits.failures(wrong))
        wrong = dict(baseline, weighted_match_rate=.7)
        self.assertIn('weighted_match_rate', limits.failures(wrong))
        self.assertEqual(limits.frequency_cap, 170.)
        self.assertEqual(limits.amplitude_cap, 15.)

    def test_absolute_bounds_report_existing_codec_error_instead_of_relabelling_it(self):
        limits = TrackLimits.create(self.score(), 50., 3., relative=False)
        self.assertEqual(set(limits.failures(self.score())), {'frequency_error_p95_cents', 'level_error_p95_db'})

    def test_maximum_caps_include_outliers_that_p95_deliberately_does_not_bound(self):
        score = dict(self.score(), frequency_error_max_cents=140., level_error_max_db=24.)
        p95 = TrackLimits.create(score, 80., 15., statistic='p95')
        maximum = TrackLimits.create(score, 80., 15., statistic='max')
        self.assertFalse(p95.failures(score))
        self.assertEqual(set(maximum.failures(score)), {'frequency_error_max_cents', 'level_error_max_db'})

    def test_optional_intelligibility_floor_is_independent_of_loose_track_tolerance(self):
        score = dict(self.score(), stoi=.79)
        limits = TrackLimits.create(score, 500., 50., minimum_stoi=.8)
        self.assertEqual(limits.failures(score), ['minimum_stoi'])
        self.assertFalse(limits.failures(dict(score, stoi=.8)))

    def test_real_zero_gain_frames_compress_monotonically_without_changing_decoding(self):
        f, d = self.frames(32)
        objective = HarmonicTrackObjective(np.zeros(int(d.sum())))
        def evaluate(frames, durations):
            pcm, wraps = render(frames, durations, 1)
            self.assertEqual(int(wraps.sum()), 0)
            return objective.evaluate((pcm.astype(float)-128)/128)
        baseline = evaluate(f, d)
        previous = len(pack_stream(f, d))
        for frequency, amplitude in ((0., 0.), (25., 1.), (75., 2.)):
            limits = TrackLimits.create(baseline, frequency, amplitude, relative=True)
            result = reduce_rate(f, d, evaluate, limits, random.Random(9), max_evaluations=12, repairs=0)
            self.assertTrue(result['feasible'])
            self.assertLessEqual(result['stream_bytes'], previous)
            f, d = result['frames'], result['durations']
            np.testing.assert_array_equal(render(f, d, 1)[0], np.full(2048, 128, np.uint8))
            previous = result['stream_bytes']
        self.assertLess(previous, 32*3)

    def test_sweep_rejects_nonmonotonic_or_ambiguous_units(self):
        args = argparse.Namespace(sweep='0:0,25:1,75:2', frequency_tolerance_cents=None,
            frequency_tolerance_hz=None, amplitude_tolerance_db=None, frequency_unit='cents')
        self.assertEqual(cli.tolerance_levels(args), ([(0., 0.), (25., 1.), (75., 2.)], 'cents'))
        args.sweep = '50:3,25:4'
        with self.assertRaises(ValueError):
            cli.tolerance_levels(args)
        args.sweep = '0:0,25:1'
        args.frequency_tolerance_hz = 10.
        with self.assertRaises(ValueError):
            cli.tolerance_levels(args)


if __name__ == '__main__':
    unittest.main()

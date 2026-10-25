"""Global allocation oracle and end-to-end native byte/quality constraints."""
import itertools
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from global_rate_pcm16 import allocate, optimize
from batch_decoder import BatchSession
from wav_to_lpx4 import encode_segment
from test_beam_excitation import raw_fixture


class AllocationTests(unittest.TestCase):
    def test_pareto_dp_matches_exhaustive_small_problem(self):
        curves = [[(1, 9.), (4, 1.)], [(1, 8.), (4, 0.)], [(1, 7.), (3, 2.)]]
        for budget in range(3, 13):
            exhaustive = []
            for picks in itertools.product(range(2), repeat=3):
                cost = sum(curves[i][j][0] for i, j in enumerate(picks))
                loss = sum(curves[i][j][1] for i, j in enumerate(picks))
                if cost <= budget:
                    exhaustive.append((loss, cost))
            paths, report = allocate(curves, budget, max_states=100)
            self.assertEqual(min((v, c) for c, v, _ in paths), min(exhaustive))
            self.assertEqual(report['pruned_states'], 0)
        self.assertEqual(allocate(curves, 2)[0], [])

    def test_explicit_state_cap_is_bounded_and_deterministic(self):
        curves = [[(1, 10.), (2, 6.), (3, 3.), (4, 1.)]] * 8
        first, report = allocate(curves, 32, max_states=3)
        self.assertEqual(first, allocate(curves, 32, max_states=3)[0])
        self.assertLessEqual(len(first), 3)
        self.assertGreater(report['pruned_states'], 0)
        for cost, loss, picks in first:
            self.assertEqual(cost, sum(curves[i][p][0] for i, p in enumerate(picks)))
            self.assertEqual(loss, sum(curves[i][p][1] for i, p in enumerate(picks)))


class NativeAllocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = BatchSession('batch')
        cls.decoder = cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.session.__exit__(None, None, None)

    def test_zero_excitation_compresses_without_changing_pcm_or_cost_peaks(self):
        source = raw_fixture(samples=1601)
        ref = self.decoder.decode_one_s16(source, 1601)
        out, pcm, report = optimize(source, ref, self.decoder, max_candidates=12, kind='music')
        self.assertLess(len(out), len(source))
        np.testing.assert_array_equal(pcm, ref)
        for k in ('bit_calls', 'rom_reads', 'max_bit_calls_sample', 'max_bit_calls_80', 'max_bit_calls_160'):
            self.assertLessEqual(report['decoder_cost_after'][k], report['decoder_cost_before'][k])

    def test_reallocates_silence_credit_to_difficult_blocks(self):
        rng = np.random.default_rng(20261025)
        ref = np.zeros(1601, np.int16)
        ref[400:1200] = np.clip(np.rint(rng.normal(0, 4500, 800)), -20000, 20000).astype(np.int16)
        baseline, original, _ = encode_segment(ref, self.decoder, fixed_bits=3, pre=0,
            lambdas=(0.,), analysis_profiles=('flat',), kind='music')
        out, pcm, report = optimize(baseline, ref, self.decoder, rounds=1,
            max_states=256, max_candidates=32, kind='music')
        self.assertLessEqual(len(out), len(baseline))
        old_error = np.sum((ref.astype(np.int64) - original) ** 2)
        new_error = np.sum((ref.astype(np.int64) - pcm) ** 2)
        self.assertLess(new_error, old_error)
        self.assertTrue(report['searches'])
        self.assertLessEqual(len(report['trials']), 32)

    def test_candidate_budget_and_invalid_inputs(self):
        blob = raw_fixture(samples=160)
        ref = np.zeros(160, np.int16)
        out, pcm, report = optimize(blob, ref, self.decoder, max_candidates=1, kind='music')
        self.assertLessEqual(len(report['trials']), 1)
        for options in ({'max_candidates': 0}, {'max_states': 1}, {'rounds': 0}, {'kind': 'invalid'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                optimize(blob, ref, self.decoder, **options)


if __name__ == '__main__':
    unittest.main()

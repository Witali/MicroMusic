import itertools
import unittest
import numpy as np

import speech_compact as compact
from speech_chain_frontier import assemble


def fixture(amplitude, samples=81, extra=False):
    frames = (samples + 319) // 320
    return compact.pack(samples, 6, [[4 + 6 * i for i in range(10)]] * frames,
        [(8, 55, 0)] * (frames * 2), [(5, amplitude)] * (frames * 16), pre=0,
        extras=[(7, 2) if extra and i == 0 else (-1, 0) for i in range(frames * 8)])[0]


class ChainFrontierTests(unittest.TestCase):
    def test_complete_continuous_objective_matches_exhaustive_oracle(self):
        pools = [[fixture(a) for a in (-6, -2, 3)], [fixture(a, 161) for a in (-4, 1, 7)]]
        seed = [pools[0][0], pools[1][0]]
        target = np.concatenate([compact.decode_model(pools[0][2]), compact.decode_model(pools[1][1])])
        def objective(pcm):
            error = pcm.astype(float) - target
            # One physical error history crosses the segment reset boundary.
            weighted = error.copy(); weighted[1:] += .7 * error[:-1]
            return float(weighted @ weighted)
        reference = np.zeros(len(target), np.int16)
        cap = sum(map(len, seed))
        result = assemble(reference, seed, pools, cap, objective=objective)
        expected = min(itertools.product(*pools), key=lambda blobs: objective(np.concatenate([compact.decode_model(b) for b in blobs])))
        self.assertEqual(result.tradeoff.streams, expected)
        self.assertEqual(result.tradeoff.file_bytes, sum(map(len, expected)))
        self.assertEqual(result.report['objective_evaluations'], 9)
        self.assertEqual(result.report['enumeration'], 'exhaustive')
        self.assertLessEqual(result.tradeoff.file_bytes, cap)

    def test_real_chain_cap_fits_without_proportional_segment_budgets(self):
        plain = [fixture(-2, 81), fixture(3, 641)]
        seed = [fixture(-2, 81, True), fixture(3, 641, True)]
        reference = np.concatenate([compact.decode_model(b) for b in seed])
        cap = len(plain[0]) + len(seed[1])
        result = assemble(reference, seed, [[plain[0]], [plain[1]]], cap)
        self.assertIsNotNone(result.tradeoff)
        self.assertLessEqual(sum(map(len, result.tradeoff.streams)), cap)
        self.assertEqual(result.report['segment_samples'], [81, 641])
        too_small = assemble(reference, seed, [[plain[0]], [plain[1]]], 22)
        self.assertIsNone(too_small.selected)
        self.assertIsNone(too_small.tradeoff)
        self.assertEqual(too_small.report['status'], 'no_pool_combination_fits')
        self.assertEqual(too_small.report['objective_evaluations'], 0)

    def test_metric_tradeoff_kept_separate_from_conservative_rollback(self):
        seed = [fixture(-2), fixture(1)]
        other = [fixture(7), fixture(-8)]
        reference = np.concatenate([compact.decode_model(b) for b in seed])
        target = np.concatenate([compact.decode_model(b) for b in other])
        def objective(pcm):
            error = pcm.astype(np.int64) - target
            return int(error @ error)
        result = assemble(reference, seed, [[other[0]], [other[1]]], sum(map(len, seed)), objective=objective)
        self.assertEqual(result.selected.streams, tuple(seed))
        self.assertEqual(result.tradeoff.streams, tuple(other))
        self.assertFalse(result.tradeoff.conservative_floors_passed)
        self.assertTrue(result.selected.conservative_floors_passed)
        np.testing.assert_array_equal(result.selected.pcm, reference)

    def test_bounded_beam_reports_finite_evaluation_scope(self):
        pool = [fixture(a) for a in range(-8, 8)]
        seed = [pool[0]] * 3
        reference = np.concatenate([compact.decode_model(b) for b in seed])
        result = assemble(reference, seed, [pool] * 3, sum(map(len, seed)),
                          beam_width=2, max_evaluations=5)
        self.assertEqual(result.report['enumeration'], 'bounded_beam')
        self.assertTrue(result.report['evaluation_limit_reached'])
        self.assertEqual(result.report['objective_evaluations'], 5)
        self.assertEqual(result.selected.streams, tuple(seed))

    def test_geometry_and_complete_reference_are_enforced(self):
        seed = fixture(1)
        reference = compact.decode_model(seed)
        with self.assertRaises(ValueError):
            assemble(reference[:-1], [seed], [[]], len(seed))
        with self.assertRaises(ValueError):
            assemble(reference, [seed], [[fixture(1, 82)]], len(seed))
        with self.assertRaises(ValueError):
            assemble(reference, seed, [[]], len(seed))
        with self.assertRaises(ValueError):
            assemble(reference, [seed], [[]], True)
        with self.assertRaises(ValueError):
            assemble(reference, [seed], [[]], len(seed), objective=lambda pcm: float('nan'))
        with self.assertRaises(ValueError):
            assemble(reference, [seed], [[]], len(seed), objective=object())
        def broken(pcm):
            raise StopIteration('objective failure')
        with self.assertRaisesRegex(StopIteration, 'objective failure'):
            assemble(reference, [seed], [[]], len(seed), objective=broken)


if __name__ == '__main__':
    unittest.main()

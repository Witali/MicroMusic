import unittest
from unittest.mock import patch

import numpy as np

from batch_decoder import BatchSession
import refine_speech_trajectory as trajectory
import speech_compact as compact
from test_refine_speech_trajectory import seed, altered


class TrajectoryCpuBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = BatchSession('batch', speech=True, speech_compact=True, compact_only=True)
        cls.decoder = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__()

    def run_search(self, reference, blob, **settings):
        return trajectory.refine(reference, blob, self.decoder, len(blob)+40,
            frame_limit=2, max_evaluations=32, speech=False, **settings)

    def test_zero_cpu_returns_initialized_exact_baseline_and_score(self):
        for profile in (4, 6):
            blob = seed(profile, 641)
            reference = compact.decode_model(altered(blob, [0]))
            captured = []
            result, pcm, report, raw = self.run_search(reference, blob, cpu_seconds=0,
                candidate_sink=lambda stream, score: captured.append((stream, score)))
            self.assertEqual(result, blob)
            self.assertEqual(raw, blob)
            np.testing.assert_array_equal(pcm, compact.decode_model(blob))
            self.assertEqual(captured, [(blob, float(report['baseline']['pcm16']['error_energy']))])
            self.assertEqual(report['full_synthesis_evaluations'], 0)
            self.assertTrue(report['cpu_budget']['exhausted'])
            self.assertEqual(report['candidate_sink_streams'], 1)

    def test_expiration_keeps_completed_path_and_finalizes_normally(self):
        blob = seed(4, 641)
        reference = compact.decode_model(altered(blob, [0]))
        clock = [0.]
        captured = []
        def sink(stream, score):
            captured.append((stream, score))
            if stream != blob:
                clock[0] = 1.5
        with patch('search_cpu_budget.time.process_time', side_effect=lambda: clock[0]):
            result, pcm, report, raw = self.run_search(reference, blob, cpu_seconds=1,
                candidate_sink=sink, excitation_candidates=0)
        self.assertGreater(len(captured), 1)
        self.assertEqual(len(captured), len({stream for stream, _ in captured}))
        self.assertTrue(report['cpu_budget']['exhausted'])
        self.assertGreater(report['full_synthesis_evaluations'], 0)
        self.assertEqual(report['cpu_budget']['search_cpu_seconds'], 1.5)
        self.assertGreaterEqual(report['cpu_budget']['cpu_overshoot_seconds'], .5)
        self.assertTrue(any(c['status'] == 'cpu_limit' for c in report['checkpoints']))
        self.assertIn(result, [stream for stream, _ in captured])
        self.assertIn(raw, [stream for stream, _ in captured])
        np.testing.assert_array_equal(pcm, compact.decode_model(result))

    def test_sink_scores_are_the_active_objective_and_bytes_are_distinct(self):
        blob = seed(6, 641)
        reference = compact.decode_model(altered(blob, [0]))
        captured = []
        def objective(pcm):
            return float(np.sum(np.abs(reference.astype(np.int64)-pcm.astype(np.int64))))
        _, _, report, _ = self.run_search(reference, blob, objective=objective,
            objective_name='absolute_error', candidate_sink=lambda stream, score: captured.append((stream, score)))
        self.assertGreater(len(captured), 1)
        self.assertEqual(report['candidate_sink_streams'], len(captured))
        self.assertEqual(len(captured), len({stream for stream, _ in captured}))
        for stream, score in captured:
            self.assertEqual(score, objective(compact.decode_model(stream)))
        self.assertFalse(report['cpu_budget']['exhausted'])

    def test_expiration_between_anchors_keeps_completed_window_status(self):
        blob = seed(4, 641)
        reference = compact.decode_model(altered(blob, [0]))
        clock = [0.]
        def anchors(*args):
            yield 0
            clock[0] = 1.5
            yield 1
        with patch('search_cpu_budget.time.process_time', side_effect=lambda: clock[0]), patch.object(
                trajectory, 'frame_order', side_effect=anchors):
            _, _, report, _ = self.run_search(reference, blob, cpu_seconds=1,
                spectral_candidates=0, excitation_candidates=0)
        self.assertTrue(report['cpu_budget']['exhausted'])
        self.assertEqual(report['completed_windows'], 1)
        self.assertEqual(report['incomplete_windows'], 0)
        self.assertEqual(len(report['checkpoints']), 1)
        self.assertEqual(report['checkpoints'][0]['status'], 'complete')

    def test_cpu_limit_does_not_hide_corrupt_final_native_output(self):
        blob = seed(4, 641)
        reference = compact.decode_model(altered(blob, [0]))
        original = self.decoder.decode_one_s16
        calls = []
        def corrupt_final(stream, count):
            value = original(stream, count).copy()
            calls.append(stream)
            if len(calls) > 1:
                value[0] ^= 1
            return value
        with patch.object(self.decoder, 'decode_one_s16', side_effect=corrupt_final):
            with self.assertRaises(AssertionError): self.run_search(reference, blob, cpu_seconds=0)
        self.assertGreater(len(calls), 1)

    def test_finalization_is_counted_outside_the_search_quota(self):
        blob = seed(6, 641)
        reference = compact.decode_model(altered(blob, [0]))
        original = self.decoder.decode_one_s16
        clock = [0.]
        def charged_native(stream, count):
            value = original(stream, count)
            clock[0] += .25
            return value
        with patch('search_cpu_budget.time.process_time', side_effect=lambda: clock[0]), patch.object(
                self.decoder, 'decode_one_s16', side_effect=charged_native):
            _, _, report, _ = self.run_search(reference, blob, cpu_seconds=0)
        timing = report['cpu_budget']
        self.assertGreater(timing['finalization_cpu_seconds'], 0)
        self.assertAlmostEqual(timing['total_cpu_seconds'], timing['search_cpu_seconds']+timing['finalization_cpu_seconds'])
        self.assertEqual(timing['cpu_overshoot_seconds'], timing['total_cpu_seconds'])

    def test_invalid_budget_or_sink_fails_before_model_work(self):
        blob = seed()
        reference = compact.decode_model(altered(blob, [0]))
        with patch.object(compact, 'decode_model', side_effect=AssertionError('unexpected model work')):
            for limit in (True, -1, float('nan'), float('inf'), '2'):
                with self.assertRaises(ValueError): self.run_search(reference, blob, cpu_seconds=limit)
            with self.assertRaises(ValueError): self.run_search(reference, blob, candidate_sink=1)


if __name__ == '__main__':
    unittest.main()

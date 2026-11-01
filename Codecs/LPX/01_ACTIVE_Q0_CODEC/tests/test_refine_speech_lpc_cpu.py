import json
import unittest
from unittest.mock import patch

import numpy as np

from batch_decoder import BatchSession
import refine_speech_lpc as lpc
import speech_compact as compact
from standard_metrics import pwm_duties
from test_speech_v4 import fixture


def seed_and_target():
    fields = list(compact.unpack(compact.repack(fixture(6, 1280))[0]))
    fields[2] = [[3 + 6*i for i in range(10)] for _ in range(4)]
    fields[3], fields[5], fields[6] = [(25, 60, 8)]*8, 0, 0
    blob = compact.pack(*fields[:7], extras=[(i % 40, 3) for i in range(32)])[0]
    fields = list(compact.unpack(blob))
    fields[2] = [row.copy() for row in fields[2]]
    fields[2][1][4] += 1
    return blob, compact.pack(*fields[:7], extras=fields[7])[0]


class LpcCpuBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = BatchSession('batch', speech=True, speech_compact=True)
        cls.only_context = BatchSession('batch', speech=True, speech_compact=True, compact_only=True)
        cls.decoder, cls.only = cls.context.__enter__(), cls.only_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.only_context.__exit__()
        cls.context.__exit__()

    def search(self, reference, blob, **kwargs):
        return lpc.refine(reference, blob, self.decoder, len(blob) + 30,
                          frame_limit=4, spectral_candidates=4, speech=False, **kwargs)

    def verify_sink(self, reference, emitted, blob, score):
        pcm = compact.decode_model(blob)
        for decoder in (self.decoder, self.only):
            np.testing.assert_array_equal(decoder.decode_one_s16(blob, len(reference)), pcm)
            np.testing.assert_array_equal(decoder.decode_one(blob, len(reference)), pwm_duties(pcm))
        error = reference.astype(np.int64) - pcm.astype(np.int64)
        self.assertEqual(score, int(np.dot(error, error)))
        emitted.append((blob, score))

    def test_zero_quota_emits_scored_serialized_baseline_without_proposals(self):
        blob, target = seed_and_target()
        reference = compact.decode_model(target)
        emitted = []
        with patch('refine_speech_lpc.coefficient_patch', side_effect=AssertionError('no proposal')), patch(
                'refine_speech_lpc.adapt_excitation', side_effect=AssertionError('no refit')):
            result, pcm, report, raw = self.search(reference, blob, cpu_seconds=0,
                candidate_sink=lambda b, score: self.verify_sink(reference, emitted, b, score))
        self.assertEqual(result, blob)
        self.assertEqual(raw, blob)
        np.testing.assert_array_equal(pcm, compact.decode_model(blob))
        self.assertEqual([b for b, _ in emitted], [blob])
        self.assertEqual(report['spectral_trials'], 0)
        self.assertTrue(report['cpu_budget']['exhausted'])
        self.assertGreaterEqual(report['cpu_budget']['total_cpu_seconds'],
                                report['cpu_budget']['search_cpu_seconds'])
        json.dumps(report, allow_nan=False)

    def test_expiration_preserves_completed_accepted_and_raw_bookkeeping(self):
        blob, target = seed_and_target()
        reference = compact.decode_model(target)
        for allowed in (True, False):
            clock = [0.]
            emitted = []
            def sink(candidate, score):
                self.verify_sink(reference, emitted, candidate, score)
                if candidate != blob: clock[0] = 3.
            with self.subTest(allowed=allowed), patch('search_cpu_budget.time.process_time',
                    side_effect=lambda: clock[0]), patch('refine_speech_lpc.no_regression', return_value=allowed):
                result, pcm, report, raw = self.search(reference, blob, cpu_seconds=1, candidate_sink=sink)
            self.assertEqual(len(emitted), 2)
            self.assertNotEqual(emitted[1][0], blob)
            self.assertEqual(raw, emitted[1][0])
            self.assertEqual(result, emitted[1][0] if allowed else blob)
            np.testing.assert_array_equal(pcm, compact.decode_model(result))
            self.assertEqual(report['accepted_frames'], int(allowed))
            self.assertEqual(report['full_metric_evaluations'], 1)
            self.assertTrue(report['cpu_budget']['exhausted'])
            self.assertEqual(report['cpu_budget']['cpu_overshoot_seconds'], 2.)

    def test_disabled_budget_and_sink_preserve_numerical_results(self):
        blob, target = seed_and_target()
        reference = compact.decode_model(target)
        first = self.search(reference, blob)
        emitted = []
        second = self.search(reference, blob, cpu_seconds=None,
            candidate_sink=lambda b, score: self.verify_sink(reference, emitted, b, score))
        self.assertEqual(first[0], second[0])
        np.testing.assert_array_equal(first[1], second[1])
        self.assertEqual(first[3], second[3])
        omit = {'seconds', 'cpu_budget'}
        self.assertEqual({k: v for k, v in first[2].items() if k not in omit},
                         {k: v for k, v in second[2].items() if k not in omit})
        blobs = [b for b, _ in emitted]
        self.assertEqual(len(blobs), len(set(blobs)))
        self.assertIn(second[0], blobs)
        self.assertIn(second[3], blobs)
        self.assertFalse(second[2]['cpu_budget']['exhausted'])

    def test_invalid_budget_or_sink_fails_before_heavy_initialization(self):
        blob, target = seed_and_target()
        reference = compact.decode_model(target)
        with patch('refine_speech_lpc.coefficient_trace', side_effect=AssertionError('not initialized')):
            for kwargs in (dict(cpu_seconds=True), dict(cpu_seconds=-1), dict(cpu_seconds=float('nan')),
                           dict(cpu_seconds=float('inf')), dict(cpu_seconds='1'), dict(candidate_sink=[])):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    self.search(reference, blob, **kwargs)

    def test_sink_error_is_not_silently_converted_to_budget_expiration(self):
        blob, target = seed_and_target()
        with self.assertRaisesRegex(RuntimeError, 'sink failed'):
            self.search(compact.decode_model(target), blob,
                        candidate_sink=lambda *_: (_ for _ in ()).throw(RuntimeError('sink failed')))

    def test_original_finalization_still_rejects_native_pwm_mismatch(self):
        blob, target = seed_and_target()
        emitted = []
        class WrongPwm:
            def decode_one_s16(self, data, n): return compact.decode_model(data)
            def decode_one(self, data, n): return np.zeros(n, np.uint8)
        with self.assertRaisesRegex(AssertionError, 'result native PWM mismatch'):
            lpc.refine(compact.decode_model(target), blob, WrongPwm(), len(blob) + 30,
                       cpu_seconds=0, speech=False, candidate_sink=lambda *args: emitted.append(args))
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0][0], blob)


if __name__ == '__main__':
    unittest.main()

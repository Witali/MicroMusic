"""The explicit objective wrapper cannot silently weaken the existing gate."""
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from batch_decoder import BatchSession
from refine_speech_perceptual import refine
import speech_compact as compact
from test_speech_v4 import fixture


class ObjectiveWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = BatchSession('batch', speech=True, speech_compact=True, compact_only=True)
        cls.decoder = cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.session.__exit__()

    def test_conservative_mode_is_forced_and_raw_remains_separate(self):
        seed = compact.repack(fixture(6, 321))[0]
        reference = compact.decode_model(seed)
        fields = list(compact.unpack(seed))
        fields[3] = [(max(0, s - 1), lag, gain) for s, lag, gain in fields[3]]
        raw = compact.pack(*fields[:7], extras=fields[7])[0]
        calls = []
        def fake(ref, blob, decoder, cap, **settings):
            calls.append(settings)
            self.assertTrue(np.isfinite(settings['objective'](reference)))
            return blob, reference, {}, raw
        with patch.dict(sys.modules, {'refine_speech_trajectory': SimpleNamespace(refine=fake)}):
            selected, pcm, report, alternative = refine(reference, seed, self.decoder, len(seed),
                                                       mode='perceptual')
        self.assertEqual(selected, seed)
        self.assertEqual(alternative, raw)
        np.testing.assert_array_equal(pcm, reference)
        self.assertEqual(calls[0]['selection'], 'conservative')
        self.assertTrue(report['raw_listening_candidate_separate'])
        self.assertFalse(report['raw_conservative_floors_passed'])
        self.assertTrue(report['native_model_pwm_exact'])
        self.assertEqual(report['baseline_objective'], 0)
        self.assertGreater(report['raw_objective'], 0)

    def test_independent_gate_and_byte_cap_check_bad_refiner_outputs(self):
        seed = compact.repack(fixture(4, 321))[0]
        reference = compact.decode_model(seed)
        fields = list(compact.unpack(seed))
        fields[3] = [(max(0, s - 1), lag, gain) for s, lag, gain in fields[3]]
        bad = compact.pack(*fields[:7], extras=fields[7])[0]
        def fake(*args, **settings):
            return bad, compact.decode_model(bad), {}, bad
        with patch.dict(sys.modules, {'refine_speech_trajectory': SimpleNamespace(refine=fake)}):
            with self.assertRaisesRegex(AssertionError, 'conservative gate'):
                refine(reference, seed, self.decoder, len(seed))
            with self.assertRaisesRegex(AssertionError, 'complete-file cap'):
                refine(reference, seed, self.decoder, len(seed) - 1)

    def test_explicit_no_fit_and_no_selection_override(self):
        seed = compact.repack(fixture(4, 20))[0]
        reference = compact.decode_model(seed)
        def fake(*args, **settings):
            return None, None, {'fit_status': 'no-fit'}, None
        with patch.dict(sys.modules, {'refine_speech_trajectory': SimpleNamespace(refine=fake)}):
            selected, pcm, report, raw = refine(reference, seed, self.decoder, len(seed) - 1,
                                                mode='sse')
            self.assertIsNone(selected)
            self.assertIsNone(pcm)
            self.assertIsNone(raw)
            self.assertEqual(report['fit_status'], 'no-fit')
            self.assertTrue(report['automatic_floors_unchanged'])
            for kwargs in ({'selection': 'objective'}, {'objective': lambda x: 0},
                           {'objective_name': 'other'}):
                with self.assertRaises(ValueError):
                    refine(reference, seed, self.decoder, len(seed), **kwargs)
            for cap in (True, 0, 65536, 100.5):
                with self.assertRaises(ValueError):
                    refine(reference, seed, self.decoder, cap)

    def test_real_oversized_seed_exports_tradeoff_frontier_but_no_selected_audio(self):
        from test_refine_speech_trajectory import seed
        blob = seed(4, 640)
        reference = compact.decode_model(blob)
        frontier = []
        selected, pcm, report, raw = refine(
            reference, blob, self.decoder, len(blob) - 2, mode='perceptual',
            frame_limit=1, spectral_candidates=0, excitation_candidates=0,
            max_evaluations=32, frontier=frontier)
        self.assertIsNone(selected)
        self.assertIsNone(pcm)
        self.assertIsNotNone(raw)
        self.assertEqual(report['fit_status'], 'feasible_tradeoff_only')
        self.assertFalse(report['raw_conservative_floors_passed'])
        self.assertTrue(frontier)
        self.assertTrue(all(len(row['stream']) <= len(blob) - 2 for row in frontier))
        self.assertEqual(report['baseline_objective'], 0)
        self.assertGreater(report['raw_objective'], 0)

    def test_real_padded_tail_can_reclaim_bytes_without_changing_played_pcm(self):
        from test_refine_speech_trajectory import seed
        blob = seed(6, 641)
        reference = compact.decode_model(blob)
        selected, pcm, report, _ = refine(
            reference, blob, self.decoder, len(blob) - 2, mode='perceptual',
            frame_limit=1, spectral_candidates=0, excitation_candidates=0,
            max_evaluations=32)
        self.assertIsNotNone(selected)
        self.assertLessEqual(len(selected), len(blob) - 2)
        np.testing.assert_array_equal(pcm, reference)
        self.assertEqual(report['selected_objective'], 0)

    def test_real_search_objective_modes_preserve_perfect_baseline(self):
        from test_refine_speech_trajectory import seed
        for mode in ('sse', 'perceptual'):
            blob = seed(4, 321)
            reference = compact.decode_model(blob)
            selected, pcm, report, raw = refine(
                reference, blob, self.decoder, len(blob), mode=mode,
                frame_limit=1, spectral_candidates=0, excitation_candidates=0,
                max_evaluations=8)
            self.assertEqual(selected, blob)
            self.assertEqual(raw, blob)
            self.assertEqual(report['selected_objective'], 0)
            self.assertTrue(report['automatic_floors_unchanged'])
            np.testing.assert_array_equal(pcm, reference)


if __name__ == '__main__':
    unittest.main()

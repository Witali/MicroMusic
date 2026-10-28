import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf

import speech_compact as compact
from adaptive_speech_voice import refine_candidates
from batch_decoder import BatchSession
from encode_speech_voice import main, encode as seed_encode
from standard_metrics import error_metrics


def stream(profile=6, extra=False, zero=False):
    vector = ([2, 5, 8, 11, 14, 17, 20, 23, 26, 29] if profile == 4
              else [5, 11, 17, 23, 29, 35, 41, 47, 53, 59])
    spectra = [vector] * 3
    params = [(0 if zero else 22, 40, 12)] * 6
    pulses = ([(0, 7), (0, 0)] * 24 if profile == 6
              else [(0, 8), (0, -8)] * 24)
    extras = [(-1, 0)] * 24
    if extra:
        extras[0] = (3, -2)
    return compact.pack(801, profile, spectra, params, pulses, pre=8192, extras=extras)[0]


class AdaptiveVoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.common_context = BatchSession('batch', speech=True, speech_compact=True)
        cls.only_context = BatchSession('batch', speech=True, speech_compact=True, compact_only=True)
        cls.common = cls.common_context.__enter__()
        cls.only = cls.only_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.only_context.__exit__()
        cls.common_context.__exit__()

    def search(self, ref, baseline, seeds=(), **settings):
        return refine_candidates(ref, baseline, seeds, self.common,
            max_bytes=settings.pop('max_bytes', len(baseline)),
            compact_decoder=self.only, speech=False, **settings)

    def test_exact_seed_beats_bad_control_with_both_native_layouts(self):
        good, bad = stream(), stream(zero=True)
        ref = compact.decode_model(good)
        captured = []
        result, pcm, report, raw = self.search(ref, bad, [good, good],
                                              max_refinement_calls=0, candidate_sink=captured.append)
        self.assertEqual(result, good)
        self.assertEqual(raw, good)
        np.testing.assert_array_equal(pcm, ref)
        self.assertEqual(len(report['candidates']), 2)
        self.assertEqual(captured, [bad, good])
        self.assertTrue(report['native_v5_only_checked'])
        self.assertEqual(report['refinement_calls'], 0)
        self.assertTrue(report['selected_differs_from_control'])
        json.dumps(report, allow_nan=False)

    def test_no_fit_returns_no_audio_and_does_not_run_operators(self):
        good = stream()
        result, pcm, report, raw = self.search(compact.decode_model(good), good,
            max_bytes=22, max_refinement_calls=4)
        self.assertIsNone(result)
        self.assertIsNone(pcm)
        self.assertIsNone(raw)
        self.assertEqual(report['refinement_calls'], 0)
        self.assertEqual(report['frontier'], [])

    def test_existing_optional_pulses_are_never_lost_by_adapter(self):
        good = stream(extra=True)
        with patch('adaptive_speech_voice.enhance', side_effect=AssertionError('must not drop extras')):
            result, pcm, report, _ = self.search(compact.decode_model(good), good,
                max_refinement_calls=1, lpc_preset='default')
        self.assertEqual(result, good)
        np.testing.assert_array_equal(pcm, compact.decode_model(good))
        self.assertEqual(report['refinement_calls'], 1)
        self.assertIn('existing_extras_preserved', [row['reason'] for row in report['skipped']])

    def test_marker_overhead_is_checked_before_extra_search(self):
        good = stream(profile=4)
        with patch('adaptive_speech_voice.enhance', side_effect=AssertionError('no marker capacity')):
            result, _, report, _ = self.search(compact.decode_model(good), good,
                max_refinement_calls=1, lpc_preset='default')
        self.assertEqual(result, good)
        self.assertIn('no_capacity_after_all_marker_bits', [row['reason'] for row in report['skipped']])

    def test_full_firmware_cost_cannot_be_replaced_by_stream_size(self):
        good, bad = stream(), stream(zero=True)
        ref = compact.decode_model(good)
        self.assertEqual(len(good), len(bad))
        def actual_image_size(blob):
            return 900 if blob == bad else 1002
        result, _, report, raw = self.search(ref, bad, [good], max_refinement_calls=0,
            firmware_cost=actual_image_size, max_flash_bytes=1000)
        self.assertEqual(result, bad)
        self.assertEqual(raw, bad)
        self.assertTrue(report['full_flash_measured'])
        self.assertFalse(report['candidates'][1]['fits_flash_cap'])
        with self.assertRaises(ValueError):
            self.search(ref, bad, max_flash_bytes=1000)

    def test_control_remains_available_when_refinement_cannot_improve(self):
        good = stream()
        result, _, report, _ = self.search(compact.decode_model(good), good,
            max_refinement_calls=2, lpc_preset='default')
        self.assertEqual(result, good)
        self.assertLessEqual(report['refinement_calls'], 2)
        self.assertEqual(report['frontier'], [0])

    def test_nonspeech_never_requests_stoi_inside_any_operator(self):
        good = stream()
        requests = []
        def nonspeech_metrics(reference, pcm, speech=False):
            self.assertFalse(speech, 'A nonspeech operator requested speech intelligibility')
            requests.append(speech)
            return error_metrics(reference, pcm, False)
        with patch('refine_speech_compact.error_metrics', side_effect=nonspeech_metrics), patch(
                'enhance_speech_compact.error_metrics', side_effect=nonspeech_metrics):
            result, _, report, _ = self.search(compact.decode_model(good), good,
                max_bytes=len(good)+64, max_refinement_calls=3, lpc_preset='default')
        self.assertEqual(result, good)
        self.assertGreater(len(requests), 0)
        self.assertEqual({stage['operator'] for stage in report['stages']},
                         {'extras', 'header_filters', 'joint_lpc_excitation'})

    def test_invalid_bounds_and_mismatched_seeds_fail_before_refinement(self):
        good = stream()
        ref = compact.decode_model(good)
        for kwargs in (dict(max_refinement_calls=True), dict(max_refinement_calls=-1),
                       dict(max_bytes=21), dict(lpc_preset='unbounded'),
                       dict(extra_full_evaluations=0)):
            with self.assertRaises(ValueError):
                self.search(ref, good, **kwargs)
        with self.assertRaises(ValueError):
            self.search(ref, good, [stream(profile=4)])

    def test_default_cli_declares_prequantization_gain_and_adaptive_search(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.wav'
            sf.write(source, 1e-7*np.sin(2*np.pi*np.arange(640)/40), 8000, subtype='FLOAT')
            before = source.read_bytes()
            output = root / 'result'
            with patch.object(sys, 'argv', ['encoder', str(source), str(output),
                                          '--profile', '6', '--refinement-calls', '0']):
                main()
            report = json.loads((output/'report.json').read_text())
            target, _ = sf.read(output/'target.wav', dtype='int16')
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(report['schema'], 'lpx-v5-adaptive-voice-v2')
            self.assertGreater(report['level']['gain'], 1)
            self.assertEqual(report['prepared_target_encoding_level']['gain'], 1)
            self.assertTrue(report['input_conversion']['gain_before_pcm16_rounding'])
            self.assertTrue(np.any(target))
            self.assertIsNotNone(report['selected_bytes'])
            self.assertEqual(report['refinement_calls'], 0)

    def test_changed_gain_cli_uses_old_baseline_only_for_actual_byte_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, baseline_path, output = root/'source.wav', root/'old.l4hy', root/'result'
            sf.write(source, 1e-7*np.sin(2*np.pi*np.arange(640)/40), 8000, subtype='FLOAT')
            baseline, _, _, _ = seed_encode(np.zeros(640, np.int16), 6, self.common, pre_values=(0,))
            baseline_path.write_bytes(baseline)
            with patch.object(sys, 'argv', ['encoder', str(source), str(output), '--profile', '6',
                '--baseline', str(baseline_path), '--refinement-calls', '0']):
                main()
            report = json.loads((output/'report.json').read_text())
            self.assertTrue(report['original_baseline_used_as_byte_cap_only'])
            self.assertEqual(report['complete_byte_cap'], len(baseline))
            self.assertEqual(report['seed_search']['control_kind'], 'fresh_legacy_at_declared_target_level')
            if report['selected_bytes'] is not None:
                self.assertLessEqual(report['selected_bytes'], len(baseline))
            self.assertEqual(baseline_path.read_bytes(), baseline)


if __name__ == '__main__':
    unittest.main()

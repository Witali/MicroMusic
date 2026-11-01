import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf

import adaptive_speech_chain as chain
import adaptive_speech_voice as local
from batch_decoder import BatchSession
from encode_speech_voice import main
import speech_compact as compact
from speech_chain_history import prefix_pool_ids, ranked_prefix_ids, retained_prefixes


def stream(n=801, profile=6, zero=False, extra=False):
    vector = ([2, 5, 8, 11, 14, 17, 20, 23, 26, 29] if profile == 4
              else [5, 11, 17, 23, 29, 35, 41, 47, 53, 59])
    frames = (n + 319) // 320
    pulses = ([(0, 7), (0, 0)] if profile == 6 else [(0, 8), (0, -8)]) * (frames * 8)
    extras = [(-1, 0)] * (frames * 8)
    if extra:
        extras[0] = (3, -2)
    return compact.pack(n, profile, [vector] * frames,
        [(0 if zero else 22, 40, 12)] * (frames * 2), pulses,
        pre=8192, extras=extras)[0]


class AdaptiveChainTests(unittest.TestCase):
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

    def select(self, reference, baseline, histories=(), **settings):
        cap = settings.pop('max_bytes') if 'max_bytes' in settings else sum(map(len, baseline))
        return chain.select_candidates(reference, baseline, histories, self.common,
            max_bytes=cap,
            compact_decoder=self.only, speech=False, **settings)

    def history(self, reference, baseline, seeds):
        pool = []
        _, _, report, _ = local.refine_candidates(reference, baseline, seeds, self.common,
            max_bytes=2 * len(baseline), compact_decoder=self.only, speech=False,
            max_refinement_calls=0, candidate_sink=pool.append)
        return dict(index=0, pool=pool, report=report)

    def test_deeper_search_retains_earlier_fitting_whole_winner(self):
        baseline, early, late = stream(zero=True), stream(), stream(extra=True)
        target = compact.decode_model(late)
        history = self.history(target, baseline, [early, late])
        rows = history['report']['candidates']
        self.assertLess(rows[2]['score'], rows[1]['score'])
        self.assertTrue(rows[1]['admissible'])
        self.assertTrue(rows[2]['admissible'])
        rows[1]['origin'], rows[2]['origin'] = 'header_filters', 'joint_lpc_excitation'
        history['report']['stages'] = [dict(parent=0, operator='header_filters', outputs=[1]),
            dict(parent=1, operator='joint_lpc_excitation', outputs=[2])]
        second = copy.deepcopy(history)
        second['index'] = 1
        whole = np.concatenate([target, target])
        self.assertGreater(2 * len(late), 2 * len(early))
        self.assertEqual(ranked_prefix_ids(history['report'], 1)['selected'], 1)
        self.assertEqual(ranked_prefix_ids(history['report'], 2)['selected'], 2)
        captured = []
        selected, pcm, report, _ = self.select(whole, [baseline, baseline], [history, second],
            max_bytes=2 * len(early), candidate_sink=lambda i, blobs: captured.append(blobs))
        self.assertEqual(selected, (early, early))
        np.testing.assert_array_equal(pcm, np.concatenate([compact.decode_model(early)] * 2))
        self.assertIn('prefix-1-selected', report['candidates'][report['selected_id']]['labels'])
        self.assertEqual(report['validation']['whole_metric_rows'], len(captured))
        self.assertEqual(report['validation']['native_output_domain_comparisons'], 12)
        json.dumps(report, allow_nan=False)

    def test_partial_history_keeps_every_unsearched_reset(self):
        good, bad = stream(), stream(zero=True)
        target = compact.decode_model(good)
        history = self.history(target, bad, [good])
        history['index'] = 1
        selected, _, report, _ = self.select(np.concatenate([target] * 3), [bad] * 3, [history])
        self.assertEqual(selected, (bad, good, bad))
        self.assertEqual(report['reset_segments'], 3)

    def test_raw_local_rejection_does_not_replace_whole_quality_gates(self):
        good, bad = stream(), stream(zero=True)
        target = compact.decode_model(good)
        history = self.history(target, bad, [good])
        history['report']['candidates'][1]['admissible'] = False
        selected, _, report, _ = self.select(target, [bad], [history])
        self.assertEqual(selected, (good,))
        self.assertIn('prefix-0-raw', report['candidates'][report['selected_id']]['labels'])

    def test_cached_local_scores_cannot_admit_a_bad_whole_chain(self):
        good, bad = stream(), stream(zero=True)
        target = compact.decode_model(good)
        history = self.history(target, good, [bad])
        history['report']['candidates'][1].update(score=-1., admissible=True)
        selected, _, report, _ = self.select(target, [good], [history])
        self.assertEqual(selected, (good,))
        rejected = next(r for r in report['candidates'] if 'prefix-0-selected' in r['labels'])
        self.assertFalse(rejected['automatic_quality_eligible'])
        self.assertFalse(rejected['old_pcm_pwm_floors_passed'])

    def test_no_fit_does_not_return_an_oversized_control(self):
        good = stream()
        selected, pcm, report, raw = self.select(compact.decode_model(good), [good], max_bytes=22)
        self.assertIsNone(selected)
        self.assertIsNone(pcm)
        self.assertIsNone(raw)
        self.assertTrue(report['decision']['no_fit'])

    def test_incumbents_dedup_exact_bytes_and_preserve_all_labels(self):
        good, bad = stream(), stream(zero=True)
        selected, _, report, _ = self.select(compact.decode_model(good), [bad],
            incumbents=[(good,), (good,), (bad,)])
        self.assertEqual(selected, (good,))
        self.assertEqual(len(report['candidates']), 2)
        self.assertEqual(report['candidates'][1]['labels'], ['incumbent-0', 'incumbent-1'])

    def test_history_geometry_size_and_causality_are_checked(self):
        good = stream()
        target = compact.decode_model(good)
        original = self.history(target, good, [])
        for kind in ('bytes', 'geometry', 'profile', 'index', 'duplicate', 'future'):
            h = copy.deepcopy(original)
            if kind == 'bytes': h['report']['candidates'][0]['file_bytes'] += 1
            if kind == 'geometry': h['pool'][0] = stream(n=800)
            if kind == 'profile': h['pool'][0] = stream(profile=4)
            if kind == 'index': h['index'] = True
            if kind == 'future': h['report']['stages'] = [dict(parent=3, outputs=[], operator='extras')]
            histories = [h, h] if kind == 'duplicate' else [h]
            with self.assertRaises(ValueError, msg=kind): self.select(target, [good], histories)
        with self.assertRaises(ValueError): self.select(target, [good], incumbents=[(stream(n=800),)])
        with self.assertRaises(ValueError): self.select(target, good, max_bytes=len(good))

    def test_full_flash_requires_complete_chain_measurement(self):
        good, bad = stream(), stream(zero=True)
        target = compact.decode_model(good)
        measured = []
        def image_size(blobs):
            measured.append(blobs)
            return 999 if blobs == (bad,) else 1001
        selected, _, report, _ = self.select(target, [bad], incumbents=[(good,)],
            firmware_cost=image_size, max_flash_bytes=1000)
        self.assertEqual(selected, (bad,))
        self.assertEqual(measured, [(bad,), (good,)])
        self.assertTrue(report['full_flash_measured'])
        with self.assertRaises(ValueError): self.select(target, [bad], max_flash_bytes=1000)

    def test_history_allows_32_calls_without_leaking_future_rows(self):
        good, bad = stream(), stream(zero=True)
        history = self.history(compact.decode_model(good), bad, [good])
        report = history['report']
        report['candidates'][1]['origin'] = 'header_filters'
        report['stages'] = [dict(parent=0, operator='header_filters', outputs=[0])] * 31
        report['stages'].append(dict(parent=0, operator='header_filters', outputs=[1]))
        self.assertEqual(prefix_pool_ids(report, 31), [0])
        self.assertEqual(prefix_pool_ids(report, 32), [0, 1])
        for value in (True, -1, 33):
            with self.assertRaises(ValueError): prefix_pool_ids(report, value)

    def test_live_controller_uses_retention_for_partial_search(self):
        good = stream()
        target = np.concatenate([compact.decode_model(good)] * 2)
        selected, pcm, report, _ = chain.refine_candidates(target, [good, good], self.common,
            max_bytes=2 * len(good), compact_decoder=self.only, speech=False,
            max_refinement_calls=1, lpc_preset='default', segment_indices=[1])
        self.assertEqual(selected, (good, good))
        np.testing.assert_array_equal(pcm, target)
        self.assertEqual(report['new_refinement_calls'], 1)
        self.assertEqual([s['index'] for s in report['segment_searches']], [1])

    def test_complete_record_can_exceed_one_reset_limit(self):
        baseline = (stream(n=64000), stream(n=800))
        target = np.concatenate([compact.decode_model(blob) for blob in baseline])
        selected, pcm, report, _ = self.select(target, baseline)
        self.assertEqual(selected, baseline)
        self.assertEqual(report['samples'], 64800)
        np.testing.assert_array_equal(pcm, target)

    def test_invalid_inputs_fail_before_local_search_or_fitting(self):
        good = stream()
        target = compact.decode_model(good)
        with patch.object(local, 'refine_candidates', side_effect=AssertionError('unexpected search')):
            for settings in (dict(candidate_sink=1), dict(anchors=[stream(n=800)]),
                             dict(seeds=[[stream(profile=4)]]), dict(segment_indices=[True])):
                with self.assertRaises(ValueError):
                    chain.refine_candidates(target, [good], self.common, max_bytes=len(good), **settings)
        with patch('encode_speech_voice.encode', side_effect=AssertionError('unexpected fitting')):
            for settings in (dict(candidate_sink=1), dict(max_refinement_calls=33)):
                with self.assertRaises(ValueError):
                    chain.encode(target, [good], self.common, **settings)

    def test_chain_cli_uses_one_prequantization_gain_and_writes_real_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root/'input.wav', root/'result'
            values = 1e-7 * np.sin(2 * np.pi * np.arange(1602) / 40)
            sf.write(source, values, 8000, subtype='DOUBLE')
            original = source.read_bytes()
            baselines = [root/('old-%d.l4hy' % i) for i in range(2)]
            for path in baselines: path.write_bytes(stream(zero=True))
            with patch.object(sys, 'argv', ['encoder', str(source), str(output), '--profile', '6',
                '--refinement-calls', '0', '--max-bytes', '512', '--baseline-chain', *map(str, baselines)]):
                main()
            report = json.loads((output/'report.json').read_text())
            target, _ = sf.read(output/'target.wav', dtype='int16')
            self.assertEqual(source.read_bytes(), original)
            self.assertGreater(report['level']['gain'], 1)
            self.assertEqual(report['prepared_target_encoding_level']['gain'], 1)
            self.assertTrue(report['original_baseline_used_as_byte_cap_only'])
            self.assertTrue(all(r['control_kind'] == 'fresh_legacy_at_declared_target_level'
                                for r in report['seed_searches']))
            self.assertEqual(report['fresh_fit_calls'], 8)
            self.assertIsNotNone(report['selected_bytes'])
            np.testing.assert_array_equal(target, np.rint(values * 32768 * report['level']['gain']).astype(np.int16))
            for name, key in (('manifest.json', 'selected_bytes'), ('raw-manifest.json', 'raw_bytes')):
                self.assertEqual((output/name).exists(), report[key] is not None)
                if report[key] is not None:
                    manifest = json.loads((output/name).read_text())
                    blobs = [(output/s['file']).read_bytes() for s in manifest['segments']]
                    self.assertEqual(sum(map(len, blobs)), report[key])
                    self.assertEqual(sum(compact.unpack(b)[0] for b in blobs), 1602)
            # Repeat cannot leave stale segment/manifests or overwrite source data.
            with patch.object(sys, 'argv', ['encoder', str(source), str(output),
                '--baseline-chain', *map(str, baselines)]):
                with self.assertRaises(ValueError): main()


if __name__ == '__main__':
    unittest.main()

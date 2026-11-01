"""Contract tests for complete caps, source grouping, capture and immutable caches."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_corpus as study


def entry(role, sizes, score=1., eligible=True, labels=None):
    labels = [str(n) for n in sizes] if labels is None else labels
    return {'role': role, 'stream_bytes': sum(sizes), 'voice_score': score,
            'automatic_quality_eligible': eligible,
            'segments': [{'stream_sha256': label} for label in labels]}


class QuietVoiceProtocolTests(unittest.TestCase):
    def test_true_complete_caps_keep_oversized_local_success_out(self):
        control = entry('control', [50, 50], 2)
        local_selected = entry('concat-selected', [60, 50], 1)
        tradeoff = entry('concat-raw', [45, 45], .5, False)
        rows = [control, local_selected, tradeoff]
        self.assertEqual(study.choose_budget(rows, 100, 100)['selected'], 'control')
        for percent in (95, 90):
            result = study.choose_budget(rows, 100, percent)
            self.assertIsNone(result['selected'])
            self.assertEqual(result['raw_tradeoff'], 'concat-raw')
        self.assertEqual(study.choose_budget([control], 101, 95)['cap'], 95)
        tiny = study.choose_budget([entry('control', [22])], 22, 90)
        self.assertEqual(tiny['cap'], 19)
        self.assertIsNone(tiny['raw_tradeoff'])
        self.assertTrue(tiny['no_fit'])

    def test_global_failed_floor_rolls_back_and_auto_no_fit_stays_null(self):
        control = entry('control', [50, 50], 2)
        globally_bad = entry('concat-selected', [49, 49], .1, False)
        result = study.choose_budget([control, globally_bad, None], 100, 100)
        self.assertEqual(result['selected'], 'control')
        # A fresh declared-target control may be larger than the old quiet cap.
        # An original-level stream is deliberately not added to this auto pool.
        no_auto_fit = study.choose_budget([entry('control', [110]), None, None], 100, 100)
        self.assertIsNone(no_auto_fit['selected'])
        self.assertIsNone(no_auto_fit['raw_tradeoff'])

    def test_duplicate_roles_are_not_distinct_signals_and_control_wins_ties(self):
        rows = [entry(role, [50, 50]) for role in ('concat-raw', 'concat-selected', 'control')]
        result = study.choose_budget(rows, 100, 100)
        self.assertEqual(result['selected'], 'control')
        self.assertEqual(result['fitting_chain_count'], 3)
        self.assertEqual(result['distinct_fitting_chain_count'], 1)
        rows.append(entry('concat-selected', [40, 50]))
        self.assertEqual(study.choose_budget(rows, 100, 100)['selected'], 'concat-selected')

    def test_actual_reset_geometry_keeps_partial_tails_and_order(self):
        record = {'profile': 6, 'samples': 641, 'segments': [
            {'index': 0, 'start': 0, 'samples': 320, 'profile': 6},
            {'index': 1, 'start': 320, 'samples': 321, 'profile': 6}]}
        self.assertEqual(study.geometry(record), [(320, 6), (321, 6)])
        for field, value in (('index', 0), ('start', 319), ('samples', True), ('profile', 4)):
            bad = copy.deepcopy(record)
            bad['segments'][1][field] = value
            with self.assertRaises(ValueError):
                study.geometry(bad)
        bad = dict(record, samples=640)
        with self.assertRaises(ValueError):
            study.geometry(bad)

    def test_source_ordinals_keep_matching_profiles_on_one_shard(self):
        def row(key, profile):
            return {'private_case_id': key, 'profile': profile, 'samples': 640,
                    'reference': {'pcm16_sha256': key}}
        records = [row('one', 4), row('two', 6), row('one', 6), row('two', 4)]
        groups = study.grouped_sources(records)
        self.assertEqual(groups, [[0, 2], [1, 3]])
        worker = {index: ordinal % 2 for ordinal, indices in enumerate(groups) for index in indices}
        self.assertEqual(worker[0], worker[2])
        self.assertEqual(worker[1], worker[3])
        for bad in (records[:-1], records + [row('one', 4)]):
            with self.assertRaises(ValueError):
                study.grouped_sources(bad)
        bad = copy.deepcopy(records)
        bad[2]['reference']['pcm16_sha256'] = 'other'
        with self.assertRaises(ValueError):
            study.grouped_sources(bad)

    def test_capture_forwards_calls_owns_order_dedup_and_counts_actual_fits(self):
        class Receiver:
            def __init__(self):
                self.calls = []
                self.pcm = object()
            def decode_one_s16(self, blob, samples):
                self.calls.append((blob, samples))
                return None if bytes(blob).endswith(b'fail') else self.pcm
            def decode_one(self, blob, samples):
                return ('forwarded', blob, samples)
        receiver = Receiver()
        fitted = []
        capture = study.CapturingDecoder(receiver, fitted.append)
        original = bytearray(b'L4HY\x05control')
        self.assertIs(capture.decode_one_s16(original, 640), receiver.pcm)
        self.assertIs(receiver.calls[0][0], original)
        original[-1] = ord('x')
        capture.decode_one_s16(b'L4HY\x05control', 640)
        capture.decode_one_s16(b'L4HY\x05next', 640)
        capture.decode_one_s16(b'L4HY\x05fail', 640)
        capture.decode_one_s16(b'L4HY\x04legacy', 640)
        capture.decode_one_s16(b'L4HY\x04legacy', 640)
        self.assertEqual(capture.streams, [b'L4HY\x05control', b'L4HY\x05next'])
        self.assertEqual(capture.completed_v4_fits, 2)
        self.assertEqual(fitted, [1, 2])
        self.assertEqual(capture.decode_one(b'anything', 12), ('forwarded', b'anything', 12))

    def test_metric_binding_does_not_accept_nan_stale_keys_or_large_roundoff(self):
        expected = {'size': 100, 'metric': {'score': .25, 'unknown': None}, 'flags': [True, False]}
        study.assert_close(copy.deepcopy(expected), expected)
        near = copy.deepcopy(expected)
        near['metric']['score'] += 1e-13
        study.assert_close(near, expected)
        for value in (float('nan'), float('inf'), .250001):
            bad = copy.deepcopy(expected)
            bad['metric']['score'] = value
            with self.assertRaises(AssertionError):
                study.assert_close(bad, expected)
        bad = copy.deepcopy(expected)
        bad['extra'] = 1
        with self.assertRaises(AssertionError):
            study.assert_close(bad, expected)

    def test_immutable_cache_rejects_modified_report_artifact_and_identity(self):
        owned = Path(__file__).resolve().parents[5] / 'build/quiet-voice-protocol-tests'
        owned.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=owned) as directory:
            folder = Path(directory)
            self.assertTrue(folder.resolve().is_relative_to(owned.resolve()))
            stream = folder / 'segment/capture.l4hy'
            study.immutable_bytes(stream, b'synthetic-stream')
            report = {'status': 'complete'}
            study.save(folder / 'record-private.json', report)
            marker = {'identity': 'epoch',
                      'report_sha256': study.sha((folder / 'record-private.json').read_bytes()),
                      'artifacts_sha256': {'segment/capture.l4hy': study.sha(stream.read_bytes())}}
            study.save(folder / 'complete-private.json', marker)
            self.assertEqual(study.inspect_cache(folder, 'epoch'), report)
            with self.assertRaises(ValueError):
                study.inspect_cache(folder, 'other-epoch')
            study.save(folder / 'record-private.json', {'status': 'tampered'})
            with self.assertRaises(ValueError):
                study.inspect_cache(folder, 'epoch')
            study.save(folder / 'record-private.json', report)
            stream.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                study.inspect_cache(folder, 'epoch')
            with self.assertRaises(ValueError):
                study.immutable_bytes(stream, b'original')

    def test_prepared_binding_identity_rejects_silent_cap_change(self):
        binding = {'records': [{'baseline_bytes': 100}], 'mode': 'preserve'}
        binding['identity'] = study.sha(study.canonical(binding))
        study.validate_binding(binding)
        binding['records'][0]['baseline_bytes'] = 1000
        with self.assertRaises(ValueError):
            study.validate_binding(binding)

    def test_cached_modules_from_another_worktree_cannot_attest_this_core(self):
        root = Path(__file__).resolve().parents[5]
        tools = root / study.PREFIX / 'tools'
        modules = {name: SimpleNamespace(__file__=str(tools / (name + '.py')))
                   for name in study.REQUIRED_CORE_MODULES}
        study.assert_core_module_origins(root, modules)
        bad = dict(modules)
        bad['speech_v4'] = SimpleNamespace(__file__=str(root / 'other-worktree' / study.PREFIX / 'tools/speech_v4.py'))
        with self.assertRaises(ValueError):
            study.assert_core_module_origins(root, bad)
        bad = dict(modules)
        bad['private_alias'] = SimpleNamespace(__file__=str(root / 'other-worktree' / study.PREFIX / 'tools/lpx4.py'))
        with self.assertRaises(ValueError):
            study.assert_core_module_origins(root, bad)
        bad = dict(modules)
        del bad['encode_speech_voice']
        with self.assertRaises(ValueError):
            study.assert_core_module_origins(root, bad)


if __name__ == '__main__':
    unittest.main()

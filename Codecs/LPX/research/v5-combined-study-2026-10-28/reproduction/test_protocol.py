"""Independent contract checks before freezing the combined corpus campaign."""
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_combined as study


def metrics(error, stoi):
    return {domain: dict(error_energy=error, stoi=stoi) for domain in ('pcm16', 'pwm8')}


class CombinedProtocolTests(unittest.TestCase):
    def test_actual_reset_offsets_order_and_complete_length_are_checked(self):
        record = dict(profile=4, samples=621, segments=[
            dict(index=0, start=0, samples=300, profile=4),
            dict(index=1, start=300, samples=321, profile=4)])
        self.assertEqual(study.reset_geometry(record), [(300, 4), (321, 4)])
        for field, bad in (('start', 320), ('index', 0), ('profile', 6), ('samples', 320)):
            changed = dict(record, segments=[dict(s) for s in record['segments']])
            changed['segments'][1][field] = bad
            with self.assertRaises(ValueError):
                study.reset_geometry(changed)

    def test_original_integer_caps_and_shared_completion_room(self):
        self.assertEqual(study.complete_cap(1800, 95), 1710)
        self.assertEqual(study.complete_cap(101, 95), 95)
        pools = [{b'a' * 60}, {b'b' * 40, b'c' * 20}]
        caps = study.generation_caps({100: 101, 95: 95, 90: 90}, pools, 0)
        self.assertEqual([cap for cap, _ in caps], [81, 75, 70])
        # The 95% segment proposal has 75 bytes of real global room; it is
        # not constrained by a proportional floor(60 * .95) = 57-byte cap.
        self.assertEqual(caps[1][1][0]['other_minimum_bytes'], 20)
        self.assertEqual(caps[1][1][0]['complete_cap'], 95)
        for size, percent in ((True, 95), (21, 100), (1800, 94)):
            with self.assertRaises(ValueError):
                study.complete_cap(size, percent)

    def test_stronger_accepted_control_cannot_be_regressed(self):
        original, control = metrics(100, .8), metrics(90, .81)
        flags = study.floor_flags(metrics(95, .82), original, control)
        self.assertTrue(flags['original_floors_passed'])
        self.assertFalse(flags['accepted_control_floors_passed'])
        self.assertFalse(flags['automatic_floors_passed'])
        self.assertTrue(study.floor_flags(metrics(89, .812), original, control)['automatic_floors_passed'])

    def test_failed_original_tradeoff_does_not_authorize_promotion(self):
        original, tradeoff = metrics(100, .8), metrics(85, .79)
        flags = study.floor_flags(metrics(80, .795), original, None, tradeoff)
        self.assertTrue(flags['tradeoff_control_floors_passed'])
        self.assertFalse(flags['original_floors_passed'])
        self.assertFalse(flags['automatic_floors_passed'])
        self.assertTrue(study.floor_flags(metrics(90, .805), original, None, tradeoff)['automatic_floors_passed'])

    def test_capacity_uses_exact_render_serialization_and_no_local_floor(self):
        compact = study.compact
        blob = compact.pack(640, 4, [[2 + 3 * i for i in range(10)]] * 2,
            [(20, 60, 8)] * 4, [(int(compact.v4.POSITIONS4[i % 16]), -8 if i & 1 else 8) for i in range(32)],
            pre=0, bright=0, extras=[(i % 40, 2) for i in range(16)])[0]
        fields = compact.unpack(blob); extras = np.array(fields[7], np.int64); before = extras.copy()
        calls = []
        def serialize(value):
            return compact.pack(*fields[:7], extras=value.tolist())[0]
        def render(value):
            calls.append(value.copy())
            return compact.decode_model(serialize(value))
        def score(pcm):
            value = pcm.astype(np.int64)
            return int(value @ value)
        emitted = []
        callback = study.capacity_callback(640, emitted)
        with patch.object(study, 'improve_extras', wraps=study.improve_extras) as spy:
            result = callback(np.array(fields[2]), 4, extras, len(blob) - 2,
                render=render, objective=score, start=320, max_evaluations=8,
                rate_lambda=0, serialize=serialize)
        self.assertIsNone(spy.call_args.kwargs['admissible'])
        self.assertEqual(spy.call_args.kwargs['candidate_batch'], 32)
        self.assertEqual(callback.statistics['evaluations'], len(calls))
        self.assertLessEqual(result.evaluations, 8)
        self.assertTrue(result.feasible)
        self.assertEqual(emitted, [result.stream])
        self.assertEqual(result.stream, serialize(result.extras))
        np.testing.assert_array_equal(extras, before)
        np.testing.assert_array_equal(result.extras[:8], extras[:8])
        with self.assertRaises(ValueError):
            callback(np.array(fields[2]), 4, extras, len(blob), render=render,
                objective=score, start=0, max_evaluations=8, rate_lambda=1, serialize=serialize)

    def test_input_epoch_rejects_missing_or_mixed_completed_controls(self):
        folder = study.REPOSITORY / 'build/encoder-quality/protocol-fixtures'
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder) as temporary:
            root = Path(temporary)
            records = [dict(id=f'speech-profile-{i:03d}') for i in range(1, 99)]
            manifest = dict(schema='lpx-v5-encoder-quality-study-v1', records=records,
                            source_sha256={'core': 'source'}, quality_source_fingerprint='quality')
            path = root / 'manifest.json'; path.write_text(json.dumps(manifest))
            paths = []
            for label, subset in zip(('tuning', 'evaluation', 'additional'), (records[:40], records[40:80], records[80:])):
                run = dict(status='complete', records=subset, manifest_sha256=study.sha(path.read_bytes()),
                    source_sha256=manifest['source_sha256'], quality_source_fingerprint='quality',
                    encoder_source_sha256={'old': 'fixed'})
                output = root / (label + '.json'); output.write_text(json.dumps(run)); paths.append(output)
            _, controls, _ = study.load_inputs(path, paths)
            self.assertEqual(len(controls), 98)
            last = json.loads(paths[-1].read_text()); last['encoder_source_sha256'] = {'old': 'changed'}
            paths[-1].write_text(json.dumps(last))
            with self.assertRaises(ValueError):
                study.load_inputs(path, paths)
            last['encoder_source_sha256'] = {'old': 'fixed'}; last['records'].pop()
            paths[-1].write_text(json.dumps(last))
            with self.assertRaises(ValueError):
                study.load_inputs(path, paths)


if __name__ == '__main__':
    unittest.main()

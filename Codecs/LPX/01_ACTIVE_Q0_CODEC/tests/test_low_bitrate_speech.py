"""Budget, input ownership and durable-best contracts for the offline search."""
from pathlib import Path
import io
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

import numpy as np

ACTIVE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ACTIVE/'tools'))
import speech_compact as compact
import speech_sparse80 as sparse
import encode_low_bitrate_speech as encoder
from encode_low_bitrate_speech import encode, spectral_bytes, spectral_plans, recover_best_checkpoint
from standard_metrics import pwm_duties, pwm_pcm16


class ModelReceiver:
    """Local wrapper fixture; corpus tests use two real native C receivers."""
    def decode_one_s16(self, blob, count):
        result = compact.decode_model(blob)
        return result if len(result) == count else None

    def decode_one(self, blob, count):
        result = self.decode_one_s16(blob, count)
        return None if result is None else pwm_duties(result)


class LowBitrateContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary_root = ACTIVE.parents[2]/'build/lpx-low-bitrate-tests'
        cls.temporary_root.mkdir(parents=True, exist_ok=True)

    def test_actual_complete_serialization_matches_allocator(self):
        rng = np.random.default_rng(3042)
        target = rng.integers(-4000, 4000, size=19200, dtype=np.int16)
        for sparse80, cap in ((True, 600), (False, 900)):
            maximum = 64 if sparse80 else 32
            desired = np.asarray([sorted(rng.choice(maximum, 10, replace=False)) for _ in range(60)])
            for _, spectra in spectral_plans(target, desired, cap, sparse80):
                if sparse80:
                    blob = sparse.pack(len(target), spectra.tolist(), [(1, 18, 0)]*60, [(0, -8)]*240)
                else:
                    blob = compact.pack(len(target), 4, spectra.tolist(), [(1, 18, 0)]*120, [(0, -8)]*960)[0]
                self.assertLessEqual(len(blob), cap)
                self.assertEqual(spectral_bytes(spectra, sparse80), len(blob))

    def test_early_interruption_keeps_exact_best_checkpoint(self):
        reference = np.rint(1800*np.sin(2*np.pi*173*np.arange(9600)/8000)).astype(np.int16)
        unchanged = reference.copy()
        completed = []
        with tempfile.TemporaryDirectory(dir=self.temporary_root) as temporary:
            output = Path(temporary)/'search'

            def stop(blob, row):
                completed.append((bytes(blob), row.copy()))
                # A consumer can interrupt immediately after a durable result.
                # The best selection and candidate journal already exist.
                saved = json.loads((output/'best-private.json').read_text())
                expected = min((item for item in completed if item[1]['admissible']),
                    key=lambda item: (item[1]['score'], len(item[0]), item[1]['id']))
                self.assertEqual(saved['selected_id'], expected[1]['id'])
                recovered, metadata = recover_best_checkpoint(output)
                self.assertEqual(recovered, expected[0])
                self.assertEqual(metadata['id'], expected[1]['id'])
                self.assertEqual((output/'selected.lpx').read_bytes(), expected[0])
                self.assertEqual(len(json.loads((output/'candidates-private.json').read_text())), len(completed))
                if len(completed) == 2:
                    raise InterruptedError('Fixture requested stop after two complete contenders')

            with self.assertRaises(InterruptedError):
                encode(reference, 2, ModelReceiver(), output=output, pres=(13926,),
                       bandwidths=(.97,), candidate_sink=stop)
            self.assertEqual(len(completed), 2)
            self.assertFalse(list(output.glob('*.partial')))
            self.assertFalse((output/'report-private.json').exists())
            self.assertEqual(len(sparse.decode_model((output/'selected.lpx').read_bytes())), len(reference))
        np.testing.assert_array_equal(reference, unchanged)

    @staticmethod
    def zero_fit(reference, co, steps, source_lags, pre, sparse80, expanded, clip_guard=False):
        block, group = (320, 80) if sparse80 else (160, 20)
        parameters = np.zeros((len(reference)//block, 3), np.int64)
        parameters[:, 1] = 18
        pulses = np.zeros((len(reference)//group, 2), np.int64)
        pulses[:, 1] = -8
        return parameters, pulses, np.zeros(len(reference), np.int16), 3 if not expanded else 7

    def test_duplicate_output_charges_work_and_checks_expected_pcm(self):
        reference = np.zeros(3200, np.int16)
        with patch.object(encoder, 'search_excitation', side_effect=self.zero_fit):
            _, _, report = encode(reference, 2, ModelReceiver(), pres=(13926,), bandwidths=(.97,))
        self.assertEqual(report['candidate_count'], 1)
        self.assertEqual(report['attempt_count'], 2)
        self.assertEqual(report['actual_work_totals']['parameter_trials'], 10)
        self.assertEqual(report['attempts'][1]['duplicate_of'], 0)

        def inconsistent(*args, **kwargs):
            parameters, pulses, expected, work = self.zero_fit(*args, **kwargs)
            if args[6]:
                expected[0] = 1
            return parameters, pulses, expected, work

        with patch.object(encoder, 'search_excitation', side_effect=inconsistent):
            with self.assertRaisesRegex(AssertionError, 'Search/model PCM differs'):
                encode(reference, 2, ModelReceiver(), pres=(13926,), bandwidths=(.97,))

    def test_pointer_survives_convenience_copy_failure(self):
        reference = np.zeros(3200, np.int16)
        original_replace = Path.replace
        with tempfile.TemporaryDirectory(dir=self.temporary_root) as temporary:
            output = Path(temporary)/'search'

            def fail_selected(path, destination):
                if path.name == 'selected.lpx.partial':
                    raise OSError('Injected convenience-copy failure')
                return original_replace(path, destination)

            with patch.object(encoder, 'search_excitation', side_effect=self.zero_fit), patch.object(Path, 'replace', new=fail_selected):
                with self.assertRaisesRegex(OSError, 'Injected'):
                    encode(reference, 2, ModelReceiver(), output=output, pres=(13926,), bandwidths=(.97,))
            blob, row = recover_best_checkpoint(output)
            self.assertTrue(row['admissible'])
            np.testing.assert_array_equal(sparse.decode_model(blob), reference)
            self.assertFalse((output/'selected.lpx').exists())

    def test_cli_listening_export_preserves_integer_pcm16_units(self):
        pcm = np.asarray([-32768, -4096, -512, 0, 512, 4096, 32766], np.int16)
        with tempfile.TemporaryDirectory(dir=self.temporary_root) as temporary:
            output = Path(temporary)/'export'
            output.mkdir()
            report = dict(selected_bytes=80, samples=len(pcm), candidate_count=1, selected_id=0, seconds=0.)
            with patch.object(encoder, 'load_voice_wav', return_value=(pcm, dict(input_level=dict(gain=1)))), \
                    patch.object(encoder, 'encode', return_value=(b'', pcm, report)), \
                    patch('batch_decoder.BatchSession') as session, \
                    patch.object(sys, 'argv', ['encode', 'unused.wav', str(output), '--kbps', '2']), \
                    patch('sys.stdout', new=io.StringIO()):
                session.return_value.__enter__.return_value = ModelReceiver()
                encoder.main()
            for name, expected in (('decoded-pcm16.wav', pcm), ('decoded.wav', pwm_pcm16(pcm))):
                with wave.open(str(output/name), 'rb') as reopened:
                    self.assertEqual(reopened.getframerate(), 8000)
                    self.assertEqual(reopened.readframes(len(pcm)), expected.astype('<i2').tobytes())

    def test_invalid_cap_and_fresh_output_contract(self):
        reference = np.zeros(320, np.int16)
        for kbps in (True, 1.5, 2.0, 4):
            with self.assertRaises(ValueError):
                encode(reference, kbps, ModelReceiver())
        with self.assertRaises(ValueError):
            encode(reference, 2, ModelReceiver(), pres=(13926,), bandwidths=(.97,))
        with tempfile.TemporaryDirectory(dir=self.temporary_root) as temporary:
            with self.assertRaises(ValueError):
                encode(reference, 2, ModelReceiver(), output=Path(temporary))


if __name__ == '__main__':
    unittest.main()

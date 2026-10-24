"""Exact Q5 transport, bounded failures and retained AVR memory accounting."""
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('q5_stream', ROOT/'tools/pack-q5-stream.py')
stream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stream)


class Q5StreamTests(unittest.TestCase):
    def test_all_field_codecs_restore_signed_differences_and_zero_runs(self):
        rng = random.Random(504)
        values = [0, 0, 0, 31, 0, 63, 63, 1]+[rng.randrange(64) for _ in range(80)]
        for method in range(5):
            for parameter in (range(8) if method else (6,)):
                bits = stream.Bits()
                tokens = [stream.token(values, i, method) for i in range(len(values))]
                for value in tokens:
                    stream.write_token(bits, value, method, parameter)
                reader = stream.Bits(bits.data)
                self.assertEqual([stream.read_token(reader, method, parameter) for _ in values], tokens)
                self.assertEqual(reader.position, bits.position)

    def test_full_phrase_round_trip_preserves_the_measured_pcm(self):
        spec = importlib.util.spec_from_file_location('q5_stream_fit', ROOT/'tools/fit-mixed-lattice.py')
        fit = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = fit
        spec.loader.exec_module(fit)
        model = json.loads(stream.MODEL.read_text(encoding='utf-8'))
        for allowed in ((0,), (0, 1, 2), (0, 1, 2, 3, 4)):
            packed, _ = stream.pack(model, allowed)
            restored = stream.unpack(packed)
            self.assertEqual(stream.columns(restored), stream.columns(model))
            self.assertEqual(restored['wave_taps'], model['wave_taps'])
        scratch = ROOT/'build/q5-stream-tests'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            path = Path(directory)/'restored.json'
            path.write_text(json.dumps(restored), encoding='utf-8')
            state, bits, state_bits, mode, *_ = fit.load(path)
            pcm, counts = fit.render(state, bits, state_bits, mode)
        self.assertEqual(len(pcm), 22272)
        self.assertFalse(counts.any())
        self.assertEqual(hashlib.sha256(pcm.tobytes()).hexdigest(),
                         '19286c14df85e5a88e074b519646615bf549df1ca7547c52a357f41d5f2dbc4d')

    def test_malformed_stream_and_unsupported_precision_are_rejected(self):
        model = json.loads(stream.MODEL.read_text(encoding='utf-8'))
        packed, _ = stream.pack(model)
        for bad in (packed[:35], packed[:-1], packed+b'\0', b'BAD!'+packed[4:]):
            with self.assertRaises(ValueError):
                stream.unpack(bad)
        bad = bytearray(packed)
        bad[9] = 0xf0
        with self.assertRaisesRegex(ValueError, 'descriptor'):
            stream.unpack(bad)
        model['state_bits'] = 4
        with self.assertRaisesRegex(ValueError, 'head-Q5'):
            stream.pack(model)

    def test_retained_budget_counts_data_and_arithmetic_without_claiming_firmware(self):
        report = json.loads((ROOT/'ATtiny13A/Sound/research/q4-pulse-shapes/head5/flash-budget.json').read_text(encoding='utf-8'))
        model = json.loads(stream.MODEL.read_text(encoding='utf-8'))
        self.assertEqual(report['modelSha256'], hashlib.sha256(stream.MODEL.read_bytes()).hexdigest())
        self.assertEqual(report['sourceSha256NormalizedLf'],
                         hashlib.sha256(Path(stream.__file__).read_text(encoding='utf-8').encode()).hexdigest())
        for row, allowed in zip(report['candidates'], ((0,), (0, 1, 2), (0, 1, 2, 3, 4))):
            data, measured = stream.pack(model, allowed)
            self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
            self.assertEqual(measured['dataBytes'], row['dataBytes'])
            self.assertEqual(row['optimisticFlashFloorBytes'], len(data)+report['arithmeticBytes']-64)
        self.assertEqual(report['optimisticFlashFloorBytes'], 1218)
        self.assertFalse(report['flashQualified'])
        self.assertFalse(report['fullFirmwareImplemented'])


if __name__ == '__main__':
    unittest.main()

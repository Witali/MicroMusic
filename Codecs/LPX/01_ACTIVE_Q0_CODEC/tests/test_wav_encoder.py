"""New-input regression: no legacy LPX/LSF/trace or private recordings needed."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import warnings
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tests')]
from batch_decoder import BatchSession
from fuzzer import gen
from l3av_parse import unpack
from lpx4 import encode, decode
from q0_model import decode_pcm16
from wav_lpc import analyze, lpc_to_lsf
from wav_to_lpx4 import encode_segment, run


class WavEncoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = BatchSession('batch')
        cls.decoder = cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.session.__exit__(None, None, None)

    def test_q0_arithmetic_against_native_random_streams(self):
        for seed in range(16):
            blob = encode(unpack(gen(20261025 + seed)))[0]
            n = int.from_bytes(blob[8:12], 'little')
            self.assertTrue(np.array_equal(decode_pcm16(blob), self.decoder.decode_one_s16(blob, n)), seed)
        blob = (ROOT / 'examples/SYNTHETIC_CELP_BUDGET/synthetic_celp_budget.l4hy').read_bytes()
        self.assertTrue(np.array_equal(decode_pcm16(blob), self.decoder.decode_one_s16(blob, 3200)))

    def test_lsf_allpass_and_stable_silence(self):
        np.testing.assert_allclose(lpc_to_lsf(np.r_[1., np.zeros(10)]), np.arange(1, 11) / 11, atol=1e-8)
        vectors, report = analyze(np.zeros(321, dtype=np.int16))
        self.assertEqual(len(vectors), 3)
        self.assertTrue(np.all(np.diff(vectors, axis=1) >= 12))
        blob, pcm, report = encode_segment(np.zeros(321, np.int16), self.decoder, lambdas=(0.,))
        self.assertEqual(pcm.tolist(), [0] * 321)
        self.assertEqual(len(decode(blob)[2]), 321)
        self.assertTrue(all(b['bits']==0 for b in decode(blob)[1]))
        self.assertEqual(report['selected']['zero_blocks_repacked'],5)

    def test_wav_only_partial_tail_and_byte_cap(self):
        t = np.arange(1601) / 8000
        ref = np.rint(32768 * (.25 * np.sin(2 * np.pi * 213 * t) + .08 * np.sin(2 * np.pi * 871 * t))).astype(np.int16)
        blob, pcm, report = encode_segment(ref, self.decoder, lambdas=(0., .001, .02), kind='music')
        self.assertGreater(report['selected']['quality']['ser_db'], 30)
        self.assertIsNone(report['selected']['quality']['stoi'])
        self.assertEqual(len(decode(blob)[2]), len(ref))
        budget = min(r['bytes'] for r in report['candidates'])
        capped, _, r = encode_segment(ref, self.decoder, max_bytes=budget, lambdas=(0., .001, .02), kind='music')
        self.assertLessEqual(len(capped), budget)
        self.assertEqual(capped, encode_segment(ref, self.decoder, max_bytes=budget,
            lambdas=(0., .001, .02), kind='music')[0])

    def test_resample_downmix_segment_manifest_and_failure_atomicity(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            t = np.arange(1603 * 3) / 24000
            x = .2 * np.sin(2 * np.pi * 317 * t)
            sf.write(p / 'input.wav', np.column_stack((x, x / 2)), 24000, subtype='PCM_16')
            report = run(p / 'input.wav', p / 'output', segment_samples=640, kind='music', lambdas=(0.,))
            self.assertEqual(report['samples'], 1603)
            self.assertEqual([s['samples'] for s in report['segments']], [640, 640, 323])
            self.assertEqual([s['offset_samples'] for s in report['segments']], [0, 640, 1280])
            parts = []
            for item in report['segments']:
                blob = (p / 'output' / item['file']).read_bytes()
                self.assertEqual(hashlib.sha256(blob).hexdigest(), item['sha256'])
                self.assertLessEqual(len(blob), 65535)
                parts.append(self.decoder.decode_one_s16(blob, item['samples']))
            preview, sr = sf.read(p / 'output/decoded.wav', dtype='int16')
            np.testing.assert_array_equal(preview, np.concatenate(parts))
            with self.assertRaises(ValueError):
                run(p / 'input.wav', p / 'failed', max_bytes=32, lambdas=(0.,))
            self.assertFalse((p / 'failed').exists())

    def test_invalid_parameters(self):
        ref = np.ones(160, np.int16)
        for opts in ({'lambdas': ()}, {'lambdas': (float('nan'),)}, {'pre': -1},
                     {'max_bytes': 65536}, {'kind': 'other'}):
            with self.subTest(opts=opts), self.assertRaises(ValueError):
                encode_segment(ref, self.decoder, **opts)

    def test_quantized_filter_instability_uses_a_stable_restart(self):
        source = ROOT.parent / '05_BENCHMARKS/INDEPENDENT_SPEECH_AND_MUSIC_2026-10-24/references/synthetic_music_12s.wav'
        from wav_lpc import load_wav
        ref = load_wav(source)[0][:24000]
        blob, pcm, report = encode_segment(ref, self.decoder, max_bytes=8018, kind='music',
            lambdas=(0., .0002, .001, .005, .02, .1, .5, 10.))
        legacy = next(a for a in report['analysis'] if a['profile'] == 'legacy')
        self.assertGreater(legacy['unstable_subframes'], 0)
        chosen = next(a for a in report['analysis'] if a['profile'] == report['selected']['profile'])
        self.assertEqual(chosen['unstable_subframes'], 0)
        self.assertGreater(report['selected']['quality']['ser_db'], 8)
        self.assertLessEqual(len(blob), 8018)


if __name__ == '__main__':
    unittest.main()

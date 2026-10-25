"""A paired change defeats greedy search but fits the original bit budget."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from batch_decoder import BatchSession
from beam_excitation_pcm16 import optimize
from lpx4 import BitWriter
from rice_v4_reference import write_scale
from refine_excitation_pcm16 import scan_tokens
from refine_lsf_pcm16 import patch_bits
from optimize_q0 import optimize as joint_optimize


def raw_fixture(scale=210, samples=80):
    header = struct.pack('<4sBBHIHHHH', b'L4HY', 2, 3, 8000, samples, 15000, 0, 160, 80)
    w = BitWriter()
    oldscale = 0
    for frame in range(0, samples, 160):
        if frame:
            w.put(0, 1)
        else:
            w.put(1, 1);w.put(0, 1)
            for v in [round(1023 * i / 11) for i in range(1, 11)]:
                w.put(v & 255, 8);w.put(v >> 8, 2)
        for block in range(frame, min(frame + 160, samples), 80):
            w.put(3, 3);write_scale(w, oldscale, scale);oldscale = scale
            for sub in range(block, min(block + 80, samples), 40):
                w.put(0, 2);w.put(0, 3)
                for _ in range(min(40, samples - sub)):w.put(4, 3)
    w.aligned()
    return header + w.get()


class BeamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = BatchSession('batch')
        cls.decoder = cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.session.__exit__(None, None, None)

    def test_delayed_pair_escapes_greedy_and_keeps_bytes(self):
        blob = raw_fixture()
        tokens = {t.sample: t for t in scan_tokens(blob)}
        target = patch_bits(blob, tokens[10].offset, 3, 5)
        target = patch_bits(target, tokens[11].offset, 3, 3)
        ref = self.decoder.decode_one_s16(target, 80)
        greedy, gp, gr = optimize(blob, ref, self.decoder, beam_width=1, max_trials=80,
            max_windows=1, tokens_per_window=2, max_delta=1, kind='music')
        beam, bp, br = optimize(blob, ref, self.decoder, beam_width=4, max_trials=80,
            max_windows=1, tokens_per_window=2, max_delta=1, kind='music')
        self.assertGreater(np.sum((gp.astype(np.int64) - ref) ** 2), 0)
        self.assertLess(np.sum((bp.astype(np.int64) - ref) ** 2),
                        np.sum((gp.astype(np.int64) - ref) ** 2))
        self.assertEqual(greedy, blob)
        self.assertEqual(len(blob), len(beam))
        self.assertLessEqual(br['trials'], 80)
        self.assertTrue(br['codeword_structure_unchanged'])

    def test_perfect_reference_and_zero_budget_are_unchanged(self):
        blob = raw_fixture()
        ref = self.decoder.decode_one_s16(blob, 80)
        for width in (1, 4, 8, 16):
            out, pcm, r = optimize(blob, ref, self.decoder, beam_width=width, kind='music')
            self.assertEqual(out, blob)
            self.assertEqual(r['trials'], 0)
        ref = ref.copy();ref[10] = 100
        out, _, r = optimize(blob, ref, self.decoder, max_trials=0, kind='music')
        self.assertEqual(out, blob)
        self.assertEqual(r['trials'], 0)

    def test_budget_and_deterministic_output(self):
        blob = raw_fixture()
        ref = np.zeros(80, np.int16);ref[10:14] = [200, -100, 60, -20]
        a, p, r = optimize(blob, ref, self.decoder, beam_width=8, window=40, max_trials=13, kind='music')
        b, q, s = optimize(blob, ref, self.decoder, beam_width=8, window=40, max_trials=13, kind='music')
        self.assertEqual(a, b)
        self.assertLessEqual(r['trials'], 13)
        self.assertGreaterEqual(r['after']['ser_db'], r['before']['ser_db'])

    def test_alternating_pipeline_preserves_perfect_reference_and_native_cost(self):
        blob = raw_fixture(samples=4800)
        ref = self.decoder.decode_one_s16(blob, 4800)
        out, pcm, report = joint_optimize(blob, ref, self.decoder, rounds=2,
            lsf_trials=12, beam_trials=16, header_trials=8)
        self.assertEqual(out, blob)
        np.testing.assert_array_equal(pcm, ref)
        self.assertEqual(report['decoder_cost_before'], report['decoder_cost_after'])
        self.assertTrue(all(s['round'] == 1 for s in report['stages']))


if __name__ == '__main__':
    unittest.main()

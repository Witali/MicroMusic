"""Encoder contracts: audible objective, hard flash budget and exact resume."""
import json
import random
import sys
import unittest
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ATtiny13A/Sound/codec'))
from auto_encoder import EncoderSearch, SpectralObjective, propose, validate_stream, MAX_STREAM_BYTES
from hq4_timbre import decode
from hq4_core import pack_stream


class EncoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames = np.array([[30 + i % 5, 3 + i % 3, 136, 136, 136, 136] for i in range(36)], np.uint8)
        cls.durations = np.full(36, 256, np.uint16)
        cls.reference = (decode(cls.frames, cls.durations).astype(float) - 128) / 128
        cls.objective = SpectralObjective(cls.reference)

    def test_spectral_match_ignores_gain_and_penalizes_missing_detail(self):
        base = self.objective.spectrum(self.reference)
        scaled = self.objective.spectrum(self.reference * .37)
        smooth = np.convolve(self.reference, np.ones(9) / 9, mode='same')
        self.assertLess(base['loss'], 1e-7)
        self.assertLess(scaled['loss'], 1e-7)
        self.assertGreater(self.objective.spectrum(smooth)['loss'], .05)

    def test_resume_matches_uninterrupted_search_and_elite_never_degrades(self):
        kwargs = dict(floor=.8, seed=812, restart_every=30, temperature=.01)
        whole = EncoderSearch(self.objective, self.frames, self.durations, **kwargs)
        split = EncoderSearch(self.objective, self.frames, self.durations, **kwargs)
        for _ in range(100):
            whole.step()
        for _ in range(37):
            split.step()
        checkpoint = json.loads(json.dumps(split.checkpoint()))
        resumed = EncoderSearch(self.objective, self.frames, self.durations, checkpoint=checkpoint, **kwargs)
        for _ in range(63):
            resumed.step()
        self.assertEqual(whole.checkpoint(), resumed.checkpoint())
        self.assertLessEqual(whole.best[2]['loss'], whole.initial['loss'])
        self.assertGreaterEqual(whole.best[2]['stoi'], .8)
        changed = dict(checkpoint); changed['config'] = dict(checkpoint['config'], floor=.81)
        with self.assertRaisesRegex(ValueError, 'configuration'):
            EncoderSearch(self.objective, self.frames, self.durations, checkpoint=changed, **kwargs)

    def test_mutations_preserve_duration_and_budget_is_checked(self):
        f, d = self.frames, self.durations
        rng = random.Random(9)
        split_seen = merge_seen = boundary_seen = False
        for _ in range(2000):
            nf, nd = propose(f, d, rng)
            self.assertEqual(int(nd.sum()), int(d.sum()))
            self.assertTrue(all(int(v) in (64, 128, 192, 256) for v in nd))
            split_seen |= len(nf) > len(f); merge_seen |= len(nf) < len(f)
            boundary_seen |= len(nd) == len(d) and not np.array_equal(nd, d)
            if len(pack_stream(nf, nd)) <= MAX_STREAM_BYTES:
                validate_stream(nf, nd, len(self.reference)); f, d = nf, nd
        self.assertTrue(split_seen and merge_seen and boundary_seen)
        oversized = np.tile(self.frames, (30, 1)); lengths = np.tile(self.durations, 30)
        with self.assertRaisesRegex(ValueError, '1024'):
            validate_stream(oversized, lengths, int(lengths.sum()))


if __name__ == '__main__':
    unittest.main()

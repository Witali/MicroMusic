"""HQ4 quality guards, exact resumption and structural duration/Flash contracts."""
import copy
import json
from pathlib import Path
import random
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_speech_search import (SpeechObjective, SpeechSearch, proposal, validate,
                               MAX_STREAM_BYTES, deterministic_estoi)
from hq4_core import pack_stream, unpack_stream
from model import decode
from speech_spectrum import PersistentSpectrumObjective


class SpeechSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = np.array([[30+i%5, 3+i%3, 136, 136, 136, 136] for i in range(36)], np.uint8)
        cls.d = np.full(36, 256, np.uint16)
        cls.reference = (decode(cls.f, cls.d, 0).astype(float)-128)/128
        bands = PersistentSpectrumObjective(cls.reference)
        cls.objective = SpeechObjective(cls.reference, band_objective=bands)

    def test_exact_hq4_self_match(self):
        score = self.objective.evaluate(self.f, self.d)
        self.assertLess(score['loss'], 1e-7)
        self.assertGreater(score['stoi'], .9999)
        self.assertGreater(score['estoi'], .9999)
        payload = validate(self.f, self.d, len(self.reference))
        f, d = unpack_stream(payload)
        np.testing.assert_array_equal(decode(f, d, 0), decode(self.f, self.d, 0))

    def test_each_export_guard_is_enforced(self):
        search = SpeechSearch(self.objective, self.f, self.d)
        self.assertTrue(search.feasible(search.initial))
        for key, change in (('stoi', -.001), ('estoi', -.001),
                            ('spectral_loss', .001), ('log_spectral_error', .001)):
            bad = dict(search.initial)
            bad[key] += change
            self.assertFalse(search.feasible(bad), key)
        bad = dict(search.initial, estoi=float('nan'))
        self.assertFalse(search.feasible(bad))

    def test_estoi_is_deterministic_and_preserves_callers_rng(self):
        np.random.seed(911)
        saved = np.random.get_state()
        value = deterministic_estoi(self.reference, self.reference*.7, 7500)
        after = np.random.get_state()
        self.assertEqual(saved[0], after[0])
        np.testing.assert_array_equal(saved[1], after[1])
        self.assertEqual(saved[2:], after[2:])
        np.random.standard_normal(123)
        self.assertEqual(value, deterministic_estoi(self.reference, self.reference*.7, 7500))

    def test_exact_resume_and_tampered_checkpoint_rejection(self):
        kwargs = dict(seed=130, restart_every=30, temperature=.02)
        whole = SpeechSearch(self.objective, self.f, self.d, **kwargs)
        split = SpeechSearch(self.objective, self.f, self.d, **kwargs)
        for _ in range(75):
            whole.step()
        for _ in range(29):
            split.step()
        saved = json.loads(json.dumps(split.checkpoint()))
        resumed = SpeechSearch(self.objective, self.f, self.d, checkpoint=saved, **kwargs)
        for _ in range(46):
            resumed.step()
        self.assertEqual(whole.checkpoint(), resumed.checkpoint())
        damaged = copy.deepcopy(saved)
        damaged['best']['score']['estoi'] -= .001
        with self.assertRaisesRegex(ValueError, 'metrics'):
            SpeechSearch(self.objective, self.f, self.d, checkpoint=damaged, **kwargs)
        damaged = copy.deepcopy(saved)
        damaged['config']['stoi_floor'] -= .01
        with self.assertRaisesRegex(ValueError, 'configuration'):
            SpeechSearch(self.objective, self.f, self.d, checkpoint=damaged, **kwargs)
        damaged = copy.deepcopy(saved)
        damaged['current']['score']['loss'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'metrics'):
            SpeechSearch(self.objective, self.f, self.d, checkpoint=damaged, **kwargs)

    def test_custom_start_cannot_weaken_frozen_control(self):
        score = self.objective.evaluate(self.f, self.d)
        better_control = dict(score, stoi=score['stoi']+.001)
        with self.assertRaisesRegex(ValueError, 'frozen HQ4 baseline'):
            SpeechSearch(self.objective, self.f, self.d, baseline_score=better_control)

    def test_full_recording_and_budget_survive_joint_proposals(self):
        rng = random.Random(14)
        f, d = self.f.copy(), self.d.copy()
        structural = False
        for _ in range(1000):
            nf, nd = proposal(f, d, rng)
            self.assertEqual(int(nd.sum()), len(self.reference))
            self.assertTrue(all(int(n) in (64, 128, 192, 256) for n in nd))
            structural |= len(nf) != len(f) or not np.array_equal(nd, d)
            if len(pack_stream(nf, nd)) <= MAX_STREAM_BYTES:
                validate(nf, nd, len(self.reference))
                f, d = nf, nd
        self.assertTrue(structural)
        with self.assertRaisesRegex(ValueError, '1024'):
            validate(np.tile(self.f, (30, 1)), np.tile(self.d, 30), len(self.reference)*30)
        with self.assertRaisesRegex(ValueError, 'entire recording'):
            validate(self.f, self.d, len(self.reference)-64)


if __name__ == '__main__':
    unittest.main()

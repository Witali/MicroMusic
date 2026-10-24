"""Learned noise format, previous-model equivalence and exact search resume."""
import json
import sys
import unittest
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ATtiny13A/Sound/codec'))
from auto_encoder import SpectralObjective
from joint_period import JointSearch
from period_residual import decode_residual
from colored_period import learn_colored_model, decode_colored, pack_colored, unpack_colored, ColoredSynthesis


class ColoredTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.legacy = json.loads((ROOT / 'ATtiny13A/Sound/research/period-joint/chego/model.json').read_text(encoding='utf-8'))
        cls.legacy['base']['samples'] = 3901
        cls.legacy['base']['frames'] = cls.legacy['base']['frames'][:61]
        cls.legacy['gains'] = cls.legacy['gains'][:61]
        cls.reference = decode_residual(cls.legacy)
        cls.model = learn_colored_model(cls.legacy, cls.reference)

    def test_inheritance_bitstream_and_random_color_cache(self):
        self.assertTrue(np.allclose(decode_colored(self.model), self.reference, atol=1e-12, rtol=0))
        model = json.loads(json.dumps(self.model))
        model['gains'] = np.random.default_rng(9).integers(0, 64, 61).tolist()
        payload = pack_colored(model)
        self.assertEqual(len(payload), 18+266+2*61+(6*61+7)//8)
        restored = unpack_colored(payload)
        self.assertEqual(model, restored)
        self.assertTrue(np.array_equal(decode_colored(model), decode_colored(restored)))
        cache = ColoredSynthesis(model)
        self.assertTrue(np.allclose(cache.render(np.array(model['base']['frames']), np.array(model['gains'])), decode_colored(model), atol=1e-12, rtol=0))
        with self.assertRaises(ValueError):
            unpack_colored(payload[:-1])

    def test_resume_is_exact_in_new_color_search(self):
        kwargs = dict(cache_factory=ColoredSynthesis, restart_every=20, seed=101)
        objective = SpectralObjective(self.reference)
        whole = JointSearch(self.model, objective, **kwargs)
        split = JointSearch(self.model, objective, **kwargs)
        for _ in range(50):
            whole.step()
        for _ in range(21):
            split.step()
        resumed = JointSearch(self.model, objective, checkpoint=json.loads(json.dumps(split.checkpoint())), **kwargs)
        for _ in range(29):
            resumed.step()
        self.assertEqual(whole.checkpoint(), resumed.checkpoint())
        self.assertTrue(resumed.feasible(resumed.best[3]))
        self.assertEqual(len(pack_colored(resumed.export())), len(pack_colored(self.model)))


if __name__ == '__main__':
    unittest.main()

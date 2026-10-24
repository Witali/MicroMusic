"""Joint cache, fixed-budget elites and exact checkpoint continuation."""
import json
import sys
import unittest
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ATtiny13A/Sound/codec'))
from auto_encoder import SpectralObjective
from joint_period import JointSearch, JointSynthesis
from period_residual import decode_residual, pack_residual


class JointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'ATtiny13A/Sound/research/period-wave/chego/residual-model.json'
        cls.model = json.loads(path.read_text(encoding='utf-8'))
        cls.reference = decode_residual(cls.model)
        cls.objective = SpectralObjective(cls.reference)

    def test_cached_joint_synthesis_matches_independent_decoder(self):
        cache = JointSynthesis(self.model)
        rng = np.random.default_rng(31)
        frames = np.array(self.model['base']['frames'])
        gains = rng.integers(0, 16, len(frames))
        frames[:, 1] = rng.integers(0, 16, len(frames))
        frames[:, 2] = rng.integers(0, 8, len(frames))
        frames[:, 3] = rng.integers(0, 2, len(frames))
        self.assertTrue(np.allclose(cache.render(frames, gains), decode_residual(cache.model(frames, gains)), atol=1e-12, rtol=0))

    def test_checkpoint_and_feasible_elite_preserve_exact_continuation(self):
        kwargs = dict(seed=43, restart_every=20)
        whole = JointSearch(self.model, self.objective, **kwargs)
        split = JointSearch(self.model, self.objective, **kwargs)
        for _ in range(55):
            whole.step()
        for _ in range(23):
            split.step()
        saved = json.loads(json.dumps(split.checkpoint()))
        resumed = JointSearch(self.model, self.objective, checkpoint=saved, **kwargs)
        for _ in range(32):
            resumed.step()
        self.assertEqual(whole.checkpoint(), resumed.checkpoint())
        self.assertTrue(resumed.feasible(resumed.best[3]))
        self.assertEqual(len(pack_residual(resumed.export())), len(pack_residual(self.model)))
        self.assertLessEqual(resumed.energy(resumed.best[3]), resumed.energy(resumed.initial))
        with self.assertRaisesRegex(ValueError, 'configuration'):
            JointSearch(self.model, self.objective, checkpoint=saved, stoi_weight=7., **kwargs)


if __name__ == '__main__':
    unittest.main()

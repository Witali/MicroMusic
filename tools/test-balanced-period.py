"""Spectral selection uses a hard intelligibility floor, not a scalar STOI reward."""
import json
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ATtiny13A/Sound/codec'))
from auto_encoder import SpectralObjective
from balanced_period import SpectralFrameSearch, SpectralBookSearch
from colored_period import decode_colored, ColoredSynthesis


class BalancedTests(unittest.TestCase):
    def test_both_searches_minimize_error_and_resume_exactly(self):
        model = json.loads((ROOT / 'ATtiny13A/Sound/research/period-book/chego/model.json').read_text(encoding='utf-8'))
        objective = SpectralObjective(decode_colored(model))
        for cls in (SpectralFrameSearch, SpectralBookSearch):
            kwargs = dict(seed=249, stoi_floor=.5, restart_every=15)
            if cls is SpectralFrameSearch:
                kwargs['cache_factory'] = ColoredSynthesis
            whole, split = cls(model, objective, **kwargs), cls(model, objective, **kwargs)
            low_error = dict(whole.initial, loss=.2, stoi=.6)
            high_stoi = dict(whole.initial, loss=.3, stoi=.99)
            self.assertLess(whole.energy(low_error), whole.energy(high_stoi))
            self.assertFalse(whole.feasible(dict(low_error, stoi=.49)))
            for _ in range(30):
                whole.step()
            for _ in range(13):
                split.step()
            resumed = cls(model, objective, checkpoint=json.loads(json.dumps(split.checkpoint())), **kwargs)
            for _ in range(17):
                resumed.step()
            self.assertEqual(whole.checkpoint(), resumed.checkpoint())
            self.assertLessEqual(resumed.best[3]['loss'], resumed.initial['loss'])
            self.assertTrue(resumed.feasible(resumed.best[3]))


if __name__ == '__main__':
    unittest.main()

"""Sparse derivatives must match a real decoder after signed dictionary edits."""
import json
import sys
import unittest
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ATtiny13A/Sound/codec'))
from colored_period import learn_colored_model, decode_colored, pack_colored
from period_residual import decode_residual
from period_book_search import BookSynthesis, BookSearch
from auto_encoder import SpectralObjective


class BookTests(unittest.TestCase):
    def test_derivatives_balanced_edits_and_exact_resume(self):
        legacy = json.loads((ROOT / 'ATtiny13A/Sound/research/period-joint/chego/model.json').read_text(encoding='utf-8'))
        legacy['base']['samples'] = 3901
        legacy['base']['frames'] = legacy['base']['frames'][:61]
        legacy['gains'] = legacy['gains'][:61]
        reference = decode_residual(legacy)
        model = learn_colored_model(legacy, reference)
        cache = BookSynthesis(model)
        rng = np.random.default_rng(42)
        book = rng.integers(-7, 8, (16, 32))
        self.assertTrue(np.allclose(cache.render(book), decode_colored(cache.model(book, None)), atol=1e-12, rtol=0))
        objective = SpectralObjective(reference)
        kwargs = dict(seed=141, restart_every=15)
        whole, split = BookSearch(model, objective, **kwargs), BookSearch(model, objective, **kwargs)
        for _ in range(50):
            whole.step()
        for _ in range(17):
            split.step()
        resumed = BookSearch(model, objective, checkpoint=json.loads(json.dumps(split.checkpoint())), **kwargs)
        for _ in range(33):
            resumed.step()
        self.assertEqual(whole.checkpoint(), resumed.checkpoint())
        self.assertTrue(np.array_equal(resumed.current[0].sum(axis=1), np.array(model['base']['codebook']).sum(axis=1)))
        self.assertEqual(len(pack_colored(resumed.export())), len(pack_colored(model)))


if __name__ == '__main__':
    unittest.main()

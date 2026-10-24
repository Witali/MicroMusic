"""Compact parsing keeps all audible parameters and phase through silent frames."""
import json
import sys
import unittest
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ATtiny13A/Sound/codec'))
from compact_period import pack_compact, unpack_compact
from colored_period import learn_colored_model, decode_colored
from period_residual import decode_residual


class CompactTests(unittest.TestCase):
    def test_random_pitch_branches_zero_fields_and_noise_modes(self):
        rng = np.random.default_rng(241)
        legacy = json.loads((ROOT / 'ATtiny13A/Sound/research/period-joint/chego/model.json').read_text(encoding='utf-8'))
        colored = learn_colored_model(legacy, decode_residual(legacy))
        for model, decoder in ((legacy, decode_residual), (colored, decode_colored)):
            model = json.loads(json.dumps(model))
            count = len(model['base']['frames'])
            edge_deltas = [127, 0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6]
            for i, frame in enumerate(model['base']['frames']):
                previous = model['base']['frames'][i-1][0] if i else 0
                delta = edge_deltas[i] if i < len(edge_deltas) else int(rng.choice([0, 1, -1, 3, -4, 20, -30]))
                frame[:] = [int(np.clip(previous+delta, 0, 255)),
                            int(rng.integers(16)), int(rng.integers(8)), int(rng.integers(2))]
                model['gains'][i] = int(rng.integers(64 if decoder == decode_colored else 16))
            payload = pack_compact(model)
            restored = unpack_compact(payload)
            self.assertTrue(np.array_equal(decoder(model), decoder(restored)))
            self.assertEqual([f[0] for f in model['base']['frames']], [f[0] for f in restored['base']['frames']])
            self.assertEqual(pack_compact(restored), payload)
            for bad in (payload[:-1], payload+b'\0', b'BAD!'+payload[4:]):
                with self.assertRaises(ValueError):
                    unpack_compact(bad)


if __name__ == '__main__':
    unittest.main()

"""Exact target scoring, deterministic resume and safe integer proposals."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

import numpy as np
from pystoi import stoi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from auto_encoder import SpectralObjective
from colored_period import decode_colored
from fixed_period import decode_fixed, from_colored, pack_fixed, unpack_fixed
from fixed_search import FixedSearch, decoder_constraints


class FixedSpeechTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        colored = json.loads((ROOT/'ATtiny13A/Sound/research/period-balanced/chego/model.json').read_text(encoding='utf-8'))
        colored['base']['samples'] = 3901
        colored['base']['frames'] = colored['base']['frames'][:61]
        colored['gains'] = colored['gains'][:61]
        cls.model = from_colored(colored)
        cls.model['dc_block_shift'] = 7
        cls.objective = SpectralObjective(decode_colored(colored))

    def test_score_uses_exact_dac_output_including_dc(self):
        search = FixedSearch(self.model, self.objective)
        pcm = (decode_fixed(self.model).astype(float)-128)/128
        expected = dict(**self.objective.spectrum(pcm), stoi=float(stoi(self.objective.reference, pcm, 7500)))
        for key, value in expected.items():
            self.assertEqual(search.initial[key], value)
        self.assertFalse(np.array_equal(decode_fixed(self.model), decode_fixed(dict(self.model, dc_block_shift=0))))
        clipped = dict(search.initial, pre_dc_clips=1)
        self.assertFalse(search.feasible(clipped))

    def test_checkpoint_continuation_matches_uninterrupted_search(self):
        kwargs = dict(seed=4321, restart_every=25)
        whole = FixedSearch(self.model, self.objective, **kwargs)
        split = FixedSearch(self.model, self.objective, **kwargs)
        for _ in range(90):
            whole.step()
        for _ in range(37):
            split.step()
        checkpoint = json.loads(json.dumps(split.checkpoint()))
        resumed = FixedSearch(self.model, self.objective, checkpoint=checkpoint, **kwargs)
        for _ in range(53):
            resumed.step()
        self.assertEqual(whole.checkpoint(), resumed.checkpoint())
        elite = resumed.export()
        self.assertTrue(resumed.feasible(resumed.best[2]))
        self.assertLessEqual(len(pack_fixed(elite)), len(pack_fixed(self.model)))
        self.assertTrue(np.array_equal(decode_fixed(elite), decode_fixed(unpack_fixed(pack_fixed(elite)))))
        bad = deepcopy(checkpoint)
        bad['best']['pcm_u8'] = bad['current']['pcm_u8'][:-4]
        with self.assertRaisesRegex(ValueError, 'PCM or score'):
            FixedSearch(self.model, self.objective, checkpoint=bad, **kwargs)

    def test_proposals_preserve_fir_and_waveform_dc_sums(self):
        search = FixedSearch(self.model, self.objective, seed=10)
        model = deepcopy(self.model)
        sums = np.sum(model['codebook'], axis=1)
        observed = set()
        for _ in range(500):
            candidate = search.propose(model)
            observed.update(key for key in model if candidate[key] != model[key])
            self.assertEqual(candidate['noise_filters'], self.model['noise_filters'])
            self.assertTrue(np.array_equal(np.sum(candidate['codebook'], axis=1), sums))
            model = candidate
        self.assertTrue({'frames', 'codebook', 'initial_phase_u16', 'dc_block_shift'} <= observed)

    def test_spectral_polish_retains_floor_without_rewarding_excess_stoi(self):
        search = FixedSearch(self.model, self.objective, objective_kind='spectral', seed=3,
                             stoi_floor=.8, spectral_ceiling=1.)
        first = dict(search.initial, stoi=.85)
        second = dict(search.initial, stoi=.95)
        self.assertEqual(search.energy(first), search.energy(second))
        self.assertGreater(search.energy(dict(first, stoi=.79)), search.energy(first))
        for _ in range(40):
            search.step()
        self.assertTrue(search.feasible(search.best[2]))
        self.assertLessEqual(search.best[2]['loss'], search.initial['loss'])

    def test_compact_search_cannot_restore_omitted_decoder_features(self):
        model = deepcopy(self.model)
        for frame in model['frames']:
            if not frame[1] & 128:
                frame[1] &= 143
            frame[2] &= 15
        self.assertEqual(decoder_constraints(model), dict(voiced_only=True, residual_colors=(0,)))
        search = FixedSearch(model, self.objective, voiced_only=True, residual_colors=(0,), seed=14)
        for _ in range(80):
            search.step()
        self.assertTrue(search.compatible(search.current[0]))
        self.assertTrue(search.compatible(search.export()))
        bad = deepcopy(model)
        bad['frames'][0][2] = 17
        self.assertFalse(search.compatible(bad))
        bad = deepcopy(model)
        bad['frames'][0][1] = 16
        self.assertFalse(search.compatible(bad))


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Check audible-word canonicalization and reduced-dictionary search limits."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
spec = importlib.util.spec_from_file_location('train_tiny_speech', ROOT/'tools/train-tiny-speech.py')
tiny = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tiny)
from auto_encoder import SpectralObjective
from fixed_period import decode_fixed, pack_avr_data


def fixture():
    word = [round(5*np.sin(2*np.pi*n/32)) for n in range(32)]
    other = [round(5*np.sin(2*np.pi*n/32)+np.sin(6*np.pi*n/32)) for n in range(32)]
    book = [[0]*32 for _ in range(16)]
    book[6], book[14] = word, other
    frames = [[100, 128 | 7 << 4 | (6 if n % 2 else 14), 0] for n in range(64)]
    frames[0][1] = 15  # An inaudible index must not retain a waveform.
    return dict(schema='period-fixed-v1', sample_rate=7500, samples=4096, hop=64,
                phase_bits=4, initial_phase_u16=0, noise_seed_u16=0xace1,
                noise_filters=[[0]*8 for _ in range(3)], codebook=book, frames=frames)


class TinySpeechTests(unittest.TestCase):
    def test_dense_dictionary_preserves_exact_pcm(self):
        model = fixture()
        before = deepcopy(model)
        reduced = tiny.canonicalize(model)
        self.assertEqual(model, before)
        self.assertEqual(tiny.active_words(reduced), [0, 1])
        self.assertTrue(all(not any(word) for word in reduced['codebook'][2:]))
        np.testing.assert_array_equal(decode_fixed(model), decode_fixed(reduced))
        self.assertLess(len(pack_avr_data(reduced, specialize=True)), len(pack_avr_data(model, specialize=True)))

    def test_exact_merge_and_proposals_respect_dictionary(self):
        model = tiny.canonicalize(fixture())
        reference = (decode_fixed(model).astype(float)-128)/128
        objective = SpectralObjective(reference)
        merged, history = tiny.merge_words(model, objective, 1)
        self.assertEqual(tiny.active_words(merged), [0])
        self.assertEqual(history[0]['evaluated'], 2)
        search = tiny.TinySearch(merged, objective, words=1, stoi_floor=0., spectral_ceiling=1.,
                                 max_peak=.95, max_data_bytes=65535, dc_choices=(0,),
                                 voiced_only=True, residual_colors=(0,))
        for _ in range(400):
            proposal = search.propose(merged)
            self.assertTrue(all(index == 0 for index in tiny.active_words(proposal)))
            self.assertTrue(all(not any(word) for word in proposal['codebook'][1:]))
        invalid = deepcopy(merged)
        invalid['frames'][1][1] |= 1
        self.assertFalse(search.compatible(invalid))


if __name__ == '__main__':
    unittest.main()

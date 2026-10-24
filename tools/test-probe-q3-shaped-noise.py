"""Paired stage gate, initializer validation and noise-mode mutation contracts."""
import importlib.util
from pathlib import Path
import random
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('shaped_probe',ROOT/'tools/probe-q3-shaped-noise.py')
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


def model():
    return dict(schema='hq4-q3-pulsebook-v1',sample_rate=7500,samples=256,tilt_shift=1,
                frames=[[40,3,136,136,136,136]],durations=[256],
                pulsebook=np.zeros((4,16),int).tolist())


class ShapedNoiseProbeTests(unittest.TestCase):
    def test_joint_gate_requires_two_strict_paired_improvements(self):
        control = dict(stoi=.85,spectrogram_loss=.49)
        self.assertFalse(probe.paired_win(control,control))
        self.assertFalse(probe.paired_win(dict(stoi=.86,spectrogram_loss=.50),control))
        self.assertFalse(probe.paired_win(dict(stoi=.84,spectrogram_loss=.48),control))
        self.assertFalse(probe.paired_win(None,control))
        self.assertTrue(probe.paired_win(dict(stoi=.851,spectrogram_loss=.489),control))

    def test_source_conversion_rejects_nonzero_long_tail_and_raw_wrap(self):
        seed = model()
        f,d,c,nearest,_ = probe.import_model(seed)
        self.assertEqual(c.shape,(4,16));self.assertFalse(nearest)
        seed['frames'][0][0] = 260
        with self.assertRaises(ValueError): probe.import_model(seed)
        seed = model();seed['schema'] = probe.BASE32_SCHEMA
        seed['pulsebook'] = np.zeros((4,32),int).tolist()
        probe.import_model(seed)
        seed['pulsebook'][0][31] = 1
        with self.assertRaises(ValueError): probe.import_model(seed)

    def test_mutations_reach_every_color_and_keep_uniform_valid_rows(self):
        f,d,c,nearest,_ = probe.import_model(model())
        state = probe.search.State(f,d,probe.codec.encode_book(c,np.zeros(4,int)),nearest,1)
        rng,seen = random.Random(423107),set()
        for _ in range(200):
            candidate = probe.mutate(state,rng)
            _,modes = probe.codec.decode_book(candidate.book)
            seen.update(map(int,modes))
            self.assertEqual(len(probe.codec.pack_book(candidate.book)),64)
        self.assertEqual(seen,{0,1,2,3})


if __name__ == '__main__':
    unittest.main()

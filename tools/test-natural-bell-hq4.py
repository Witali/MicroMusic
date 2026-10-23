"""Check source-level fitting, immutable event timing and strict gain headroom."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from bell_model import decode_bell, descriptor

spec = importlib.util.spec_from_file_location('natural_bell_builder', ROOT/'tools/build-natural-bell-hq4.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BalanceTests(unittest.TestCase):
    def source(self):
        return dict(prefix_samples=1024, mute_samples=128, decay_blocks=4,
                    partials=[dict(step=5650, phase=123, amplitude=3),
                              dict(step=8480, phase=45000, amplitude=2),
                              dict(step=10130, phase=20000, amplitude=2)])

    def test_recovers_known_level_without_changing_frequency_phase_or_timing(self):
        source = self.source()
        snapshot = copy.deepcopy(source)
        desired = self.source()
        for partial, amplitude in zip(desired['partials'], (6, 4, 3)):
            partial['amplitude'] = amplitude
        voice = np.rint(128+25*np.sin(np.arange(4096)*2*np.pi*220/7500)).astype(np.uint8)
        reference = np.r_[(decode_bell(desired).astype(float)-128)/128,
                          (voice.astype(float)-128)/128]
        result = module.balance_bell(source, reference, voice)
        self.assertEqual(source, snapshot)
        self.assertEqual([p['amplitude'] for p in result['partials']], [6, 4, 3])
        self.assertEqual(descriptor(source)[:12], descriptor(result)[:12])
        for key in ('prefix_samples', 'mute_samples', 'decay_blocks'):
            self.assertEqual(source[key], result[key])
        self.assertLessEqual(sum(p['amplitude'] for p in result['partials']), 15)
        pcm = decode_bell(result).astype(np.int16)-128
        self.assertLessEqual(int(np.max(abs(pcm))), 31)
        self.assertLess(result['balanced_bell_objective'], 1e-9)

    def test_silent_voice_is_rejected_instead_of_inventing_a_bell_level(self):
        source = self.source()
        voice = np.full(4096, 128, np.uint8)
        reference = np.r_[(decode_bell(source).astype(float)-128)/128,
                          .2*np.sin(np.arange(4096)*2*np.pi*220/7500)]
        with self.assertRaisesRegex(ValueError, 'silent voice'):
            module.balance_bell(source, reference, voice)


if __name__ == '__main__':
    unittest.main()

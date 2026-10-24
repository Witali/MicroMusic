"""Keep Q3 voice data distinct and the shared bell multiplier bit-exact."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from bell_model import SINE
from hq4_q3 import multiply
from model import mul_q4

spec = importlib.util.spec_from_file_location('q3_bell_builder', ROOT/'tools/build-q3-bell-hq4.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Q3BellTests(unittest.TestCase):
    def model(self):
        return dict(schema='hq4-q3-v1', coefficient_scale=8, coefficient_range=[-7, 7],
                    tilt_shift=1, sample_rate=7500, samples=4096,
                    frames=[[40, 2, 0x88, 0x88, 0x88, 0x88]]*16, durations=[256]*16)

    def test_q4_schema_and_unstable_q3_are_rejected(self):
        q4 = self.model()
        q4['schema'] = 'hq4-natural-timbre-v1'
        with self.assertRaisesRegex(ValueError, 'Q4 data is incompatible'):
            module.candidate_voice(q4)
        unstable = copy.deepcopy(self.model())
        unstable['frames'][0][2] = 0x80
        with self.assertRaisesRegex(ValueError, 'Q3 coefficient -8'):
            module.candidate_voice(unstable)

    def test_bell_extra_shift_exactly_recovers_original_q4_for_every_lut_gain(self):
        for value in SINE:
            for gain in range(1, 8):
                old = ((int(mul_q4(int(value), gain))+128) & 255)-128
                self.assertEqual(int(multiply(int(value), gain)) >> 1, old)

    def test_lower_scalar_loss_cannot_hide_worse_structural_components(self):
        before = dict(spectrogram_loss=.6, fine_log_error=.6, envelope_error=.6,
                      unsupported_energy=.3, missing_energy=.3)
        components = ('fine_log_error', 'envelope_error', 'unsupported_energy', 'missing_energy')
        for component in components:
            after = {key:value*.9 for key, value in before.items()}
            after[component] = before[component]*1.01
            with patch.object(module, 'SpectrogramObjective') as objective, \
                 patch.object(module, 'stoi', return_value=.8), \
                 patch.object(module, 'deterministic_estoi', return_value=.5):
                objective.return_value.evaluate.side_effect = [before, after]
                report = module.quality_gate(np.ones(4096), np.full(4096, 128), np.full(4096, 128))
                self.assertFalse(report['passed'])
                self.assertIn(component, report['failed_guards'])

    def test_candidate_timing_and_metadata_preserve_complete_voice(self):
        frames, durations, pcm, wraps = module.candidate_voice(self.model())
        self.assertEqual(len(pcm), 4096)
        self.assertEqual(int(durations.sum()), 4096)
        self.assertEqual(int(np.sum(wraps)), 0)
        self.assertEqual(frames.shape, (16, 6))
        invalid = self.model()
        invalid['samples'] = 4095
        with self.assertRaisesRegex(ValueError, 'preserve the entire recording'):
            module.candidate_voice(invalid)


if __name__ == '__main__':
    unittest.main()

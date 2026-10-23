"""Tests for independent phase, negative rounding, decay and tonal selection."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from bell_model import SINE, decode_bell, descriptor, fit, validate


class BellTests(unittest.TestCase):
    def model(self):
        return dict(prefix_samples=768, mute_samples=64, decay_blocks=2,
                    partials=[dict(step=5650, phase=65530, amplitude=3),
                              dict(step=8480, phase=200, amplitude=2),
                              dict(step=10130, phase=32800, amplitude=4)])

    def test_scalar_oracle_matches_phase_wrap_signed_rounding_and_decay(self):
        model = self.model()
        phases = [p['phase'] for p in model['partials']]
        expected = []
        for sample in range(model['prefix_samples']):
            if sample < model['mute_samples']:
                expected.append(128)
                continue
            value = 1
            for i, partial in enumerate(model['partials']):
                phases[i] = (phases[i]+partial['step']) & 65535
                value += (int(SINE[phases[i]//1024])*partial['amplitude'])//16
            age = sample-model['mute_samples']
            value //= 2**(age//(model['decay_blocks']*64))
            expected.append(value+128)
        np.testing.assert_array_equal(decode_bell(model), np.array(expected, np.uint8))

    def test_descriptor_order_and_endianness(self):
        model = self.model()
        payload = descriptor(model)
        self.assertEqual(len(payload), 15)
        self.assertEqual(payload[:2], (65530).to_bytes(2, 'little'))
        self.assertEqual(payload[6:8], (5650).to_bytes(2, 'little'))
        self.assertEqual(payload[12:], bytes([3, 2, 4]))

    def test_timing_and_storage_limits(self):
        for key, value in [('prefix_samples', 16384), ('mute_samples', 768),
                           ('mute_samples', 65), ('decay_blocks', 0), ('decay_blocks', 1.5)]:
            model = self.model()
            model[key] = value
            with self.assertRaises(ValueError):
                validate(model)
        for key, value in [('phase', 65536), ('step', 0), ('amplitude', 0), ('amplitude', 1.5)]:
            model = self.model()
            model['partials'][0][key] = value
            with self.assertRaises(ValueError):
                validate(model)

    def test_automatic_fit_keeps_audible_tones_with_phase_drift(self):
        # Long waveform MSE can prefer silence when frequencies drift. The
        # retained spectral fit must preserve independent audible partials.
        n, boundary, mute = 8192, 4096, 512
        reference = np.zeros(n)
        t = np.arange(boundary-mute)/7500
        for frequency, gain in [(640, .16), (970, .12), (1160, .22)]:
            phase = 2*np.pi*(frequency*t+2.0*t*t)
            reference[mute:boundary] += gain*np.sin(phase)*np.exp(-t/.5)
        reference[boundary:] = .3*np.sin(2*np.pi*220*np.arange(n-boundary)/7500)
        voice = np.rint(128+20*np.sin(2*np.pi*220*np.arange(n-boundary)/7500)).astype(np.uint8)
        model = fit(reference, voice, boundary)
        self.assertTrue(all(p['amplitude'] >= 1 for p in model['partials']))
        decoded = decode_bell(model).astype(float)-128
        self.assertGreater(float(np.sqrt(np.mean(decoded**2))), 1.)
        for frequency in (640, 970, 1160):
            self.assertLess(min(abs(f-frequency) for f in model['frequencies_hz']), 6)


if __name__ == '__main__':
    unittest.main()

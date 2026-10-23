"""Adaptive turns, continuous integrated phase, gaps and actual serialization."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from sin_partials import adaptive_knots, curve_errors, encode_log, decode_log, render, log_layout


class PartialSourceTests(unittest.TestCase):
    def model(self, track):
        return dict(schema='sin-partials-pc-v1', sample_rate=7500, samples=129, hop=1,
                    components=3, tracks=[track])

    def test_material_chirp_turn_is_kept_and_looser_threshold_is_nested(self):
        track = dict(id=0, frames=[0, 32, 64, 96, 128],
                     frequency_hz=[100, 150, 200, 150, 100], amplitude=[1, 1, 1, 1, 1], initial_phase=.3)
        tight = adaptive_knots(track, 2., .5)
        self.assertEqual(tight['frames'], [0, 64, 128])
        self.assertEqual(curve_errors(self.model(track), self.model(tight))['maximum_frequency_error_hz'], 0.)
        loose = adaptive_knots(track, 120., 30.)
        self.assertLessEqual(len(loose['frames']), len(tight['frames']))

    def test_phase_is_integrated_across_turn_without_reset(self):
        track = dict(id=0, frames=[0, 64, 128], frequency_hz=[100, 200, 150],
                     amplitude=[1, 1, 1], initial_phase=.3)
        actual = render(self.model(track))
        t = np.arange(129)
        cycles = np.where(t <= 64, 100*t+(100/128)*t*t,
                          150*64+200*(t-64)-(50/128)*(t-64)**2)/7500
        expected = np.cos(.3+2*np.pi*cycles)
        np.testing.assert_allclose(actual, expected, atol=3e-14)

    def test_zero_gap_survives_very_loose_simplification(self):
        track = dict(id=0, frames=[0, 32, 64, 96, 128], frequency_hz=[100]*5,
                     amplitude=[1, 0, 0, 0, 1], initial_phase=0.)
        simplified = adaptive_knots(track, 1000., 1000.)
        pcm = render(self.model(simplified))
        self.assertTrue(np.all(pcm[32:97] == 0))

    def test_log_delta_serialization_roundtrip_and_byte_accounting(self):
        track = dict(id=0, frames=[0, 32, 64, 96, 128],
                     frequency_hz=[100, 150, 200, 150, 100], amplitude=[0, .5, 1, .5, 0], initial_phase=.3)
        model = self.model(track)
        payload = encode_log(model)
        restored = decode_log(payload)
        self.assertEqual(encode_log(restored), payload)
        self.assertLessEqual(curve_errors(model, restored)['maximum_frequency_error_cents'], 18.75+1e-10)
        self.assertLessEqual(curve_errors(model, restored)['maximum_level_error_db'], .5+1e-10)
        layout = log_layout(restored, len(payload))
        self.assertEqual(sum(v for k,v in layout.items() if k != 'total_bytes'), len(payload))
        for cut in (1, len(payload)-1):
            with self.assertRaises(ValueError):
                decode_log(payload[:cut])


if __name__ == '__main__':
    unittest.main()

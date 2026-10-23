"""Known-F0, phase continuity and standalone bitstream contracts."""
import json
import sys
import unittest
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ATtiny13A/Sound/codec'))
from period_wave import (track_pitch, continuous_phase, quantize_phase, encode_model,
                         decode_model, packed_bytes, unpack_bytes, render_periods,
                         FrameSynthesis, refine_frames)


class PeriodWaveTests(unittest.TestCase):
    def test_pitch_on_harmonics_missing_fundamental_and_glide(self):
        sr, samples = 7500, 7500
        for low, high, fundamental in [(130, 130, 1.), (420, 420, 1.), (300, 300, 0.), (200, 500, 1.)]:
            expected = np.linspace(low, high, samples)
            phase = np.cumsum(expected/sr)*2*np.pi
            x = .2*(fundamental*np.cos(phase)+.6*np.cos(2*phase)+.3*np.sin(3*phase))
            centres, f0, _ = track_pitch(x)
            mask = (centres > 500) & (centres < samples-500)
            target = np.interp(centres[mask], np.arange(samples), expected)
            self.assertGreater(np.mean(f0[mask] > 0), .97)
            cents = 1200*abs(np.log2(np.maximum(f0[mask], 1)/target))
            self.assertLess(np.median(cents), 20)
            self.assertLess(np.quantile(cents, .95), 35)

    def test_noise_and_silence_are_unvoiced(self):
        for x in (np.zeros(7500), np.random.default_rng(7).normal(0, .2, 7500)):
            _, f0, _ = track_pitch(x)
            self.assertLess(np.mean(f0 > 0), .05)

    def test_low_noisy_glide_keeps_pitch(self):
        frequency = np.linspace(110, 310, 7500)
        phase = np.cumsum(frequency/7500)*2*np.pi
        audio = .2*np.cos(phase)+.07*np.cos(2*phase)+.08*np.random.default_rng(17).normal(size=len(phase))
        centres, f0, _ = track_pitch(audio)
        mask = (centres > 500) & (centres < len(audio)-500)
        target = np.interp(centres[mask], np.arange(len(audio)), frequency)
        cents = 1200*abs(np.log2(np.maximum(f0[mask], 1)/target))
        self.assertGreater(np.mean(f0[mask] > 0), .97)
        self.assertLess(np.quantile(cents, .95), 40)

    def test_phase_quantization_carries_error_without_frame_resets(self):
        centres = np.arange(60)*64+32
        f0 = np.linspace(210, 510, 60)
        f0[20:25] = 0
        target = continuous_phase(f0, centres, 3840, initial=.123)
        codes, actual = quantize_phase(target, len(target))
        steps = np.diff(actual)
        self.assertTrue(np.all(steps > 0))
        self.assertLess(np.max(abs(actual-target)), .035)
        self.assertTrue(np.allclose(steps, np.repeat(codes.astype(int), 64)[:-1]*32/65536))
        shapes = np.tile(np.cos(2*np.pi*np.arange(32)/32), (60, 1))
        pcm = render_periods(shapes, actual, centres)
        self.assertLess(np.max(abs(pcm-np.cos(2*np.pi*actual))), .006)

    def test_compact_payload_decodes_without_reference(self):
        t = np.arange(3840)/7500
        x = (.15+.1*np.sin(2*np.pi*3*t))*np.cos(2*np.pi*310*t)
        model, _ = encode_model(x, starts=2)
        encoded = packed_bytes(model)
        self.assertEqual(len(encoded), 266+2*60)
        restored = unpack_bytes(encoded)
        self.assertEqual(model, restored)
        self.assertTrue(np.array_equal(decode_model(model), decode_model(json.loads(json.dumps(restored)))))
        for bad in (encoded[:-1], b'XX'+encoded[2:]):
            with self.assertRaises(ValueError):
                unpack_bytes(bad)

    def test_search_cache_matches_decoder_including_noise_and_frame_edges(self):
        t = np.arange(3901)/7500
        model, _ = encode_model(.3*np.cos(2*np.pi*230*t), starts=2)
        rng = np.random.default_rng(5)
        for frame in model['frames']:
            frame[1:] = [int(rng.integers(16)), int(rng.integers(8)), int(rng.integers(2))]
        self.assertTrue(np.allclose(FrameSynthesis(model).render(model['frames']), decode_model(model), atol=1e-12, rtol=0))
        from auto_encoder import SpectralObjective
        refined, stats = refine_frames(model, SpectralObjective(.3*np.cos(2*np.pi*230*t)), proposals=30)
        self.assertLessEqual(stats['final_energy'], stats['initial_energy'])
        self.assertEqual(len(packed_bytes(refined)), len(packed_bytes(model)))


if __name__ == '__main__':
    unittest.main()

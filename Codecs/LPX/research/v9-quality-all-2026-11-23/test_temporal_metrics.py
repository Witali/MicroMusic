"""Meaningful phase/time/rate checks for the independent research evaluator."""
import unittest
import numpy as np
from temporal_metrics import temporal_metrics


class TemporalMetricsTests(unittest.TestCase):
    def test_phase_inversion_keeps_magnitude_and_time_exact(self):
        rng = np.random.default_rng(23)
        source = rng.integers(-1000, 1001, 16000)
        result = temporal_metrics(source, -source, 16000, framewise=False)
        self.assertGreater(sum(b["waveform_residual_power_sum"] for b in result["bands"]), 0)
        self.assertEqual(sum(b["magnitude_residual_power_sum"] for b in result["bands"]), 0)
        self.assertEqual(sum(b["magnitude_change_residual_power_sum"] for b in result["bands"]), 0)
        self.assertGreater(result["source_noisy_unvoiced_frames"], 0)

    def test_moved_burst_cannot_hide_behind_equal_global_energy(self):
        rate = 16000
        source = np.zeros(rate, dtype=np.int16)
        time = np.arange(2048) / rate
        source[2048:4096] = np.rint(10000 * np.sin(2 * np.pi * 6500 * time)).astype(np.int16)
        moved = np.roll(source, 4096)
        self.assertEqual(int(np.dot(source.astype(np.int64), source.astype(np.int64))),
                         int(np.dot(moved.astype(np.int64), moved.astype(np.int64))))
        result = temporal_metrics(source, moved, rate, framewise=False)["high_bands_from_hz"]["6000"]
        self.assertGreater(result["magnitude_change_residual_power_sum"], 0)
        self.assertGreater(result["envelope_error_squared_sum"], 0)
        self.assertGreater(result["onset_error_squared_sum"], 0)

    def test_source_classification_does_not_change_with_decoded_noise(self):
        rate = 12000
        source = np.rint(1000 * np.sin(2 * np.pi * 250 * np.arange(rate) / rate)).astype(np.int16)
        noisy = np.random.default_rng(9).integers(-10000, 10001, rate)
        a = temporal_metrics(source, source, rate)
        b = temporal_metrics(source, noisy, rate)
        self.assertEqual(a["source_framewise_private"], b["source_framewise_private"])

    def test_every_native_band_and_silence_noise_remain_visible(self):
        for rate, count in ((8000, 4), (12000, 6), (16000, 8)):
            source = np.zeros(rate, dtype=np.int16)
            decoded = np.random.default_rng(1).integers(-100, 101, rate)
            result = temporal_metrics(source, decoded, rate, framewise=False)
            self.assertEqual(len(result["bands"]), count)
            self.assertEqual(result["bands"][-1]["high_hz"], rate // 2)
            self.assertEqual(result["source_active_frames"], 0)
            self.assertGreater(sum(b["magnitude_residual_power_sum"] for b in result["bands"]), 0)
            if rate <= 12000:
                self.assertIsNone(result["high_bands_from_hz"]["6000"])
            else:
                self.assertIsNotNone(result["high_bands_from_hz"]["6000"])


if __name__ == "__main__":
    unittest.main()

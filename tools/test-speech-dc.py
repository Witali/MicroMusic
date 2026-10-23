"""Integer DC blocker correctness and signal-behaviour regression tests."""
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from dc_blocker import block_dc, state_bounds


def signed(x):
    return x.astype(np.int16)-128


class DcBlockerTests(unittest.TestCase):
    def test_silence_and_constants_settle_exactly(self):
        for shift in (5, 6, 7):
            for value in (0, 1, 73, 128, 172, 254, 255):
                out, state, clips, peak = block_dc(np.full(8192, value, np.uint8), shift)
                np.testing.assert_array_equal(out[-512:], 128)
                self.assertEqual(clips, 0)
                self.assertLessEqual(peak, 128)
                lo, hi = state_bounds(shift)
                self.assertTrue(lo <= state <= hi)

    def test_chunks_and_phrase_loops_equal_continuous_filtering(self):
        rng = np.random.default_rng(23080)
        phrase = rng.integers(0, 256, 1023, dtype=np.uint8)
        all_input = np.tile(phrase, 3)
        for shift in (5, 6, 7):
            expected, expected_state, clips, peak = block_dc(all_input, shift)
            state, outputs, chunk_clips, chunk_peak = 0, [], 0, 0
            for chunk in np.array_split(all_input, 31):
                out, state, count, local_peak = block_dc(chunk, shift, state)
                outputs.append(out)
                chunk_clips += count
                chunk_peak = max(chunk_peak, local_peak)
            np.testing.assert_array_equal(np.concatenate(outputs), expected)
            self.assertEqual((state, chunk_clips, chunk_peak), (expected_state, clips, peak))

    def test_scalar_signed16_specification_and_extreme_state_bounds(self):
        rng = np.random.default_rng(23081)
        pcm = np.r_[np.zeros(2000, np.uint8), np.full(2000, 255, np.uint8),
                    rng.integers(0, 256, 20000, dtype=np.uint8)]
        for shift in (5, 6, 7):
            state, result, clips, peak = 0, [], 0, 0
            lo, hi = state_bounds(shift)
            for value in pcm:
                rounded = state+(1 << (shift-1))
                self.assertTrue(-32768 <= rounded <= 32767)
                sample = int(value)-128-(rounded >> shift)
                state += sample
                self.assertTrue(lo <= state <= hi)
                clips += not -128 <= sample <= 127
                peak = max(peak, abs(sample))
                result.append(max(-128, min(127, sample))+128)
            out, final, count, max_sample = block_dc(pcm, shift)
            np.testing.assert_array_equal(out, result)
            self.assertEqual((final, count, max_sample), (state, clips, peak))
            self.assertGreater(clips, 0)

    def test_slow_drift_removed_while_voice_band_is_preserved(self):
        n = np.arange(75000)
        tone = np.rint(35*np.sin(2*np.pi*300*n/7500))
        drift = 24+np.rint(14*np.sin(2*np.pi*2*n/7500))
        pcm = (128+tone+drift).astype(np.uint8)
        for shift in (5, 6, 7):
            out, _, clips, _ = block_dc(pcm, shift)
            residual = signed(out)[3000:]
            signal = tone[3000:]
            # Integer quantization adds about one LSB; voice gain remains close.
            gain = np.dot(residual, signal)/np.dot(signal, signal)
            drift_out = np.convolve(residual, np.ones(750)/750, mode='valid')
            self.assertTrue(.97 < gain < 1.04)
            self.assertLess(np.sqrt(np.mean(drift_out**2)), 2.5)
            self.assertLess(abs(residual.mean()), .1)
            self.assertEqual(clips, 0)

    def test_tail_settles_and_asymmetry_is_not_mirrored(self):
        period = np.r_[np.full(5, 180, np.uint8), np.full(20, 115, np.uint8)]
        out, state, _, _ = block_dc(np.tile(period, 400), 6)
        x = signed(out[-1000:])
        self.assertGreater(x.max(), 3*abs(x.min()))
        tail, _, _, _ = block_dc(np.full(2048, 128, np.uint8), 6, state)
        np.testing.assert_array_equal(tail[-512:], 128)

    def test_input_validation(self):
        for shift in (0, 4, 8):
            with self.assertRaises(ValueError):
                block_dc(np.array([128], np.uint8), shift)
        with self.assertRaises(ValueError):
            block_dc([128])
        with self.assertRaises(ValueError):
            block_dc(np.array([128], np.uint8), 6, 32767)


if __name__ == '__main__':
    unittest.main()

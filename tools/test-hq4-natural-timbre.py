"""T-profile compatibility, explicit overflow detection and gentle rate fitting."""
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_core import pack_stream, unpack_stream
from hq4_timbre import restore_tilt

spec = importlib.util.spec_from_file_location('natural_timbre', ROOT/'tools/probe-hq4-natural-timbre.py')
natural = importlib.util.module_from_spec(spec)
spec.loader.exec_module(natural)


class NaturalTimbreTests(unittest.TestCase):
    def test_profile_two_matches_retained_integer_t_model(self):
        pcm = np.random.default_rng(531).integers(0, 256, 4096, dtype=np.uint8)
        np.testing.assert_array_equal(natural.tilt(pcm, 2)[0], restore_tilt(pcm))

    def test_filter_overflow_is_counted_even_if_wrapped_output_is_finite(self):
        pcm = np.full(256, 255, np.uint8)
        result, wraps = natural.tilt(pcm, 3)
        self.assertGreater(wraps, 0)
        self.assertEqual(result.dtype, np.uint8)
        self.assertEqual(len(result), len(pcm))
        self.assertEqual(natural.tilt(np.full(256, 128, np.uint8), 3)[1], 0)

    def test_local_rate_fit_preserves_all_timing_pitch_gain_and_excitation(self):
        stream = (ROOT/'ATtiny13A/Sound/codec/release/vinni/speech.hq').read_bytes()
        frames, durations = unpack_stream(stream)
        fitted = natural.fit_rate(frames, durations, 603)
        self.assertLessEqual(len(pack_stream(fitted, durations)), 603)
        np.testing.assert_array_equal(fitted[:, :2], frames[:, :2])
        self.assertEqual(int(durations.sum()), 22272)
        # The first parameter frame must still initialize the lattice exactly.
        np.testing.assert_array_equal(fitted[0], frames[0])


if __name__ == '__main__':
    unittest.main()

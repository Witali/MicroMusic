"""Complete-phrase analysis, period detection and exact-decoded rate constraints."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from new_hq4_encoder import (analyze, initial_model, pitch_period, search,
                             validate_reference, MAX_STREAM_BYTES)
from hq4_core import pack_stream, unpack_stream
from model import decode


class NewHQ4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames = np.array([[50, 4, 137, 136, 136, 136]]*20, np.uint8)
        cls.durations = np.full(20, 256, np.uint16)
        cls.reference = (decode(cls.frames, cls.durations, 0).astype(float)-128)/128

    def test_fundamental_is_not_a_harmonic_or_zero(self):
        t = np.arange(256)
        for period in (25, 50, 80):
            # A weaker fundamental plus its strong second harmonic must not
            # force an octave-up estimate when the true period is supported.
            audio = np.sin(2*np.pi*t/period)+.65*np.sin(4*np.pi*t/period)
            self.assertLessEqual(abs(pitch_period(audio)-period), 1)
        self.assertEqual(pitch_period(np.zeros(256)), 0)

    def test_analysis_retains_awkward_final_block(self):
        for hop in (64, 128, 256):
            x = np.r_[self.reference, self.reference[:192]]
            f, d = analyze(x, hop=hop)
            self.assertEqual(int(d.sum()), len(x))
            self.assertTrue(all(int(n) in (64, 128, 192, 256) for n in d))
            got_f, got_d = unpack_stream(pack_stream(f, d))
            np.testing.assert_array_equal(decode(got_f, got_d, 0), decode(f, d, 0))

    def test_complete_recording_can_be_rate_selected(self):
        (f, d, score, _), trials = initial_model(self.reference, stream_budget=150)
        self.assertLessEqual(len(pack_stream(f, d)), 150)
        self.assertEqual(len(decode(f, d, 0)), len(self.reference))
        self.assertTrue(np.isfinite(score['stoi']))
        self.assertGreater(len(trials), 1)

    def test_long_recording_has_no_silent_truncation_fallback(self):
        long = np.tile(self.reference, 25)[:126144]
        with self.assertRaisesRegex(ValueError, 'complete recording'):
            initial_model(long)

    def test_search_preserves_quality_guards_and_is_seeded(self):
        args = dict(proposals=50, seed=129, stream_budget=MAX_STREAM_BYTES)
        f, d, report = search(self.reference, self.frames, self.durations, **args)
        f2, d2, report2 = search(self.reference, self.frames, self.durations, **args)
        self.assertEqual(pack_stream(f, d), pack_stream(f2, d2))
        self.assertEqual(report, report2)
        self.assertEqual(int(d.sum()), len(self.reference))
        self.assertGreaterEqual(report['final']['stoi']+1e-12, report['initial']['stoi'])
        self.assertLessEqual(report['final']['loss'], report['initial']['loss']*1.03+1e-12)

    def test_search_rejects_malformed_model_instead_of_decoding_it(self):
        for f, d in ((self.frames[:, :5], self.durations),
                     (self.frames, self.durations[:-1]),
                     (self.frames.astype(float), self.durations),
                     (self.frames, self.durations.astype(np.int64)-257)):
            with self.assertRaises(ValueError):
                search(self.reference, f, d, proposals=0)

    def test_reference_contract_rejects_changed_rate_bad_samples_and_silence(self):
        for x, sr in ((self.reference, 8000), (self.reference[:-1], 7500),
                      (np.zeros(5120), 7500), (np.full(5120, np.nan), 7500),
                      (np.column_stack((self.reference, self.reference)), 7500)):
            with self.assertRaises(ValueError):
                validate_reference(x, sr)


if __name__ == '__main__':
    unittest.main()

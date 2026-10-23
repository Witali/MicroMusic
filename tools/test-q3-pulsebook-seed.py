"""Fixed-time packet learning and exact modular inverse contracts."""
import json
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from q3_pulsebook import legacy_tables, render, validate
from q3_pulsebook_seed import timing, byte_inverse, initialize


class PulsebookSeedTests(unittest.TestCase):
    def test_schedule_starts_at_lag_one_and_advances_at_duration_minus_one(self):
        f = np.array([[5, 1, 0x88, 0x88, 0x88, 0x88]]*3, np.uint8)
        d = np.array([64, 64, 64], np.uint16)
        owner, lag = timing(f, d)
        np.testing.assert_array_equal(np.bincount(owner), [64, 64, 64])
        np.testing.assert_array_equal(lag[:6], [1, 2, 3, 4, 0, 1])
        self.assertEqual(lag[63], 1)
        self.assertEqual(lag[127], 1)
        self.assertEqual(owner[-1], 0)
        self.assertEqual(lag[-1], 1)

    def test_byte_inverse_recovers_known_source_for_both_product_rules(self):
        f = np.array([[30, 2+16*(i % 4), 0x9a, 0x87, 0x99, 0x88] for i in range(16)], np.uint8)
        f[4:6, 0] = 0
        d = np.full(16, 256, np.uint16)
        book = legacy_tables()
        owner, lag = timing(f, d)
        seed, excitation = 0xa7, np.zeros(int(d.sum()), np.int16)
        for t in range(len(excitation)):
            i, gain = int(owner[t]), int(f[owner[t], 1] & 15)
            if not f[i, 0]:
                low = seed & 1
                seed >>= 1
                if low: seed ^= 0xb8
                excitation[t] = -gain if seed & 1 else gain
            elif lag[t] < 16:
                excitation[t] = int(book[int(f[i, 1] >> 4), lag[t]])*gain
        for nearest in (False, True):
            pcm, _ = render(f, d, book, 1, nearest)
            target = pcm.astype(np.int16)-128
            got = byte_inverse(target, f, d, nearest)
            np.testing.assert_array_equal(got, excitation)

    def test_learned_seed_is_parameter_only_bounded_and_keeps_complete_timing(self):
        f = np.array([[30, 2+16*(i % 4), 0x88, 0x88, 0x88, 0x88] for i in range(16)], np.uint8)
        d = np.full(16, 256, np.uint16)
        pcm, _ = render(f, d, legacy_tables(), 1, True)
        reference = (pcm.astype(float)-128)/128
        model, report = initialize(reference, f.tolist(), d.tolist(), nearest=True,
            inverse='byte', balance=False, iterations=4, stream_budget=615)
        serialized = json.loads(json.dumps(model))
        frames = np.asarray(serialized['frames'], np.uint8)
        durations = np.asarray(serialized['durations'], np.uint16)
        book = np.asarray(serialized['pulsebook'], np.int8)
        validate(frames, durations, book, len(reference), 615)
        np.testing.assert_array_equal(durations, d)
        np.testing.assert_array_equal(frames[:, 0], f[:, 0])
        independent, _ = render(frames, durations, book, 1, True)
        reference[:] = 0  # Decoding cannot use retained source samples.
        np.testing.assert_array_equal(independent, render(frames, durations, book, 1, True)[0])
        self.assertEqual(len(independent), len(pcm))
        self.assertEqual(report['changed_pitch_frames'], 0)

    def test_unstable_fields_and_changed_source_length_fail_before_fitting(self):
        f = np.array([[30, 2, 0x88, 0x88, 0x88, 0x88]]*16, int)
        d = np.full(16, 256, int)
        for invalid in (f+np.array([256, 0, 0, 0, 0, 0]), f.copy()):
            if invalid.max() < 256: invalid[0, 2] = 0x80
            with self.assertRaises(ValueError):
                initialize(np.zeros(4096), invalid, d)
        with self.assertRaises(ValueError):
            initialize(np.zeros(4095), f, d)


if __name__ == '__main__':
    unittest.main()

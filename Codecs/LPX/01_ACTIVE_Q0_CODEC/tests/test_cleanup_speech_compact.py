"""Independent q-history/DAG oracles and full native admission for exact cleanup."""
import struct
import unittest

import numpy as np

from batch_decoder import BatchSession
from cleanup_speech_compact import cleanup, _cleanup_once
from lpx4 import BitWriter
from q0_model import table
import speech_compact as compact


def fields(profile=4, samples=640):
    frames = (samples + 319) // 320
    spectra = [[2 + i * 2 for i in range(10)] for _ in range(frames)]
    params = [(20, 20, 14)] * (frames * 2)
    pulses = [(0, 8 if profile == 4 else 7)] * (frames * 16)
    return [samples, profile, spectra, params, pulses, 13926, 6000]


def trace(blob):
    """Scalar oracle: complete causal history, not the implementation's ring."""
    n, _, _, params, pulses, _, _, extras = compact.unpack(blob)
    steps = table('scale_table.inc')
    history = []
    drive = []
    for at in range(n):
        scale, lag, gain = params[at // 160]
        old = history[at - lag] if at >= lag else 0
        # Python floor division independently spells the signed right shift.
        prediction = (gain * old + 8) // 16
        pos, amp = pulses[at // 20]
        ep, ea = extras[at // 40]
        value = prediction + (amp if at % 20 == pos else 0) + (ea if at % 40 == ep else 0)
        value = max(-32, min(31, value))
        history.append(value)
        drive.append(value * int(steps[scale * 8]))
    live = {at for at in range(n) if steps[params[at // 160][0] * 8] != 0}
    todo = list(live)
    while todo:
        at = todo.pop()
        _, lag, gain = params[at // 160]
        parent = at - lag
        if gain and parent >= 0 and parent not in live:
            live.add(parent)
            todo.append(parent)
    return history, drive, live


def alternate_syntax(values, *, zero_markers=False, escape_spectrum=False):
    """Legal noncanonical bitstream, written separately from compact.pack."""
    n, profile, spectra, params, pulses, _, _ = values
    canonical = compact.pack(*values, force_extras=zero_markers)[0]
    writer = BitWriter()
    previous = None
    for frame, spectrum in enumerate(spectra):
        if escape_spectrum:
            writer.put(1, 1)
            writer.put(0, 1)
            gaps = [spectrum[0]] + [b - a - 1 for a, b in zip(spectrum, spectrum[1:])]
            for gap in gaps:
                writer.put(0, 8)
                writer.put(gap, 5 if profile == 4 else 6)
        else:
            compact.put_spectrum(writer, spectrum, previous, 5 if profile == 4 else 6)
        previous = spectrum
        for half in range(2):
            scale, lag, gain = params[frame * 2 + half]
            writer.put(scale, 5); writer.put(lag - 18, 7); writer.put(gain // 2, 3)
            for chunk in range(4):
                a, b = pulses[frame * 16 + half * 8 + chunk * 2:frame * 16 + half * 8 + chunk * 2 + 2]
                if profile == 4:
                    for position, amplitude in (a, b):
                        writer.put(list(compact.v4.POSITIONS4).index(position), 4)
                        writer.put(int(amplitude > 0), 1)
                else:
                    pair = a[0] + 20 * b[0]
                    writer.put(pair, 8); writer.put(pair >> 8, 1)
                    writer.put(a[1] & 15, 4); writer.put(b[1] & 15, 4)
                if zero_markers:
                    writer.put(1, 1); writer.put(39, 6); writer.put(0, 4)
    writer.aligned()
    payload = writer.get()
    return canonical[:20] + struct.pack('<H', len(payload)) + payload


class CleanupSpeechCompactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.common_session = BatchSession('batch', v3_features=124, speech=True, speech_compact=True)
        cls.compact_session = BatchSession('batch', v3_features=124, speech=True, speech_compact=True, compact_only=True)
        cls.common = cls.common_session.__enter__()
        cls.only = cls.compact_session.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.compact_session.__exit__()
        cls.common_session.__exit__()

    def check(self, blob):
        new, report = cleanup(blob, common=self.common, compact_only=self.only)
        old_q, old_drive, live = trace(blob)
        new_q, new_drive, _ = trace(new)
        self.assertEqual(old_drive, new_drive)
        self.assertEqual([old_q[i] for i in sorted(live)], [new_q[i] for i in sorted(live)])
        self.assertEqual(report['observable_q_samples'], len(live))
        self.assertEqual(compact.unpack(blob)[:7], compact.unpack(new)[:7])
        self.assertLessEqual(len(new), len(blob))
        self.assertEqual(_cleanup_once(new)[0], new)
        self.assertTrue(report['native_common_pcm_pwm_exact'] and report['native_v5_only_pcm_pwm_exact'])
        self.assertEqual(report['saved_bytes'], sum(report[k] for k in (
            'canonical_repack_saved_bytes', 'dead_active_removal_saved_bytes',
            'saturated_active_removal_saved_bytes', 'empty_marker_layer_saved_bytes')))
        return new, report

    def test_zero_scale_history_is_live_only_when_later_gain_reads_it(self):
        for gain in (0, 14):
            values = fields(6, 320)
            values[3] = [(0, 18, 0), (20, 145, gain)]
            extras = [(-1, 0)] * 8
            extras[0] = (15, 7)
            blob = compact.pack(*values, extras=extras)[0]
            new, report = self.check(blob)
            self.assertEqual(report['unobservable_extras_removed'], int(gain == 0))
            self.assertEqual(compact.unpack(new)[7][0], (-1, 0) if gain == 0 else (15, 7))
            if gain == 0:
                self.assertGreater(report['changed_unobservable_q_samples'], 0)
            else:
                without = compact.pack(*values)[0]
                self.assertFalse(np.array_equal(compact.decode_model(blob), compact.decode_model(without)))

    def test_both_clipping_signs_feedback_and_signed_rounding(self):
        for sign in (-1, 1):
            values = fields(4, 640)
            values[4] = [(0, sign * 8)] * 32
            extras = [(-1, 0)] * 16
            # Let the unmodified recurrence reach the asymmetric -32/+31
            # bounds before testing same-sign and opposite-sign clipping ties.
            extras[3] = (0, -8 if sign < 0 else 7)
            extras[4] = (0, 1 if sign < 0 else -1)
            blob = compact.pack(*values, extras=extras)[0]
            _, report = self.check(blob)
            self.assertEqual(report['saturation_equivalent_extras_removed'], 2)
            self.assertFalse(report['final_extra_marker_layer'])

    def test_mandatory_partial_packet_fields_and_unplayed_tail_extras(self):
        for profile in (4, 6):
            for samples in (1, 19, 20, 39, 40, 159, 160, 161, 180, 300, 319, 320, 321, 500):
                values = fields(profile, samples)
                extras = [(39, 7)] * (len(values[2]) * 8)
                blob = compact.pack(*values, extras=extras)[0]
                _, report = self.check(blob)
                self.assertEqual(report['unplayed_tail_extras_removed'], sum(
                    chunk * 40 + 39 >= samples for chunk in range(len(extras))))
                self.assertEqual(report['stored_samples'], ((samples + 319) // 320) * 320)

    def test_legal_zero_amplitude_markers_and_noncanonical_rice_are_separate(self):
        for profile in (4, 6):
            values = fields(profile, 321)
            blob = alternate_syntax(values, zero_markers=True, escape_spectrum=True)
            self.assertTrue(all(a == 0 and p == 39 for p, a in compact.unpack(blob)[7]))
            new, report = self.check(blob)
            self.assertEqual(report['legal_marker_one_amplitude_zero_count'], 16)
            self.assertEqual(report['original_active_extras'], 0)
            self.assertEqual(report['dead_active_removal_saved_bytes'], 0)
            self.assertEqual(report['saturated_active_removal_saved_bytes'], 0)
            self.assertGreater(report['canonical_repack_saved_bytes'], 20)
            self.assertEqual(report['empty_marker_layer_saved_bytes'], 2)
            self.assertEqual(new, compact.pack(*values)[0])

    def test_random_mixed_scales_lags_gains_positions_and_full_native_outputs(self):
        rng = np.random.default_rng(640001)
        for profile in (4, 6):
            for trial in range(24):
                n = int(rng.integers(1, 1601))
                values = fields(profile, n)
                values[2] = [sorted(map(int, rng.choice(32 if profile == 4 else 64, 10, replace=False)))
                             for _ in values[2]]
                values[3] = [(int(rng.integers(0, 32)), int(rng.integers(18, 146)), int(rng.integers(0, 8)) * 2)
                             for _ in values[3]]
                values[3][0] = (trial % 6, 18 if trial & 1 else 145, 14)
                values[4] = [(int(rng.choice(compact.v4.POSITIONS4)) if profile == 4 else int(rng.integers(20)),
                              int(rng.choice((-8, 8))) if profile == 4 else int(rng.integers(-8, 8)))
                             for _ in values[4]]
                values[5] = int(rng.integers(0, 16385)); values[6] = int(rng.integers(0, 11470))
                extras = [(int(rng.integers(0, 40)), int(rng.integers(-8, 8)))
                          for _ in range(len(values[2]) * 8)]
                self.check(compact.pack(*values, extras=extras)[0])

    def test_maximum_stream_and_owned_input_fixed_point(self):
        values = fields(6, 64000)
        extras = [(0, 7)] * 1600
        blob = bytearray(compact.pack(*values, extras=extras)[0])
        before = bytes(blob)
        new, report = self.check(blob)
        self.assertEqual(bytes(blob), before)
        self.assertEqual(report['samples'], 64000)
        again, second = cleanup(new, common=self.common, compact_only=self.only)
        self.assertEqual(again, new)
        self.assertEqual(second['saved_bytes'], 0)

    def test_invalid_input_and_native_mismatch_never_return_a_result(self):
        valid = compact.pack(*fields(4, 180))[0]
        for invalid in (valid[:21], valid[:-1], valid + b'\0', bytes(22), b'', 7):
            with self.assertRaises(ValueError):
                cleanup(invalid, common=self.common, compact_only=self.only)
        class WrongDecoder:
            def decode_one_s16(self, blob, n): return np.zeros(n, np.int16)
            def decode_one(self, blob, n): return np.zeros(n, np.uint8)
        with self.assertRaises(AssertionError):
            cleanup(valid, common=WrongDecoder(), compact_only=self.only)


if __name__ == '__main__':
    unittest.main()

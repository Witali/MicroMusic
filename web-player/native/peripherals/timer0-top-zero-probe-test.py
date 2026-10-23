"""Synthetic protocol tests only; these are not ATtiny13A observations."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "probe_decode", Path(__file__).with_name("timer0-top-zero-probe-decode.py"))
decoder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decoder)


def frame(kind, sequence, counter=0):
    payload = [1, kind, sequence & 255, sequence >> 8, counter, 0, 16, 0, 0, 0x61, 0x0f]
    checksum = 0
    for value in payload:
        checksum ^= value
    return [0xa5, 0x5a] + payload + [checksum]


def capture(frames):
    changes = [(0.0, {})]
    for number, encoded in enumerate(frames):
        start = number * 0.02 + 0.001
        if number:
            changes.extend([(start, {"t0": 1}), (start + 0.005, {"t0": 0})])
        bit_index = 0
        for value in encoded:
            for bit in range(7, -1, -1):
                at = start + 0.000010 + bit_index * 0.000002
                changes.extend([(at, {"data": (value >> bit) & 1}),
                                (at + 0.0000005, {"clock": 1}),
                                (at + 0.000001, {"clock": 0})])
                bit_index += 1
    state = {"clock": 0, "data": 0, "t0": 0}
    rows = []
    for at, change in sorted(changes, key=lambda item: item[0]):
        state.update(change)
        rows.append({"time_s": str(at), **{key: str(value) for key, value in state.items()}})
    return rows


class ProtocolTests(unittest.TestCase):
    profile = {"pulses": 2, "defines": {}}

    def test_preserves_unpredicted_counter_values(self):
        rises, records = decoder.decode_rows(capture([frame(0, 0), frame(1, 1, 199), frame(1, 2, 31)]), self.profile)
        self.assertEqual(len(rises), 2)
        self.assertEqual([record["tcnt0"] for record in records], [0, 199, 31])

    def test_rejects_corrupted_checksum(self):
        corrupted = frame(1, 1)
        corrupted[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "Checksum"):
            decoder.decode_rows(capture([frame(0, 0), corrupted, frame(1, 2)]), self.profile)

    def test_rejects_missing_pulse_record(self):
        with self.assertRaisesRegex(ValueError, "sequence"):
            decoder.decode_rows(capture([frame(0, 0), frame(1, 2), frame(1, 3)]), self.profile)

    def test_rejects_truncated_capture(self):
        rows = capture([frame(0, 0), frame(1, 1), frame(1, 2)])
        rows = [row for row in rows if float(row["time_s"]) < 0.0412]
        with self.assertRaisesRegex(ValueError, "Incomplete frame"):
            decoder.decode_rows(rows, self.profile)


if __name__ == "__main__":
    unittest.main()

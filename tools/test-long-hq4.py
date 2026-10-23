"""Meaningful duration, parser safety and legacy compatibility checks."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from long_hq4 import pack_stream, unpack_stream
from hq4_core import pack_stream as legacy_pack


class LongHq4Tests(unittest.TestCase):
    def test_all_duration_codes_and_pitch_modes(self):
        d = np.arange(64, 3969, 64, dtype=np.uint16)
        for pitch in (0, 1, 63, 64, 126):
            f = np.tile(np.array([pitch, 63, 0x78, 0x89, 0xab, 0xcd], np.uint8), (len(d), 1))
            actual_f, actual_d = unpack_stream(pack_stream(f, d))
            np.testing.assert_array_equal(actual_f, f)
            np.testing.assert_array_equal(actual_d, d)

    def test_existing_headers_are_byte_identical(self):
        d = np.array([64, 128, 192, 256, 64, 128, 192, 256], np.uint16)
        f = np.array([[p, 2, 0x88, 0x87, 0x88, 0x89] for p in (0, 48, 63, 64, 88, 126, 1, 20)], np.uint8)
        self.assertEqual(pack_stream(f, d), legacy_pack(f, d))

    def test_retained_public_streams_are_compatible(self):
        for clip in ('chego', 'otvechaesh', 'vinni'):
            payload = (ROOT/'ATtiny13A/Sound/codec/release'/clip/'speech.hq').read_bytes()
            f, d = unpack_stream(payload)
            self.assertEqual(pack_stream(f, d), payload)

    def test_coefficient_update_modes(self):
        f = np.array([[48, 1, 0x88, 0x88, 0x88, 0x88], [49, 2, 0x87, 0x88, 0x88, 0x88],
                      [50, 3, 0x87, 0x88, 0x89, 0x88], [51, 4, 0x87, 0x88, 0x89, 0x88],
                      [52, 5, 0x88, 0x88, 0x88, 0x88]], np.uint8)
        d = np.array([512]*5, np.uint16)
        decoded, durations = unpack_stream(pack_stream(f, d))
        np.testing.assert_array_equal(decoded, f)
        np.testing.assert_array_equal(durations, d)

    def test_reserved_eof_and_bad_durations(self):
        frame = [[48, 2, 0x88, 0x88, 0x88, 0x88]]
        for duration in (0, 63, 65, 4032, 4096, 65536, -64, 128.5):
            with self.assertRaises(ValueError):
                pack_stream(frame, [duration])
        for payload in (b'', b'\xff', b'\xc4', b'\xc4\x30', b'\x30\x42',
                        b'\xc4\x7f\x02\x88\x88\x88\x88', b'\x30\x02\x88'):
            with self.assertRaises(ValueError):
                unpack_stream(payload)


if __name__ == '__main__':
    unittest.main()

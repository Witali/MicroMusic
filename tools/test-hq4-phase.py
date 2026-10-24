"""Independent checks for audited arithmetic and the specified phase lifecycle."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_core import unpack_stream
from model import decode as legacy
from hq4_phase import audit, decode, render


class PhaseTests(unittest.TestCase):
    def test_legacy_auditor_matches_all_retained_streams(self):
        for clip in ('chego', 'otvechaesh', 'vinni'):
            f, d = unpack_stream((ROOT/'ATtiny13A/Sound/codec/release'/clip/'speech.hq').read_bytes())
            np.testing.assert_array_equal(decode(f, d, False), legacy(f, d, 0))

    def test_continuous_countdown_crosses_frame_boundary(self):
        f = np.array([[48, 3, 0x88, 0x88, 0x88, 0x88]]*2, np.uint8)
        d = np.array([64, 128], np.uint16)
        _, _, old, _, _ = render(f, d, False)
        _, _, new, _, _ = render(f, d, True)
        self.assertEqual(list(np.flatnonzero(old)[:2]), [47, 110])
        self.assertEqual(list(np.flatnonzero(new)[:2]), [47, 95])

    def test_zero_initial_period_is_explicitly_preserved(self):
        f = np.array([[0, 3, 0x88, 0x88, 0x88, 0x88], [64, 3, 0x88, 0x88, 0x88, 0x88]], np.uint8)
        d = np.array([64, 256], np.uint16)
        _, _, pulses, _, _ = render(f, d, True)
        self.assertEqual(list(np.flatnonzero(pulses)), [318])

    def test_wrap_audit_detects_real_overflow_not_only_output_extrema(self):
        f = np.array([[40, 15, 0, 255, 193, 115], [21, 15, 83, 113, 192, 104],
                      [42, 15, 8, 104, 39, 88], [2, 15, 210, 163, 99, 208]], np.uint8)
        d = np.array([256]*4, np.uint16)
        info = audit(f, d)
        self.assertGreater(info['subtraction_wraps']+info['state_addition_wraps'], 0)
        self.assertEqual(info['multiplication_count'], 15*1024)
        np.testing.assert_array_equal(decode(f, d, False), legacy(f, d, 0))


if __name__ == '__main__':
    unittest.main()

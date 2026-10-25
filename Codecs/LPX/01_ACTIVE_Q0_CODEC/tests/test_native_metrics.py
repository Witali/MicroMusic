"""The native read-bit probe must handle the decoder's 32-bit sample counts."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from optimize_q0 import cost_probe, probe
from test_beam_excitation import raw_fixture


class NativeMetricsTests(unittest.TestCase):
    def test_long_stream_does_not_wrap_count_or_rolling_windows(self):
        executable = cost_probe()
        reports = []
        for count in (65535, 65536, 65697):
            report = probe(raw_fixture(samples=count), executable)
            self.assertEqual(report['samples'], count)
            reports.append(report)
        # Extending the identical repeating tail cannot introduce a new peak.
        for field in ('max_bit_calls_sample', 'max_bit_calls_80', 'max_bit_calls_160'):
            self.assertEqual([r[field] for r in reports], [reports[0][field]] * 3)


if __name__ == '__main__':
    unittest.main()

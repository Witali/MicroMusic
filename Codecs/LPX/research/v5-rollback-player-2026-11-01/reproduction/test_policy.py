"""Pure scope/report/JSON contracts only; never import numerical player operators."""
import struct
import unittest
from policy import rows, geometry, normalize, sha, report_ok, SAMPLES, BYTES


def fixture():
    parts, blobs = [], []; at = 0
    for index, (samples, size) in enumerate(zip((64000, 64000, 64000, 64000, 25632), (3000, 3000, 3000, 3000, 4141))):
        blob = struct.pack('<4sBBHIHHHHH', b'L4HY', 5, 132, 8000, samples, 0, 0, 320, 160, size - 22) + bytes(size - 22)
        parts.append(dict(index=index, start=at, profile=4, samples=samples, file_bytes=len(blob), stream_sha256=sha(blob), flags=132))
        blobs.append(blob); at += samples
    return parts, blobs


class PolicyContracts(unittest.TestCase):
    def test_exact_four_rows(self):
        actual = rows()
        self.assertEqual(len(actual), 4)
        self.assertEqual({(r['role'], r['extra_irq_cycles']) for r in actual},
                         {(role, irq) for role in ('baseline', 'candidate') for irq in (0, 100)})
        self.assertTrue(all(r['assembly'] is True and r['storage'] == 'rom' for r in actual))

    def test_complete_order_flags_and_bounds(self):
        parts, blobs = fixture(); geometry(parts, blobs)
        with self.assertRaises(ValueError): geometry(parts[:-1], blobs[:-1])
        bad = normalize(parts); bad[1]['start'] += 1
        with self.assertRaises(ValueError): geometry(bad, blobs)
        bad = normalize(parts); bad[0]['flags'] ^= 128
        with self.assertRaises(ValueError): geometry(bad, blobs)
        self.assertEqual(sum(map(len, blobs)), BYTES)

    def test_persisted_json_range_types(self):
        value = dict(verification=dict(cost=dict(embedded_segment_ranges=[(32, 64), (64, 128)])))
        persisted = normalize(value)
        self.assertIsInstance(persisted['verification']['cost']['embedded_segment_ranges'][0], list)
        self.assertEqual(normalize(persisted), persisted)

    def test_underrun_clock_eof_and_stack_rejected(self):
        report = dict(produced=SAMPLES, played=SAMPLES, timer_ticks=SAMPLES, timer_events=SAMPLES,
            underruns=0, decoder_error=0, observer_errors=0, observer_exit_code=0, queued_at_stop=0,
            eof=1, stopped=1, timer_started=1, stack_margin_all_bytes=100,
            cpu_hz=16000000, audio_hz=8000, tick_interval_min_cycles=1996, tick_interval_max_cycles=2004,
            pwm_interval_min_cycles=1936, pwm_interval_max_cycles=2064)
        report_ok(report)
        for key, value in (('underruns', 1), ('eof', 0), ('queued_at_stop', 1),
                           ('stack_margin_all_bytes', 0), ('cpu_hz', 8000000), ('played', True)):
            with self.assertRaises(ValueError): report_ok({**report, key: value})


if __name__ == '__main__': unittest.main()

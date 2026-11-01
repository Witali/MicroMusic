"""Contract checks for diagnostic label identity and executable-offset proof."""
import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT = Path(__file__).parents[1] / "scripts/probe-source-map-labels.py"
spec = importlib.util.spec_from_file_location("source_map_labels", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def mapping():
    rows = [[1, 0, 2, 3], [1], [5, 0, 2, -2, 0], [1, 0, 0, 0, 0]]
    return {"version": 3, "sources": ["web-player/native/peripherals/device.c"],
            "names": ["old"], "mappings": ",".join("".join(probe.vlq(v) for v in row) for row in rows)}


class LabelTests(unittest.TestCase):
    def test_labels_keep_positions_and_unmapped_gaps(self):
        original = probe.decode_map(mapping())
        for unique, count in [(False, 1), (True, 3)]:
            converted, expected = probe.label_map(mapping(), unique)
            rows = probe.decode_map(converted)
            self.assertEqual([(r["offset"], r["position"]) for r in rows],
                             [(r["offset"], r["position"]) for r in original])
            self.assertIsNone(rows[1]["name"])
            self.assertEqual(probe.check_labels(rows, expected), (3, count))

    def test_duplicate_source_positions_still_have_distinct_unique_labels(self):
        converted, _ = probe.label_map(mapping(), True)
        rows = probe.decode_map(converted)
        self.assertEqual(rows[2]["position"], rows[3]["position"])
        self.assertNotEqual(rows[2]["name"], rows[3]["name"])

    def test_wrong_and_unknown_label_origins_are_rejected(self):
        converted, expected = probe.label_map(mapping(), True)
        for field, value in [("name", "unknown"), ("position", ("", "other.c", 2, 3))]:
            rows = probe.decode_map(converted)
            rows[0][field] = value
            with self.assertRaises(AssertionError):
                probe.check_labels(rows, expected)

    def test_unsupported_and_broken_maps_are_rejected(self):
        self.assertEqual(probe.vlq(-(2**31)), "B")
        with self.assertRaises(AssertionError):
            probe.vlq(2**31)
        for changes in [{"version": 4}, {"mappings": ";"}, {"mappings": "g"},
                        {"mappings": "AAAAA", "names": []}, {"mappings": "B"},
                        {"mappings": "ggggggE"}, {"mappings": "AAAA,AAAA"}]:
            value = copy.deepcopy(mapping())
            value.update(changes)
            with self.assertRaises(AssertionError):
                probe.decode_map(value)

    def test_offset_proof_detects_custom_sections_before_executable_sections(self):
        header, body, custom = b"\0asm\1\0\0\0", b"\1\1\0", b"\0\2\1x"
        original = probe.executable_sections(header + body)
        self.assertEqual(original, probe.executable_sections(header + body + custom))
        self.assertNotEqual(original, probe.executable_sections(header + custom + body))
        for broken in [header + b"\1\x80", header + b"\1\2\0", b"invalid"]:
            with self.assertRaises(AssertionError):
                probe.executable_sections(broken)

    def test_python_optimization_cannot_silently_disable_proof(self):
        result = subprocess.run([sys.executable, "-O", str(SCRIPT), "--help"], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"requires its proof assertions", result.stderr)


if __name__ == "__main__":
    unittest.main()

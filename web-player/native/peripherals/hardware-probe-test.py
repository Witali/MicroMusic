"""Synthetic wire-v2 tests only; no chip measurements or predicted ADC results."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("hardware_probe_decode", Path(__file__).with_name("hardware-probe-decode.py"))
decoder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decoder)
CONFIG = {"schema": "micromusic-attiny13a-hardware-probe-v1", "probeId": 3,
          "sequencePolicy": "consecutive", "firmware": "missing-default.S"}
PROFILE = {"id": "synthetic", "profileId": 7}


def frame(sequence=0, data=(255, 0, 199, 31, 128, 2), version=2, probe=3, profile=7):
    payload = [version, probe, profile, sequence & 255, sequence >> 8, *data]
    checksum = 0
    for byte in payload:
        checksum ^= byte
    return [0xa5, 0x5a, *payload, checksum]


def bits(packet):
    return [(byte >> bit) & 1 for byte in packet for bit in range(7, -1, -1)]


def rows(stream):
    result = [{"time_s": "0", "clock": "0", "data": "0"}]
    for index, bit in enumerate(stream):
        for phase, clock in [(1, 0), (2, 1), (3, 0)]:
            result.append({"time_s": str((index * 4 + phase) / 1000000), "clock": str(clock), "data": str(bit)})
    return result


class ProtocolTests(unittest.TestCase):
    def test_preserves_unpredicted_bytes(self):
        result = decoder.decode_rows(rows(bits(frame()) + bits(frame(1))), CONFIG, PROFILE)
        self.assertEqual([r["sequence"] for r in result["records"]], [0, 1])
        self.assertEqual(result["records"][1]["data"], [255, 0, 199, 31, 128, 2])
        self.assertEqual(result["transportQuality"], "complete-frames")
        self.assertEqual(result["fragments"], [])

    def test_checksum(self):
        packet = frame()
        packet[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "Checksum"):
            decoder.decode_rows(rows(bits(packet)), CONFIG, PROFILE)

    def test_legacy_version_is_distinct(self):
        with self.assertRaisesRegex(ValueError, "legacy Timer0"):
            decoder.decode_rows(rows(bits(frame(version=1))), CONFIG, PROFILE)

    def test_identity(self):
        for patch in ({"probe": 2}, {"profile": 8}):
            with self.subTest(patch=patch), self.assertRaisesRegex(ValueError, "identity"):
                decoder.decode_rows(rows(bits(frame(**patch))), CONFIG, PROFILE)

    def test_missing_or_duplicate_record(self):
        for sequence in (0, 2):
            with self.subTest(sequence=sequence), self.assertRaisesRegex(ValueError, "sequence"):
                decoder.decode_rows(rows(bits(frame()) + bits(frame(sequence))), CONFIG, PROFILE)

    def test_truncated_tail(self):
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            decoder.decode_rows(rows(bits(frame()) + bits(frame(1))[:37]), CONFIG, PROFILE)

    def test_no_frame(self):
        with self.assertRaisesRegex(ValueError, "No complete"):
            decoder.decode_rows(rows([]), CONFIG, PROFILE)

    def test_bad_timestamp(self):
        for value in ("nan", "inf", "-inf", "-1"):
            capture = rows(bits(frame()))
            capture[2]["time_s"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                decoder.decode_rows(capture, CONFIG, PROFILE)

    def test_bad_digital_or_initial_clock(self):
        for column, value in (("clock", "2"), ("data", "0.5"), ("clock", "1")):
            capture = rows(bits(frame()))
            capture[0][column] = value
            with self.subTest(column=column, value=value), self.assertRaises(ValueError):
                decoder.decode_rows(capture, CONFIG, PROFILE)

    def test_repeated_boot_frames(self):
        config = {**CONFIG, "probeId": 2, "sequencePolicy": "reset-to-zero"}
        capture = rows(bits(frame(probe=2)) + bits(frame(probe=2)))
        self.assertEqual(len(decoder.decode_rows(capture, config, PROFILE)["records"]), 2)

    def test_reset_fragments_are_explicit(self):
        config = {**CONFIG, "probeId": 2, "sequencePolicy": "reset-to-zero"}
        packet = bits(frame(probe=2))
        capture = rows(packet + packet[:37] + packet + packet[:9])
        with self.assertRaises(ValueError):
            decoder.decode_rows(capture, config, PROFILE)
        result = decoder.decode_rows(capture, config, PROFILE, True)
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual([gap["bitCount"] for gap in result["fragments"]], [37, 9])
        self.assertEqual(result["transportQuality"], "unframed-bits-retained")

    def test_fragment_recovery_not_for_adc(self):
        with self.assertRaisesRegex(ValueError, "reset-to-zero"):
            decoder.decode_rows(rows(bits(frame())), CONFIG, PROFILE, True)

    def test_expected_record_count(self):
        with self.assertRaisesRegex(ValueError, "Expected 2"):
            decoder.decode_rows(rows(bits(frame())), {**CONFIG, "expectedRecords": 2}, PROFILE)

    def test_hardware_conditions(self):
        conditions = {"chipMarking": "synthetic test fixture", "chipRevision": None,
                      "vccVolts": 5, "temperatureC": 25, "clockHz": 8000000,
                      "fuses": {"low": "0x70", "high": "0xff", "lock": 255},
                      "instrument": {"name": "synthetic, not hardware"}, "timingToleranceSeconds": 1e-8}
        self.assertEqual(decoder.measurements(conditions), conditions)
        for key, value in (("vccVolts", 0), ("clockHz", True), ("temperatureC", float("nan")),
                           ("fuses", {"low": 256, "high": 255, "lock": 255}), ("instrument", {})):
            with self.subTest(key=key), self.assertRaises(ValueError):
                decoder.measurements({**conditions, key: value})

    def test_cli_provenance_and_hardware_conditions_required(self):
        build = Path(__file__).resolve().parents[3] / "build" / "hardware-protocol-test"
        build.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="wire-", dir=build) as temporary:
            folder = Path(temporary)
            self.assertTrue(folder.resolve().is_relative_to(build.resolve()))
            source = folder / "actual.S"
            source.write_text("/* synthetic source identity */\n", encoding="utf-8")
            config = folder / "config.json"
            config.write_text(json.dumps({**CONFIG, "profiles": [PROFILE]}), encoding="utf-8")
            waveform = folder / "wave.csv"
            capture = rows(bits(frame()))
            with waveform.open("w", newline="", encoding="utf-8") as output:
                writer = csv.DictWriter(output, fieldnames=capture[0].keys())
                writer.writeheader()
                writer.writerows(capture)
            command = [sys.executable, str(Path(decoder.__file__)), str(waveform), "--config", str(config),
                       "--profile", PROFILE["id"], "--source", str(source), "--capture-kind"]
            run = subprocess.run([*command, "synthetic"], capture_output=True, text=True, check=True)
            result = json.loads(run.stdout)
            self.assertEqual(result["status"], "synthetic-decoder-test")
            self.assertEqual(result["identities"]["sourceSha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            rejected = subprocess.run([*command, "hardware"], capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("--measurements", rejected.stderr)


if __name__ == "__main__":
    unittest.main()

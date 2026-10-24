"""Actual EEPROM/Flash crossover, canonical stream limits, and EEPROM provenance."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_core import pack_stream

spec = importlib.util.spec_from_file_location('test_rounded_eeprom_builder', ROOT/'tools/build-q3-rounded-eeprom.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def full_frames(count):
    return [[40, 1 | ((i % 4) << 4), *([0x79 if i % 2 else 0x97]*4)] for i in range(count)]


def fixtures():
    # 9 compact full frames=54 bytes, extended full=7, repeat=2. An
    # extended-duration header begins at offset63, its pitch byte in Flash64.
    frames = full_frames(10)
    frames[-1][0] = 90
    frames += [[40, 2, *frames[-1][2:]], [90, 0x11, 0x88, 0x88, *frames[-1][4:]],
               [40, 0x21, 0x88, 0x88, 0x79, 0x79]]
    durations = [64]*11+[192, 128]
    yield 'extended-header-at-63', np.array(frames, np.uint8), np.array(durations, np.uint16)
    # Ten full frames=60 bytes; the low-half update fills bytes60..63.
    # The entire speech stream is in EEPROM and EOF is the first Flash byte.
    frames = full_frames(10)
    frames += [[40, 1, 0x88, 0x88, *frames[-1][4:]]]
    yield 'eof-at-first-flash-byte', np.array(frames, np.uint8), np.array([64]*11, np.uint16)
    # Full coefficient update at60 spans the boundary (coefficients62..65).
    # 105 compact full frames plus one extended full frame=637 bytes exactly.
    frames = full_frames(106)
    frames[-1][0] = 90
    yield 'maximum-637-byte-stream', np.array(frames, np.uint8), np.array([64]*105+[192], np.uint16)


class RoundedEepromTests(unittest.TestCase):
    def test_fixture_boundaries_and_maximum_budget_are_real_serialized_offsets(self):
        cases = {name:pack_stream(f, d) for name, f, d in fixtures()}
        self.assertEqual(cases['extended-header-at-63'][63:65], bytes([0xc3, 90]))
        self.assertEqual(len(cases['eof-at-first-flash-byte']), 64)
        self.assertEqual(len(cases['maximum-637-byte-stream']), 637)
        self.assertEqual(builder.MAX_STREAM_BYTES, 637)
        self.assertEqual(builder.CORE_BYTES+637-64+1, 1024)
        self.assertEqual(builder.FLOOR_MAX_STREAM_BYTES, 639)
        self.assertEqual(builder.FLOOR_CORE_BYTES+639-64+1, 1024)

    def test_out_of_budget_trailing_data_sample_mismatch_and_unstable_coefficients_reject(self):
        build = ROOT/'build'
        build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='test-q3-ee-', dir=build) as temporary:
            self.assertTrue(Path(temporary).resolve().is_relative_to(build.resolve()))
            stream = Path(temporary)/'speech.hq'
            cases = list(fixtures())
            _, f, d = cases[-1]
            payload = pack_stream(f, d)
            for raw in (payload[:63], payload+b'\0'):
                stream.write_bytes(raw)
                with self.assertRaisesRegex(ValueError, '64..637'):
                    builder.load_stream(stream, int(d.sum()))
            stream.write_bytes(payload)
            with self.assertRaisesRegex(ValueError, 'complete requested'):
                builder.load_stream(stream, int(d.sum())+64)
            with self.assertRaisesRegex(ValueError, 'positive complete'):
                builder.load_stream(stream, True)
            f = f.copy()
            f[0, 2] = 0x80
            stream.write_bytes(pack_stream(f, d))
            with self.assertRaisesRegex(ValueError, 'coefficient -8'):
                builder.load_stream(stream, int(d.sum()))

    def test_three_engine_execution_across_both_split_kinds_and_eof(self):
        suffix = '.exe' if os.name == 'nt' else ''
        avr = Path(os.environ.get('AVR_BIN', ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node = Path(os.environ.get('NODE', ROOT.parents[1]/('build/toolchains/node-22.22.3/node'+suffix)))
        if not (avr/('avr-gcc'+suffix)).exists() or not node.exists():
            self.skipTest('Set AVR_BIN and NODE to the repository toolchains')
        output = ROOT/'build/q3-rounded-eeprom-validation'
        output.mkdir(parents=True, exist_ok=True)
        for rounded in (True, False):
          for fixture_name, frames, durations in fixtures():
            name = ('rounded-' if rounded else 'floor-')+fixture_name
            if not rounded and fixture_name == 'maximum-637-byte-stream':
                repeat = frames[-1].copy()
                repeat[0] = 40
                frames = np.vstack((frames, repeat))
                durations = np.r_[durations, np.uint16(64)]
            with self.subTest(name=name):
                payload = pack_stream(frames, durations)
                source = output/(name+'.hq')
                source.write_bytes(payload)
                destination = output/name
                report = builder.build(source, destination, avr, node, expected_samples=int(durations.sum()), rounded=rounded)
                self.assertEqual(report['status'], 'verified', json.dumps(report.get('verification')))
                self.assertEqual(report['codeBytes'], 450 if rounded else 448)
                self.assertEqual(report['eepromUsedBytes'], 64)
                self.assertEqual(report['streamFlashBytes'], len(payload)-64)
                self.assertEqual((destination/'eeprom.bin').read_bytes(), payload[:64])
                self.assertEqual(report['eepromSha256'], builder.sha(payload[:64]))
                self.assertEqual(report['verification']['eepromSha256'], report['eepromSha256'])
                self.assertEqual(report['verification']['mismatches'], 0)
                self.assertEqual(report['verification']['missedSamples'], 0)
                self.assertEqual(report['verification']['lostOverflows'], 0)
                self.assertEqual(report['verification']['engines'], ['reference','wasm','wasm-unoptimized'])
                self.assertEqual(report['verification']['verifiedSamples'], int(durations.sum())*3)
                self.assertEqual(report['silenceSamplesVerified'], int(durations.sum())*2)
                self.assertLessEqual(report['flashBytes'], 1024)
                if len(payload) == (637 if rounded else 639):
                    self.assertEqual(report['flashBytes'], 1024)
                if len(payload) == 64:
                    self.assertEqual(report['flashBytes'], 452 if rounded else 450)


if __name__ == '__main__':
    unittest.main()

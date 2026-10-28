"""Focused prototype checks; generated streams/binaries stay in ignored build/."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(HERE), str(ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'),
               str(ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC/tests')]
import numpy as np
import speech_compact as compact
from batch_decoder import BatchDecoder, BatchSession
from benchmark_speech_flash import source_hashes
from lpx4 import BitWriter
from materialize import materialize
from scale_repeat import from_v5, to_v5
from speech_parameter_costs import METHODS, stream_cost
from standard_metrics import pwm_duties
from test_speech_parameter_costs import zero_amplitude_marker
from test_speech_v4 import fixture
import reference


def unusual_source(profile, n=641):
    """Legal deliberately noncanonical spectra/markers and aliased raw scales."""
    original = compact.repack(fixture(profile, n))[0]
    values = compact.unpack(original)
    header = bytearray(original[:20])
    header[5] |= 128
    writer = BitWriter()
    for frame, spectrum in enumerate(values[2]):
        writer.put(1, 1)
        writer.put(0, 1)
        last = -1
        for value in spectrum:
            # Force full absolute escapes even when ordinary Rice is shorter.
            writer.put(0, 8)
            writer.put(value - last - 1, 5 if profile == 4 else 6)
            last = value
        for half in range(2):
            index = 2 * frame + half
            scale = (index // 2) % 32
            writer.put(scale, 5)
            writer.put(0 if index % 2 else 127, 7)
            writer.put(0, 3)
            for chunk in range(4):
                a, b = values[4][16 * frame + 8 * half + 2 * chunk:16 * frame + 8 * half + 2 * chunk + 2]
                if profile == 4:
                    for pos, amp in (a, b):
                        writer.put(list(compact.v4.POSITIONS4).index(pos), 4)
                        writer.put(int(amp > 0), 1)
                else:
                    pair = a[0] + 20 * b[0]
                    writer.put(pair & 255, 8)
                    writer.put(pair >> 8, 1)
                    writer.put(a[1] & 15, 4)
                    writer.put(b[1] & 15, 4)
                marker = frame == half == chunk == 0
                writer.put(int(marker), 1)
                if marker:
                    writer.put(39, 6)
                    writer.put(0, 4)
    writer.aligned()
    payload = writer.get()
    return bytes(header) + struct.pack('<H', len(payload)) + payload


def build_native(source, output, only, extra=()):
    subprocess.run(['g++', '-O2', '-std=c++11', '-shared', '-fPIC',
                    '-DLPX4_ENABLE_SPEECH=1', '-DLPX4_ENABLE_SPEECH_COMPACT=1',
                    '-DLPX4_ENABLE_ASM=0', '-DLPX4_COMPACT_ONLY=' + str(only),
                    *extra, '-I' + str(source), str(source / 'Lpx4HybridCore.cpp'),
                    str(source / 'native_batch_decoder.cpp'), '-o', str(output)],
                   check=True, capture_output=True)
    return BatchDecoder(output)


class ScaleRepeatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / 'build').mkdir(exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=ROOT / 'build', ignore_cleanup_errors=True)
        cls.folder = Path(cls.temporary.name)
        cls.source, cls.receipt = materialize(cls.folder / 'derived')
        cls.new = [build_native(cls.source, cls.folder / ('new-' + str(only) + '.dll'), only) for only in (0, 1)]
        cls.sessions = [BatchSession('batch', speech=True, speech_compact=True, compact_only=bool(only)) for only in (0, 1)]
        cls.old = [session.__enter__() for session in cls.sessions]

    @classmethod
    def tearDownClass(cls):
        for session in cls.sessions:
            session.__exit__()
        cls.temporary.cleanup()

    def test_byte_roundtrip_parameter_and_charged_size(self):
        for profile in (4, 6):
            for n in (1, 19, 20, 159, 160, 161, 319, 320, 321, 641, 64000):
                base = compact.repack(fixture(profile, n), force_extras=True)[0]
                for old in (base, unusual_source(profile, n)):
                    new = from_v5(old)
                    self.assertEqual(new[:5], b'L4HY\x06')
                    self.assertEqual(new[22], 1)
                    self.assertEqual(len(new) - 22, int.from_bytes(new[20:22], 'little'))
                    self.assertEqual(to_v5(new), old)
                    independent, params = reference.restore_v5(new)
                    self.assertEqual(independent, old)
                    self.assertEqual(params, compact.unpack(old)[3])
                    self.assertEqual(len(new), stream_cost(old, METHODS[0])['proposed_file_bytes'])
            source, _ = zero_amplitude_marker(profile)
            self.assertEqual(to_v5(from_v5(source)), source)

    def test_exact_pcm_pwm_common_compact_and_explicit_reference_adapter(self):
        for profile in (4, 6):
            for n in (1, 160, 180, 320, 321, 641, 64000):
                ordinary = compact.unpack(compact.repack(fixture(profile, n))[0])
                extras = [(i % 40, (-1 if i & 1 else 1) * (1 + i % 7)) for i in range(len(ordinary[7]))]
                active = compact.pack(*ordinary[:7], extras=extras, force_extras=True)[0]
                for old in (unusual_source(profile, n), active):
                    new = from_v5(old)
                    expected = compact.decode_model(old)
                    np.testing.assert_array_equal(reference.decode_model(new), expected)
                    for baseline, experimental in zip(self.old, self.new):
                        self.assertIsNone(baseline.decode_one_s16(new, n))
                        self.assertIsNone(experimental.decode_one_s16(old, n))
                        np.testing.assert_array_equal(baseline.decode_one_s16(old, n), expected)
                        np.testing.assert_array_equal(experimental.decode_one_s16(new, n), expected)
                        np.testing.assert_array_equal(experimental.decode_one(new, n), pwm_duties(expected))

    def test_selector_bounds_truncation_and_sticky_reader_errors(self):
        original = unusual_source(6, 640)
        source = from_v5(original)
        for selector in (0, 2, 255):
            bad = bytearray(source)
            bad[22] = selector
            with self.assertRaises(ValueError):
                to_v5(bad)
            with self.assertRaises(ValueError):
                reference.restore_v5(bad)
            for decoder in self.new:
                self.assertIsNone(decoder.decode_one_s16(bytes(bad), 640))
        for cut in range(len(source)):
            bad = bytearray(source[:cut])
            if len(bad) >= 22:
                bad[20:22] = (len(bad) - 22).to_bytes(2, 'little')
            with self.assertRaises(ValueError):
                to_v5(bad)
            with self.assertRaises(ValueError):
                reference.restore_v5(bad)
            for decoder in self.new:
                self.assertIsNone(decoder.decode_one_s16(bytes(bad), 640))
        for offset, value, width in ((8, 0, 4), (8, 64001, 4), (8, 0xffffffff, 4), (12, 16385, 2), (14, 11470, 2), (16, 160, 2), (18, 80, 2)):
            bad = bytearray(source)
            bad[offset:offset + width] = value.to_bytes(width, 'little')
            for decoder in self.new:
                self.assertIsNone(decoder.decode_one_s16(bytes(bad), 640))

    def test_lag_sentinel_copy_reset_error_and_storage_alternatives(self):
        source = self.folder / 'lifecycle-stream.bin'
        source.write_bytes(from_v5(unusual_source(6, 641)))
        for only in (0, 1):
            for flags in ((), ('-DLPX4_ROM_POINTER=0', '-DLPX4_EXCITATION_Q4=0', '-DLPX4_BATCHED_REMAINING=0', '-DLPX4_LPC_RING=0', '-DLPX4_ROTATE_LPC_ANCHORS=0')):
                target = self.folder / ('lifecycle-' + str(only) + '-' + str(len(flags)) + '.exe')
                subprocess.run(['g++', '-O2', '-std=c++11', '-DLPX4_ENABLE_SPEECH=1',
                                '-DLPX4_ENABLE_SPEECH_COMPACT=1', '-DLPX4_ENABLE_ASM=0',
                                '-DLPX4_COMPACT_ONLY=' + str(only), *flags,
                                '-I' + str(self.source), str(self.source / 'Lpx4HybridCore.cpp'),
                                str(HERE / 'lifecycle.cpp'), '-o', str(target)], check=True, capture_output=True)
                result = subprocess.run([str(target), str(source)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_frozen_source_and_derived_tamper_guards(self):
        source, _ = materialize(self.folder / 'derived')
        self.assertEqual(source_hashes(ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC/src'), self.receipt['production_source_sha256'])
        self.assertEqual(source_hashes(source), self.receipt['derived_source_sha256'])
        with self.assertRaises(ValueError):
            materialize(ROOT / 'outside-build')
        target = self.folder / 'derived/provenance.json'
        original = target.read_bytes()
        target.write_bytes(b'{}')
        with self.assertRaises(ValueError):
            materialize(self.folder / 'derived')
        target.write_bytes(original)


if __name__ == '__main__':
    unittest.main(verbosity=2)

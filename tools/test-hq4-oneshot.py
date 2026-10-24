"""Experimental HQ4 stream admission without compiling or touching a release."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hq4_oneshot', ROOT/'tools/build-hq4-oneshot.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class CandidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retained = builder.CODEC/'release/vinni/speech.hq'
        cls.payload = cls.retained.read_bytes()
        cls.frames, cls.durations = builder.validate_stream(cls.payload)
        cls.scratch = ROOT/'build/hq4-candidate-tests'
        cls.scratch.mkdir(parents=True, exist_ok=True)

    def test_default_retains_frozen_numerical_pcm_guard(self):
        source, payload, phrase, frozen_sha = builder.load_stream('vinni')
        self.assertEqual(source, self.retained)
        self.assertEqual(payload, self.payload)
        self.assertEqual(len(phrase), 22272)
        self.assertEqual(builder.sha(phrase.tobytes()), frozen_sha)
        changed = phrase.copy()
        changed[0] ^= 1
        with patch.object(builder, 'decode', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'retained real AVR recording'):
                builder.load_stream('vinni')

    def test_explicit_candidate_allows_changed_pcm(self):
        # The first spectral header's gain changes while frame lengths stay fixed.
        changed = bytearray(self.payload)
        header_offset = 2 if changed[0] & 0xc0 == 0xc0 else 1
        changed[header_offset] ^= 1
        with tempfile.TemporaryDirectory(prefix='hq4-candidate-', dir=self.scratch) as directory:
            candidate = Path(directory)/'speech.hq'
            candidate.write_bytes(changed)
            source, payload, phrase, frozen_sha = builder.load_stream('vinni', candidate)
        self.assertEqual(source, candidate.resolve())
        self.assertEqual(payload, changed)
        self.assertEqual(len(phrase), 22272)
        self.assertIsNone(frozen_sha)
        original = builder.decode(self.frames, self.durations, 0)
        self.assertFalse(np.array_equal(phrase, original))
        self.assertEqual(self.retained.read_bytes(), self.payload)

    def test_candidate_cannot_shorten_or_extend_the_retained_phrase(self):
        with tempfile.TemporaryDirectory(prefix='hq4-candidate-', dir=self.scratch) as directory:
            candidate = Path(directory)/'speech.hq'
            candidate.write_bytes(bytes((64, 0, 128, 128, 128, 128)))
            with self.assertRaisesRegex(ValueError, 'complete phrase duration'):
                builder.load_stream('vinni', candidate)

    def test_candidate_rejects_flash_overflow_before_compilation(self):
        with tempfile.TemporaryDirectory(prefix='hq4-candidate-', dir=self.scratch) as directory:
            candidate = Path(directory)/'speech.hq'
            candidate.write_bytes(self.payload+bytes((64, 64)))
            with self.assertRaisesRegex(ValueError, '617-byte Flash budget'):
                builder.load_stream('vinni', candidate)

    def test_candidate_rejects_truncated_frames_invalid_pitch_and_eof(self):
        malformed = (b'', b'\xc1', b'\x40', b'\x40\x00\x88',
                     b'\xc1\x7f\x00\x88\x88\x88\x88',
                     b'\xc4\x01\x00\x88\x88\x88\x88',
                     b'\x40\x40', self.payload+b'\xff',
                     self.payload+b'\xff\x00', self.payload[:-1])
        for payload in malformed:
            with self.subTest(payload=payload[:8]):
                with self.assertRaises(ValueError):
                    builder.validate_stream(payload)

    def test_new_recording_needs_explicit_complete_sample_count(self):
        with tempfile.TemporaryDirectory(prefix='hq4-new-', dir=self.scratch) as directory:
            candidate = Path(directory)/'speech.hq'
            candidate.write_bytes(bytes((64, 0, 136, 136, 136, 136)))
            source, payload, phrase, frozen_sha = builder.load_stream('new-phrase', candidate, 64)
            self.assertEqual(len(phrase), 64)
            self.assertIsNone(frozen_sha)
            for invalid in (0, -64, 65, True):
                with self.assertRaisesRegex(ValueError, 'multiple-of-64'):
                    builder.load_stream('new-phrase', candidate, invalid)
            with self.assertRaisesRegex(ValueError, 'complete phrase duration'):
                builder.load_stream('new-phrase', candidate, 128)
            with self.assertRaisesRegex(ValueError, 'explicit stream'):
                builder.load_stream('new-phrase', None, 64)


if __name__ == '__main__':
    unittest.main()

"""Prevent nearly silent output when wider integer PWM samples are exported."""
from pathlib import Path
import tempfile
import unittest
import wave

import numpy as np

from pcm16_wav import write_pcm16_wav


class Pcm16WavTests(unittest.TestCase):
    def test_wider_integer_units_preserve_amplitude_and_sign(self):
        expected = np.array([-32768, -8192, -256, -1, 0, 1, 256, 8192, 32512, 32767], np.int32)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'listening.wav'
            for dtype in (np.int16, np.int32, np.int64):
                source = expected.astype(dtype)
                write_pcm16_wav(path, source)
                with wave.open(str(path), 'rb') as result:
                    self.assertEqual(result.getparams()[:4], (1, 2, 8000, len(expected)))
                    actual = np.frombuffer(result.readframes(len(expected)), dtype='<i2')
                np.testing.assert_array_equal(actual, expected)
                np.testing.assert_array_equal(source, expected)
            self.assertEqual(list(Path(folder).glob('*.partial')), [])

    def test_invalid_units_preserve_an_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'keep.wav'
            path.write_bytes(b'preserve')
            for invalid in (np.array([0.5]), np.array([32768]), np.array([-32769]),
                            np.array([], np.int16), np.zeros((2, 2), np.int16)):
                with self.assertRaises(ValueError):
                    write_pcm16_wav(path, invalid)
                self.assertEqual(path.read_bytes(), b'preserve')


if __name__ == '__main__':
    unittest.main()

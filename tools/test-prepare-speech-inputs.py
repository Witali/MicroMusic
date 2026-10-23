"""Full-duration preprocessing, normalization and source provenance contracts."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np
import soundfile as sf

PATH = Path(__file__).with_name('prepare-speech-inputs.py')
spec = importlib.util.spec_from_file_location('prepare_speech_inputs', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InputTests(unittest.TestCase):
    def test_full_stereo_duration_preserved_and_hashed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rate = 16000
            t = np.arange(16001)/rate
            audio = .2*np.sin(2*np.pi*180*t)+.01
            source = root/'external.wav'
            sf.write(source, np.c_[audio, audio*.8], rate, subtype='PCM_16')
            report = module.prepare(source, root/'reference')
            got, sr = sf.read(root/'reference/reference.wav')
            self.assertEqual(report['source_samples'], len(audio))
            self.assertEqual(report['source_sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(sr, 7500)
            self.assertEqual(len(got)%64, 0)
            self.assertLess(report['trailing_zero_padding_samples'], 64)
            self.assertGreaterEqual(report['unpadded_samples']/sr, len(audio)/rate)
            self.assertLess(abs(max(abs(got))-.85), .00004)
            self.assertFalse(report['speech_cropped'])
            self.assertEqual(len(got), report['reference_samples'])

    def test_silent_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'silent.wav'
            sf.write(source, np.zeros(7500), 7500)
            with self.assertRaisesRegex(ValueError, 'silent'):
                module.prepare(source, root/'result')


if __name__ == '__main__':
    unittest.main()

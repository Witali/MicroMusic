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
    @classmethod
    def setUpClass(cls):
        cls.temporary_root = (PATH.resolve().parents[1]/'build/speech-input-tests').resolve()
        if not cls.temporary_root.is_relative_to(PATH.resolve().parents[1]):
            raise ValueError('Temporary fixtures must stay in the workspace')
        cls.temporary_root.mkdir(parents=True, exist_ok=True)

    def test_full_stereo_duration_preserved_and_hashed(self):
        with tempfile.TemporaryDirectory(dir=self.temporary_root) as directory:
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
        with tempfile.TemporaryDirectory(dir=self.temporary_root) as directory:
            root = Path(directory)
            source = root/'silent.wav'
            sf.write(source, np.zeros(7500), 7500)
            with self.assertRaisesRegex(ValueError, 'silent'):
                module.prepare(source, root/'result')

    def test_explicit_excerpt_records_original_time_range(self):
        with tempfile.TemporaryDirectory(dir=self.temporary_root) as directory:
            root = Path(directory)
            source = root/'source.wav'
            t = np.arange(15000)/7500
            sf.write(source, .3*np.sin(2*np.pi*150*t), 7500)
            report = module.prepare(source, root/'tail', start_seconds=1.2)
            self.assertTrue(report['speech_cropped'])
            self.assertEqual(report['source_samples'], 15000)
            self.assertEqual(report['selection_start_seconds'], 1.2)
            self.assertEqual(report['selection_end_seconds'], 2.)
            self.assertEqual(report['unpadded_samples'], 6000)


if __name__ == '__main__':
    unittest.main()

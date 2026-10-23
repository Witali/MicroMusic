"""Separate flat quantized peaks, actual byte overflow and WAV alterations."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('audit_speech_clipping', ROOT/'tools/audit-speech-clipping.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SpeechClippingTests(unittest.TestCase):
    def test_flat_peaks_measured_at_observed_extrema_below_dac_limits(self):
        values = np.array([0, .125, .25, .25, .25, .125, 0, -.25, -.25, 0])
        stats = module.signal_stats(values)
        self.assertEqual(stats['observed_maximum']['maximum_equal_run'], 3)
        self.assertEqual(stats['observed_minimum']['maximum_equal_run'], 2)
        self.assertEqual(stats['local_positive_plateaus_ge2'], 1)
        self.assertEqual(stats['local_negative_plateaus_ge2'], 1)
        self.assertEqual(stats['samples_abs_ge_one'], 0)
        self.assertEqual(stats['unique_levels'], 4)

    def test_quantized_monotonic_steps_are_not_local_peak_plateaus(self):
        stats = module.signal_stats(np.repeat(np.arange(-3, 4)/128, 3))
        self.assertEqual(stats['local_positive_plateaus_ge2'], 0)
        self.assertEqual(stats['local_negative_plateaus_ge2'], 0)
        self.assertEqual(stats['observed_maximum']['maximum_equal_run'], 3)
        self.assertEqual(stats['unique_levels'], 7)

    def fixture(self, root, frames):
        frames = np.asarray(frames, np.uint8)
        durations = np.full(len(frames), 256, np.uint16)
        pcm = module.decode(frames, durations, 0)
        reference = root/'reference.wav'
        sf.write(reference, .1*np.sin(np.arange(len(pcm))*.1), 7500, subtype='FLOAT')
        entry = dict(id='fixture', language='ru', voice='male', condition='natural', source_id='fixture',
            reference='reference.wav', reference_sha256=module.sha(reference))
        model = dict(schema='hq4-corpus-baseline-v1', reference_sha256=entry['reference_sha256'],
            sample_rate=7500, frames=frames.tolist(), durations=durations.tolist())
        path = root/'model.json'
        path.write_text(json.dumps(model), encoding='utf-8')
        (root/'speech.hq').write_bytes(module.pack_stream(frames, durations))
        (root/'expected.raw').write_bytes(pcm.tobytes())
        sf.write(root/'decoded.wav', (pcm.astype(float)-128)/128, 7500, subtype='FLOAT')
        return path, entry

    def test_independent_exact_byte_and_float_wav_checks_detect_rescaling(self):
        (ROOT/'build').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
            root = Path(directory)
            path, entry = self.fixture(root, [[40, 5, 0x88, 0x88, 0x88, 0x88]])
            report = module.audit_model(path, entry, root)
            self.assertTrue(report['exact_oracle_equal'])
            self.assertTrue(report['float_wav_sample_exact'])
            self.assertEqual(report['arithmetic']['subtraction_wraps'], 0)
            audio, rate = sf.read(root/'decoded.wav')
            sf.write(root/'decoded.wav', audio*.5, rate, subtype='FLOAT')
            with self.assertRaisesRegex(AssertionError, 'altered, clipped or rescaled'):
                module.audit_model(path, entry, root)

    def test_internal_wraps_are_detected_even_with_valid_float_wav_conversion(self):
        (ROOT/'build').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
            root = Path(directory)
            path, entry = self.fixture(root, [[40,15,0,255,193,115], [21,15,83,113,192,104],
                [42,15,8,104,39,88], [2,15,210,163,99,208]])
            report = module.audit_model(path, entry, root)
            audit = report['arithmetic']
            self.assertGreater(audit['subtraction_wraps']+audit['state_addition_wraps'], 0)
            self.assertTrue(report['float_wav_sample_exact'])


if __name__ == '__main__':
    unittest.main()

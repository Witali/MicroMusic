"""Output arithmetic, portable packed data and truthful adapter status."""
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from colored_period import decode_colored
from fixed_period import decode_fixed, from_colored
from speech_targets import c_data_header, decode_for_profile, export_model, resolve_profile


class TargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads((ROOT/'ATtiny13A/Sound/research/period-balanced/chego/model.json').read_text(encoding='utf-8'))
        cls.fixed = from_colored(cls.source)

    def test_encoder_objective_hears_exact_selected_arithmetic(self):
        floating = decode_for_profile(self.source, resolve_profile())
        self.assertTrue(np.array_equal(floating, decode_colored(self.source)))
        expected = (decode_fixed(self.fixed).astype(np.float64)-128)/128
        for target, kwargs in [('pc', dict(arithmetic='fixed')), ('avr', dict(mcu='attiny13')),
                               ('mcu', dict(mcu='another-controller'))]:
            actual = decode_for_profile(self.fixed, resolve_profile(target, **kwargs))
            self.assertTrue(np.array_equal(actual, expected))

    def test_invalid_profiles_cannot_silently_change_rate_or_arithmetic(self):
        with self.assertRaisesRegex(ValueError, 'fixed arithmetic'):
            resolve_profile('avr', 'float')
        with self.assertRaisesRegex(ValueError, '7500'):
            resolve_profile('mcu', custom_profile=dict(schema='speech-output-profile-v1', sample_rate=16000))
        with self.assertRaisesRegex(ValueError, 'positive integer'):
            resolve_profile('mcu', custom_profile=dict(schema='speech-output-profile-v1', sram_bytes=-1))
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            resolve_profile('mcu', custom_profile=dict(schema='speech-output-profile-v1', imaginary_limit=12))
        with self.assertRaisesRegex(ValueError, 'identifier'):
            c_data_header(b'abcd', 'unsafe-name')
        with self.assertRaisesRegex(ValueError, 'no inverse'):
            decode_for_profile(self.fixed, resolve_profile())

    def test_pc_float_export_preserves_unscaled_pcm(self):
        with tempfile.TemporaryDirectory(prefix='speech-target-', dir=ROOT/'build') as directory:
            output = Path(directory)
            report = export_model(self.source, output, resolve_profile())
            raw = np.frombuffer((output/'speech.f32').read_bytes(), dtype='<f4')
            self.assertTrue(np.array_equal(raw, decode_colored(self.source).astype('<f4')))
            self.assertEqual(report['validation']['firmware'], 'not_built')
            self.assertIsNone(report['validation']['total_flash_bytes'])
            self.assertFalse((output/'speech_data.h').exists())

    def test_mcu_header_roundtrips_and_wav_is_exact_dac_pcm(self):
        from fixed_period import decode_fixed, unpack_fixed
        profile = resolve_profile('mcu', mcu='small-test-chip', custom_profile=dict(
            schema='speech-output-profile-v1', flash_bytes=100, sram_bytes=16, cpu_hz=1000000))
        with tempfile.TemporaryDirectory(prefix='speech-target-', dir=ROOT/'build') as directory:
            output = Path(directory)
            report = export_model(self.fixed, output, profile)
            payload = (output/'speech.bin').read_bytes()
            header_bytes = bytes(int(value, 16) for value in re.findall(r'0x([0-9a-f]{2})', (output/'speech_data.h').read_text()))
            self.assertEqual(header_bytes, payload)
            self.assertTrue(np.array_equal(decode_fixed(unpack_fixed(payload)), decode_fixed(self.fixed)))
            with wave.open(str(output/'speech.wav'), 'rb') as handle:
                self.assertEqual((handle.getnchannels(), handle.getsampwidth(), handle.getframerate()), (1, 1, 7500))
                self.assertEqual(handle.readframes(handle.getnframes()), (output/'speech.u8').read_bytes())
            self.assertFalse(report['validation']['flash_data_fits'])
            self.assertIsNone(report['validation']['sram_bytes'])
            self.assertFalse(report['validation']['timing_verified'])

    def test_build_requires_real_adapter_and_keeps_failure_evidence(self):
        with tempfile.TemporaryDirectory(prefix='speech-target-', dir=ROOT/'build') as directory:
            folder = Path(directory)
            missing = resolve_profile('mcu', custom_profile=dict(schema='speech-output-profile-v1', adapter=str(folder/'missing.py')))
            with self.assertRaises(FileNotFoundError):
                export_model(self.fixed, folder/'missing', missing, build=True)
            saved = json.loads((folder/'missing/manifest.json').read_text())
            self.assertEqual(saved['validation']['firmware'], 'not_built')
            adapter = folder/'failure.py'
            adapter.write_text("import sys\nprint('deliberate adapter failure')\nsys.exit(3)\n", encoding='utf-8')
            failing = resolve_profile('mcu', custom_profile=dict(schema='speech-output-profile-v1', adapter=str(adapter)))
            with self.assertRaisesRegex(RuntimeError, 'adapter failed'):
                export_model(self.fixed, folder/'failure', failing, build=True)
            saved = json.loads((folder/'failure/manifest.json').read_text())
            self.assertEqual(saved['validation']['firmware'], 'build_failed')
            self.assertEqual(saved['adapter_returncode'], 3)
            self.assertIn('deliberate', (folder/'failure/build.log').read_text())


if __name__ == '__main__':
    (ROOT/'build').mkdir(exist_ok=True)
    unittest.main()

"""A decoded sidecar must never replace the encoder's original WAV input."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
import warnings
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_beam_excitation import raw_fixture
from optimize_q0 import run as joint_run
from optimize_old_lpc import run as legacy_run
from global_rate_pcm16 import run as global_run
from wav_to_lpx4 import run as wav_run
from output_paths import protect_outputs


class OutputCollisionTests(unittest.TestCase):
    def test_sidecar_cannot_overwrite_reference_wav(self):
        runners = [(joint_run, {'lsf_trials': 0, 'beam_trials': 0, 'header_trials': 0}),
                   (legacy_run, {'lsf_trials': 0, 'excitation_trials': 0, 'header_trials': 0}),
                   (global_run, {'rounds': 1, 'max_candidates': 1})]
        for runner, options in runners:
            with self.subTest(tool=runner.__module__), tempfile.TemporaryDirectory() as td:
                p = Path(td)
                source = p / 'source.l4hy';source.write_bytes(raw_fixture(samples=4800))
                wav = p / 'reference.wav'
                sf.write(wav, np.ones(4800, np.int16), 8000, subtype='PCM_16')
                original = wav.read_bytes()
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', RuntimeWarning)
                    with self.assertRaises(ValueError):
                        runner(source, wav, p / 'reference.l4hy', **options)
                self.assertEqual(wav.read_bytes(), original)
                self.assertFalse((p / 'reference.l4hy').exists())

    def test_wav_encoder_cannot_replace_its_own_input_preview(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td);wav = p / 'decoded.wav'
            sf.write(wav, np.arange(160, dtype=np.int16), 8000, subtype='PCM_16')
            original = wav.read_bytes()
            with self.assertRaises(ValueError):
                wav_run(wav, p, kind='music', lambdas=(0.,))
            self.assertEqual(wav.read_bytes(), original)
            self.assertFalse((p / 'manifest.json').exists())

    def test_primary_output_cannot_also_be_its_decoded_sidecar(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td);source = p / 'source.l4hy';wav = p / 'reference.wav'
            source.write_bytes(raw_fixture(samples=4800))
            sf.write(wav, np.zeros(4800, np.int16), 8000, subtype='PCM_16')
            with self.assertRaises(ValueError):
                joint_run(source, wav, p / 'output.wav', lsf_trials=0, beam_trials=0, header_trials=0)
            self.assertFalse((p / 'output.wav').exists())

    def test_hard_link_alias_is_protected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td);source = p/'input.wav';output = p/'output.wav'
            source.write_bytes(b'original source')
            try:
                os.link(source, output)
            except (PermissionError, NotImplementedError):
                self.skipTest('This filesystem/session cannot create hard links')
            with self.assertRaises(ValueError):
                protect_outputs([source], [output])
            self.assertEqual(source.read_bytes(), b'original source')

    def test_explicit_in_place_codec_output_remains_available(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td);source = p/'source.l4hy';wav = p/'reference.wav'
            source.write_bytes(b'codec');wav.write_bytes(b'reference')
            protect_outputs([source,wav], [source,p/'source.wav',p/'source.json'], replace=(source,source))


if __name__ == '__main__':
    unittest.main()

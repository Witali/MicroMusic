"""Host layout and optional pinned-native bridge contracts before pilot search."""
from pathlib import Path
import os
import random
import sys
import tempfile
import unittest

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import encode_meta320 as encoder
import speech_meta320 as meta
import speech_compact as compact
import speech_sparse80 as sparse
from batch_decoder import BatchDecoder
from standard_metrics import pwm_duties


class LayoutContracts(unittest.TestCase):
    def test_adaptive_cost_and_lower_density_complete_packets(self):
        rng = np.random.default_rng(90320)
        desired = np.asarray([sorted(rng.choice(32, 10, replace=False)) for _ in range(60)])
        reference = rng.integers(-4000, 4000, 19200, dtype=np.int16)
        spectra = encoder.adaptive_spectra(reference, desired, 900)
        self.assertIsNotNone(spectra)
        blob = meta.pack(len(reference), spectra.tolist(), [(0, 18, 0)]*60, [(0, -8)]*960)
        self.assertEqual(len(blob), encoder.layout_bytes(spectra))
        self.assertLessEqual(len(blob), 900)
        for cadence in (2, 4, 8):
            held = np.asarray([desired[(i//cadence)*cadence] for i in range(60)])
            packed = meta.pack(len(reference), held.tolist(), [(0, 18, 0)]*60, [(0, -8)]*960)
            self.assertEqual(len(packed), encoder.layout_bytes(held))


@unittest.skipUnless(os.environ.get('LPX_META_COMMON') and os.environ.get('LPX_META_V5_ONLY'),
                     'Supply pinned common/v5-only native libraries')
class NativeBridgeContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.common = BatchDecoder(Path(os.environ['LPX_META_COMMON']))
        cls.only = BatchDecoder(Path(os.environ['LPX_META_V5_ONLY']))

    def test_independent_native_expansion_pcm_pwm_and_tails(self):
        rng = random.Random(93120)
        for n in (1, 19, 20, 159, 160, 319, 320, 321, 639, 640, 641, 3200):
            frames = (n+319)//320
            spectra = [sorted(rng.sample(range(32), 10)) for _ in range(frames)]
            params = [(rng.randrange(32), rng.randrange(18, 146), 2*rng.randrange(8)) for _ in range(frames)]
            pulses = [(rng.choice(meta.POSITIONS), rng.choice((-8, 8))) for _ in range(frames*16)]
            blob = meta.pack(n, spectra, params, pulses, 11469, 4096 if n%2 else 0)
            bridge, modeled = meta.expand(blob), meta.decode_model(blob)
            for receiver in (self.common, self.only):
                np.testing.assert_array_equal(receiver.decode_one_s16(bridge, n), modeled)
                np.testing.assert_array_equal(receiver.decode_one(bridge, n), pwm_duties(modeled))

    def test_cross_format_protected_incumbent_and_pointer(self):
        n = 9600
        spectra, pulses = [list(range(10))]*(n//320), [(0, -8)]*(n//20)
        ordinary = compact.pack(n, 4, spectra, [(0, 18, 0)]*(n//160), pulses)[0]
        candidate = meta.pack(n, spectra, [(0, 18, 0)]*(n//320), pulses)
        temporary_root = encoder.ROOT/'build/meta320/tests'
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as temporary:
            gate = encoder.Admission(np.zeros(n, np.int16), ordinary, Path(temporary)/'admission', self.common, self.only)
            gate.add(candidate, np.zeros(n, np.int16), origin='synthetic_exact_silence', work=dict(parameter_trials=1))
            self.assertTrue(gate.rows[1]['admissible'])
            self.assertEqual(gate.best()['version'], 9)
            self.assertEqual(encoder.recover_best_checkpoint(gate.output)[0], candidate)
            gate.add(candidate, np.zeros(n, np.int16), origin='duplicate', work=dict(parameter_trials=2))
            self.assertEqual(gate.attempts[-1]['duplicate_of'], 1)

    def test_existing_sparse80_header_uses_exact_two_kbit_cap(self):
        n = 9600
        original = sparse.pack(n, [list(range(10))]*(n//320), [(0, 18, 0)]*(n//320), [(0, -8)]*(n//80))
        temporary_root = encoder.ROOT/'build/meta320/tests'
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as temporary:
            gate = encoder.Admission(np.zeros(n, np.int16), original, Path(temporary)/'admission', self.common, self.only)
            self.assertEqual(gate.cap, 300)
            changed = sparse.pack(n, [list(range(10))]*(n//320), [(0, 18, 0)]*(n//320), [(0, -8)]*(n//80), 13926, 4096)
            gate.add(changed, np.zeros(n, np.int16), origin='existing_header')
            self.assertEqual(gate.rows[-1]['version'], 8)
            self.assertEqual(changed[22:], original[22:])


if __name__ == '__main__':
    unittest.main()

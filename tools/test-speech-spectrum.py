"""Persistent spectral detail must retain duration, weak harmonics and attacks."""
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from speech_spectrum import PersistentSpectrumObjective


class PersistentSpectrumTest(unittest.TestCase):
    def setUp(self):
        self.sr = 7500
        self.t = np.arange(self.sr)/self.sr
        self.voice = .2*np.sin(2*np.pi*125*self.t)

    def test_identity_gain_and_polarity_preserve_spectrum(self):
        objective = PersistentSpectrumObjective(self.voice)
        self.assertLess(objective.evaluate(self.voice)['persistent_spectral_error'],1e-12)
        self.assertLess(objective.evaluate(-self.voice*.13)['persistent_spectral_error'],1e-12)
        self.assertLess(objective.evaluate(-self.voice*.13)['band_loss'],1e-12)
        self.assertLess(abs(objective.ridges[0]['median_hz']-125),1)

    def test_persistent_extra_frequency_is_preserved_as_soft_detail(self):
        reference = self.voice+.075*np.sin(2*np.pi*820*self.t)
        objective = PersistentSpectrumObjective(reference)
        ridges = [ridge for ridge in objective.ridges if abs(ridge['median_hz']-820)<2]
        self.assertTrue(ridges)
        self.assertGreater(max(ridge['duration_ms'] for ridge in ridges),800)
        self.assertGreater(objective.evaluate(self.voice)['persistent_spectral_error'],.01)
        self.assertGreater(objective.evaluate(self.voice)['band_shape_loss'],.01)
        bands = objective.compare_bands(self.voice)
        missing = max(bands,key=lambda item:item['missing_magnitude_energy_fraction'])
        self.assertLess(missing['low_hz'],820)
        self.assertGreater(missing['high_hz'],820)
        self.assertEqual(objective.weights.min(),1.)
        self.assertLessEqual(objective.weights.max(),3.)

    def test_short_ring_is_not_promoted_to_persistent_tone(self):
        ring = np.where((self.t>.4)&(self.t<.415),.3*np.sin(2*np.pi*820*self.t),0)
        objective = PersistentSpectrumObjective(self.voice+ring)
        self.assertFalse(any(abs(item['median_hz']-820)<5 for item in objective.ridges))
        # The transient remains part of the full objective even without a ridge.
        self.assertGreater(objective.evaluate(self.voice)['persistent_spectral_error'],.001)

    def test_disjoint_short_tones_do_not_pool_duration(self):
        ring = np.zeros_like(self.t)
        for start in (.15,.4,.65):
            active = (self.t>=start)&(self.t<start+.015)
            ring[active] = .3*np.sin(2*np.pi*820*self.t[active])
        objective = PersistentSpectrumObjective(self.voice+ring)
        self.assertFalse(any(abs(item['median_hz']-820)<5 for item in objective.ridges))

    def test_harmonic_hint_does_not_claim_noise_or_formant(self):
        objective = PersistentSpectrumObjective(self.voice+.08*np.sin(2*np.pi*500*self.t))
        centres = np.arange(0,len(self.voice),64)+32
        report = objective.diagnostics(np.full(len(centres),125.),np.ones(len(centres)),centres)
        harmonic = next(item for item in report['ridges'] if abs(item['median_hz']-500)<2)
        self.assertEqual(harmonic['interpretation'],'harmonic_context_candidate')
        self.assertGreater(harmonic['near_estimated_voice_harmonic_fraction'],.95)
        self.assertIn('not proof',report['interpretation'])

    def test_temporal_envelope_detects_reversed_syllable_timing(self):
        envelope = .2+.8*np.exp(-((self.t-.3)/.09)**2)
        reference = envelope*self.voice
        candidate = envelope[::-1]*self.voice
        objective = PersistentSpectrumObjective(reference)
        self.assertGreater(objective.evaluate(candidate)['band_envelope_loss'],.2)
        self.assertLess(objective.evaluate(reference)['band_loss'],1e-12)

    def test_invalid_input_and_duration_are_rejected(self):
        with self.assertRaises(ValueError):PersistentSpectrumObjective(np.zeros(7500))
        with self.assertRaises(ValueError):PersistentSpectrumObjective(self.voice,sr=8000)
        with self.assertRaises(ValueError):PersistentSpectrumObjective(self.voice,min_run_ms=0)
        objective = PersistentSpectrumObjective(self.voice)
        for invalid in (self.voice[:-1],np.full(7500,np.nan),np.zeros((7500,2))):
            with self.assertRaises(ValueError):objective.evaluate(invalid)


if __name__=='__main__':unittest.main()

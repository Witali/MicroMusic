"""Automatic tonal-event selection on an independent synthetic recording."""
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from speech_spectrum import PersistentSpectrumObjective

spec = importlib.util.spec_from_file_location('hq4_bell_probe', ROOT/'tools/probe-hq4-bell.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class TonalProbeTests(unittest.TestCase):
    def test_first_multimode_strike_does_not_select_later_tone(self):
        sr = 7500
        t = np.arange(sr*3)/sr
        strike = np.maximum(0., t-.2)
        envelope = ((t >= .2) & (t < 1.0))*np.exp(-strike*2)
        x = envelope*(.4*np.sin(2*np.pi*1145*t)+.25*np.sin(2*np.pi*655*t))
        x += .4*np.sin(2*np.pi*1530*t)*((t > 1.7) & (t < 2.6))
        selected = probe.tonal_event(PersistentSpectrumObjective(x))
        self.assertGreaterEqual(len(selected), 2)
        self.assertTrue(all(r['start_seconds'] < .4 and r['end_seconds'] < 1.2 for r in selected))
        frequencies = [r['median_hz'] for r in selected]
        self.assertTrue(any(abs(f-1145) < 20 for f in frequencies))
        self.assertTrue(any(abs(f-655) < 20 for f in frequencies))

    def test_low_frequency_voice_does_not_create_a_high_tone_target(self):
        t = np.arange(7500)/7500
        x = .4*np.sin(2*np.pi*170*t)
        with self.assertRaisesRegex(ValueError, 'No strong persistent'):
            probe.tonal_event(PersistentSpectrumObjective(x))


if __name__ == '__main__':
    unittest.main()

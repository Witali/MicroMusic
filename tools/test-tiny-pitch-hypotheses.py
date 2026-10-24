"""Exact legacy control, generic octave hypotheses and protected fallback."""
from pathlib import Path
import sys
import unittest
import json

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from fixed_period import decode_fixed
from new_tiny_encoder import analyze_reference
from tiny_period import pack_tiny
from tiny_pitch_hypotheses import pitch_hypotheses, analysis_from_pitch, safe_initialize, run


class TinyPitchTests(unittest.TestCase):
    def reference(self):
        t = np.arange(4096)/7500
        return (.2*np.cos(2*np.pi*140*t)+.05*np.cos(2*np.pi*280*t))*np.hanning(len(t))

    def test_legacy_helper_matches_frozen_phase_shapes_and_integer_model(self):
        x = self.reference()
        _, base, analysis = analyze_reference(x, starts=1, seed=23230, pitch_mode='legacy')
        item = pitch_hypotheses(x)[0]
        derived, info = analysis_from_pitch(x, item)
        self.assertEqual(derived['initial_phase_u16'], base['initial_phase_u16'])
        self.assertEqual([f[0] for f in derived['frames']], [f[0] for f in base['frames']])
        np.testing.assert_array_equal(info['phase'], analysis['phase'])
        np.testing.assert_array_equal(info['shapes'], analysis['shapes'])
        for words in (4, 8):
            old, _ = safe_initialize(x, base, analysis, words, 23230)
            new, _ = safe_initialize(x, derived, info, words, 23230)
            self.assertEqual(pack_tiny(old)['flash_data'], pack_tiny(new)['flash_data'])
            self.assertEqual(pack_tiny(old)['eeprom'], pack_tiny(new)['eeprom'])
            np.testing.assert_array_equal(decode_fixed(old), decode_fixed(new))

    def test_octaves_preserve_unvoiced_and_only_transform_admissible_source_f0(self):
        items = pitch_hypotheses(self.reference())
        legacy = items[0]['f0']
        for item, factor in zip(items[1:3], (.5, 2.)):
            mask = (legacy > 0) & (legacy*factor >= 65) & (legacy*factor <= 850)
            np.testing.assert_array_equal(item['f0'][mask], legacy[mask]*factor)
            np.testing.assert_array_equal(item['f0'][~mask], legacy[~mask])

    def test_good_public_incumbent_is_preserved_as_actual_model_bytes_and_pcm(self):
        x, _ = sf.read(ROOT/'web-player/audio/originals/chego.wav')
        saved = json.loads((ROOT/'ATtiny13A/Sound/research/tiny-speech/chego/model.json').read_text())
        original = x.copy()
        _, incumbent, selected, report = run(x, baseline_model=saved)
        self.assertTrue(report['baseline_fallback'])
        self.assertTrue(report['selected_quality_gate']['candidate_passed'])
        self.assertEqual(pack_tiny(incumbent)['flash_data'], pack_tiny(selected)['flash_data'])
        self.assertEqual(pack_tiny(incumbent)['eeprom'], pack_tiny(selected)['eeprom'])
        np.testing.assert_array_equal(decode_fixed(incumbent), decode_fixed(selected))
        np.testing.assert_array_equal(x, original)

    def test_out_of_pcm_range_input_is_rejected_without_gain_changes(self):
        x = self.reference()
        x[100] = 1.001
        with self.assertRaises(ValueError):
            run(x)
        self.assertEqual(x[100], 1.001)


if __name__ == '__main__':
    unittest.main()

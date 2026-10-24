"""Real-byte seed fitting, original targets and non-dominated candidate retention."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('q3_pulsebook_search',ROOT/'tools/probe-q3-pulsebook.py')
search = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = search
spec.loader.exec_module(search)


class PulsebookSearchTests(unittest.TestCase):
    def test_seed_budget_fit_saves_real_bytes_without_changing_timing_pitch_or_gain(self):
        f = np.array([[40,3,0x88,0x88,0x88,0x88],[40,3,0x89,0x88,0x88,0x88],
            [41,4,0x89,0x99,0x88,0x88],[41,4,0x89,0x99,0x89,0x88]],np.uint8)
        d = np.full(4,256,np.uint16)
        before = f.copy()
        size = len(search.pack_stream(f,d))
        fitted,changes = search.fit_budget(f,d,size-2)
        self.assertLessEqual(len(search.pack_stream(fitted,d)),size-2)
        self.assertTrue(changes)
        np.testing.assert_array_equal(f,before)
        np.testing.assert_array_equal(fitted[:,:2],f[:,:2])
        np.testing.assert_array_equal(d,np.full(4,256))
        second,_ = search.fit_budget(f,d,size-2)
        np.testing.assert_array_equal(fitted,second)

    def test_starting_below_user_target_is_evaluated_without_old_quality_ceiling(self):
        model = json.loads((ROOT/'ATtiny13A/Sound/research/q3-rounded-eeprom/qualified/model.json').read_text())
        reference,sr = sf.read(ROOT/'web-player/audio/originals/vinni.wav',dtype='float64')
        self.assertEqual(sr,7500)
        objective = search.Objective(reference)
        f,d = np.asarray(model['frames'],np.uint8),np.asarray(model['durations'],np.uint16)
        f,_ = search.fit_budget(f,d,613)
        state = search.State(f,d,search.legacy_tables(),True,1)
        score = objective.evaluate(state)
        self.assertIsNotNone(score)
        self.assertLess(score['stoi'],.9)
        self.assertFalse(score['target_met'])
        self.assertTrue(np.isfinite(objective.energy(score)))

    def test_pareto_retains_both_dimensions_and_rejects_dominated_duplicates(self):
        def state(stoi,loss):
            return search.State(None,None,None,False,1,dict(stoi=stoi,spectrogram_loss=loss))
        archive = []
        for candidate in (state(.84,.5),state(.80,.4),state(.82,.53),state(.84,.5)):
            archive = search.pareto_add(archive,candidate)
        self.assertEqual(len(archive),2)
        self.assertEqual(max(x.score['stoi'] for x in archive),.84)
        self.assertEqual(min(x.score['spectrogram_loss'] for x in archive),.4)
        archive = search.pareto_add(archive,state(.9,.34))
        self.assertEqual(len(archive),1)
        self.assertEqual(archive[0].score['stoi'],.9)


if __name__ == '__main__':
    unittest.main()

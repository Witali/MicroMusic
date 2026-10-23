"""Search contracts: validated seeds, explicit pole conversion and Pareto ends."""
import importlib.util
from pathlib import Path
import random
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('probe32',ROOT/'tools/probe-q3-pulsebook32.py')
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


def model():
    return dict(schema='hq4-q3-pulsebook-v1',samples=256,frames=[[40,3,136,136,136,136]],
                durations=[256],pulsebook=np.zeros((4,16),int).tolist(),tilt_shift=1)


class Search32Tests(unittest.TestCase):
    def test_old_seed_padding_has_no_source_side_information(self):
        f,d,b,conversion = probe.import_model(model())
        self.assertEqual(b.shape,(4,32))
        self.assertFalse(np.any(b))
        self.assertEqual(conversion['padded_zero_taps'],64)
        self.assertEqual(probe.validate(f,d,b),probe.pack_stream(f,d))

    def test_malformed_raw_values_do_not_wrap_into_valid_seed(self):
        for value in (260,-252,4.5):
            bad = model();bad['frames'][0][0] = value
            with self.assertRaises(ValueError): probe.import_model(bad)
        bad = model();bad['durations'] = [65792]
        with self.assertRaises(ValueError): probe.import_model(bad)

    def test_pole_conversion_is_explicit_and_old_score_is_not_used(self):
        bad = model();bad['frames'][0][2] = 0x80
        with self.assertRaises(ValueError): probe.import_model(bad)
        bad['schema'] = 'hq4-q3-pulsebook-pole-v1'
        f,_,_,conversion = probe.import_model(bad)
        self.assertEqual(int(f[0,2]),0x81)
        self.assertEqual(conversion['pole_nibbles_replaced'],1)

    def test_mutations_reach_new_lags_and_archive_keeps_both_extremes(self):
        f,d,b,_ = probe.import_model(model())
        state = probe.State(f,d,b,False,1)
        rng = random.Random(20261023)
        self.assertTrue(any(np.any(probe.mutate(state,rng).book[:,16:]) for _ in range(100)))
        archive = []
        for intelligibility,spectrum in ((.9,.5),(.8,.3),(.85,.4),(.7,.6)):
            value = probe.State(f,d,b,False,1,dict(stoi=intelligibility,spectrogram_loss=spectrum))
            archive = probe.pareto_add(archive,value)
        self.assertEqual(len(archive),3)
        self.assertEqual(max(s.score['stoi'] for s in archive),.9)
        self.assertEqual(min(s.score['spectrogram_loss'] for s in archive),.3)


if __name__ == '__main__':
    unittest.main()

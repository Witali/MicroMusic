"""Joint moves cross coordinate barriers without changing the decoder format."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('block_search_contracts',ROOT/'tools/refit-lattice-blocks.py')
probe=importlib.util.module_from_spec(spec);sys.modules[spec.name]=probe;spec.loader.exec_module(probe)


class LatticeBlockTests(unittest.TestCase):
    def test_proposals_are_stable_joint_moves_and_do_not_mutate_the_seed(self):
        model=ROOT/'ATtiny13A/Sound/research/q4-pulse-shapes/voice-search/model.json'
        state,bits,*_=probe.fit.load(model);before=state.fields()
        proposals=list(probe.row_proposals(state,bits,50,np.array([-15,14,-4,3,-2,1,0,0]),('pair','source','neighbor')))
        self.assertTrue(any(np.count_nonzero(k!=state.coefficients[50])==2 for family,k,g in proposals if family=='pair'))
        self.assertTrue(any(g!=state.gains_q1[50] for _,_,g in proposals))
        self.assertEqual(len(proposals),len(set((tuple(k),g) for _,k,g in proposals)))
        for _,k,g in proposals:
            probe.fit.codec.validate(k[None,:],bits,6);self.assertTrue(0<=g<=30)
        self.assertEqual(before,state.fields())

    def test_no_search_reproduces_the_full_original_seed_and_rejects_a_changed_reference(self):
        model=ROOT/'ATtiny13A/Sound/research/q4-pulse-shapes/voice-search/model.json'
        reference=ROOT/'web-player/audio/originals/vinni.wav'
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            result=probe.run(reference,model,Path(folder),0)
            self.assertEqual(result['final']['pcm_sha256'],'2b1a8a30717bcc7657df024b1002350b816086492e092535193ba7123abc7523')
            self.assertAlmostEqual(result['final']['stoi'],.8885910280071512,places=12)
            bad=Path(folder)/'wrong.wav'
            data=bytearray(reference.read_bytes());data[-2]^=1;bad.write_bytes(data)
            with self.assertRaises(ValueError):probe.run(bad,model,Path(folder)/'rejected',0)


if __name__=='__main__':unittest.main()

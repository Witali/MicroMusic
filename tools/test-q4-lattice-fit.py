"""Joint-fit mutations, exact seed transfer and retained fractional excitation."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('q4_lattice_fit_contracts',ROOT/'tools/refine-q4-lattice.py')
fit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fit;spec.loader.exec_module(fit)


class LatticeFitTests(unittest.TestCase):
    def fixture(self):
        waves=np.zeros((8,16),np.int16);waves[0,:4]=[4,6,4,-2]
        return fit.State(np.array([40,0],np.int16),np.array([10,4],np.int16),
            np.array([128,128],np.int16),np.zeros((2,8),np.int16),
            np.zeros(2,np.int16),waves,np.zeros(2,np.int16))

    def test_quarter_excitation_seed_matches_exact_q4_control(self):
        state=fit.load(ROOT/'ATtiny13A/Sound/research/q4-voice-patterns/full/per-frame-control.json')
        fit.validate(state);pcm,counts=fit.render(state,0,False)
        self.assertFalse(np.any(counts))
        self.assertEqual(hashlib.sha256(pcm.tobytes()).hexdigest(),
            '9e90cf39850388f5eb0ca01d8b1a84ce8a7e0dce94edf76977252e448c0a2133')

    def test_actions_change_only_the_proposed_fields_and_keep_source_isolated(self):
        original=self.fixture();snapshot=original.fields()
        examples=[('coefficient',0,2,1),('gain',0,0,-1),('pitch',0,0,1),
            ('mode',0,0,1),('wave',0,0,-1),('boundary',0,0,64),('split',0,1,-1)]
        for action in examples:
            changed=fit.apply(original,action);self.assertIsNotNone(changed);fit.validate(changed)
            self.assertEqual(original.fields(),snapshot)
            self.assertNotEqual(changed.fields(),snapshot)
            self.assertEqual(int(changed.durations.sum()),int(original.durations.sum()))
        split=fit.apply(original,('split',0,1,-1))
        self.assertEqual(int(split.modes[0]),1)
        np.testing.assert_array_equal(split.waves_q1[1],[4,5,4,-2]+[0]*12)
        np.testing.assert_array_equal(split.waves_q1[0],original.waves_q1[0])
        pitch=fit.apply(original,('pitch',0,0,1))
        self.assertEqual((int(pitch.pitches[0]),int(pitch.halves[0])),(40,1))

    def test_state_precision_preserves_subunit_excitation_through_feedback(self):
        # Input is 3/4 DAC unit; a byte input rounds it to zero before feedback.
        excitation=np.full(32,3,np.int32);rows=np.zeros(32,np.int32)
        k=np.zeros((1,8),np.int16);k[0,0]=-8
        byte,_=fit.codec.filter_signal(excitation,rows,k,tilt_shift=0,state_bits=0,fraction_bits=2)
        word,counts=fit.codec.filter_signal(excitation,rows,k,tilt_shift=0,state_bits=4,fraction_bits=2)
        np.testing.assert_array_equal(byte,np.full(32,128,np.uint8))
        np.testing.assert_array_equal(word,np.array([128]+[129]*31,np.uint8))
        self.assertFalse(np.any(counts))

    def test_invalid_coordinate_moves_do_not_wrap_their_storage(self):
        state=self.fixture();state.coefficients[0,0]=15;state.gains_q1[0]=30
        state.waves_q1[0,0]=7;state.durations[:]=64
        for action in [('coefficient',0,0,1),('gain',0,0,1),('wave',0,0,1),('boundary',0,0,64)]:
            self.assertIsNone(fit.apply(state,action))


if __name__=='__main__':unittest.main()

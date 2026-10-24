"""Forward pulse fitting preserves timing, noise and linear superposition."""
import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pulse_output_contracts',ROOT/'tools/refit-pulse-output.py')
probe=importlib.util.module_from_spec(spec);sys.modules[spec.name]=probe;spec.loader.exec_module(probe)


class PulseOutputTests(unittest.TestCase):
    def test_wave_precision_does_not_change_the_linear_voice_or_noise_scale(self):
        fit=probe.fit
        state=fit.State(np.array([40,0,50,35]),np.array([4,3,6,4]),np.full(4,128),
            np.tile(np.array([2,-3,1,0,1,-1,0,0]),(4,1)),np.array([0,0,1,0]),
            np.zeros((8,16),np.int16),np.array([0,0,1,2]))
        state.waves_q1[0,:2]=[4,-2];state.waves_q1[1,:3]=[3,-2,-1]
        a,offset,old,_,_=probe.responses(state,np.full(8,4),0)
        promoted=state.copy();promoted.waves_q1*=2;promoted.wave_fraction_bits=2
        b,new_offset,new_old,_,error=probe.responses(promoted,np.full(8,4),0)
        self.assertLess(error,1e-12);np.testing.assert_allclose(offset,new_offset,atol=1e-12,rtol=0)
        np.testing.assert_allclose(a@old,b@new_old,atol=1e-12,rtol=0)

    def test_response_matrix_reconstructs_mixed_voice_noise_and_transitions(self):
        fit=probe.fit
        for width in (16,32):
            state=fit.State(np.array([40,0,26,55]),np.array([6,3,4,5]),np.full(4,128),
                np.tile(np.array([2,-3,1,0,1,-1,0,0]),(4,1)),np.array([0,0,1,0]),
                np.zeros((8,width),np.int16),np.array([0,0,1,2]),np.array([0,0,2,1]))
            state.waves_q1[0,:4]=[4,-2,-1,1];state.waves_q1[1,-1]=2
            matrix,offset,old,coordinates,error=probe.responses(state,np.full(8,4),0)
            self.assertLess(error,1e-12);self.assertEqual(matrix.shape,(512,2*width))
            changed=state.copy()
            for mode,tap in coordinates:changed.waves_q1[mode,tap]=((tap*3+mode)%9)-4
            rows,ex=probe.excitation(changed,changed.waves_q1,0)
            direct=probe.floating_filter(ex,rows,changed.coefficients,np.full(8,4))
            values=np.array([changed.waves_q1[m,t] for m,t in coordinates])
            np.testing.assert_allclose(matrix@values+offset,direct,atol=1e-12,rtol=0)

    def test_phase_target_reconstructs_an_identical_signal_without_time_shift(self):
        x=np.random.default_rng(914).normal(0,.1,7501)
        for size in (256,512,1024):
            target=probe.phase_target(x,x,size)
            self.assertEqual(target.shape,x.shape);np.testing.assert_allclose(target,x,atol=1e-12,rtol=0)


if __name__=='__main__':unittest.main()

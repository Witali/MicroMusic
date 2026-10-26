"""Delayed decisions and existing pitch/sparse modes are reconstructed exactly."""
from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from batch_decoder import BatchSession
from test_beam_excitation import raw_fixture
from joint_rate import trellis,encode_joint
from q0_model import coefficient_trace,table
from lpx4 import decode


class JointRateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.session=BatchSession('batch',v3_features=24);cls.decoder=cls.session.__enter__()
    @classmethod
    def tearDownClass(cls):cls.session.__exit__(None,None,None)

    def test_trellis_keeps_lookahead_paths_and_exact_sparse_recursion(self):
        seed=raw_fixture(samples=40);co=coefficient_trace(decode(seed)[0],40);steps=table('scale_table.inc')
        target=np.resize(np.array([3000,-2000,1000,0],np.int64),40)
        args=(target,co,np.zeros(10,np.int64),0,0,15000,0,int(steps[200]),3,np.ones(145,np.int64),np.array([2,18,16,0],np.int64),.01,1e6)
        q,h,d,c,loss,cost,valid=trellis(*args,4)
        self.assertTrue(valid);history=[1]*145;pulses=0
        for value in q:
            prediction=min(3,max(-4,(16*history[-18]+8)>>4));delta=int(value)-prediction
            self.assertTrue(-16<=delta<=15);pulses+=bool(delta);history.append(int(value))
        self.assertLessEqual(pulses,10);self.assertEqual(cost,11*pulses)
        first=trellis(*args,1)
        self.assertLessEqual(loss/1e6+.01*cost,first[4]/1e6+.01*first[5]+1e-12)

    def test_joint_partial_extremes_determinism_and_native_model(self):
        seed=raw_fixture(samples=161);ref=np.resize(np.array([-32768,32767,0,1000,-1000],np.int16),161)
        a,pcm,r=encode_joint(seed,ref,self.decoder,lam=.01,kind='music')
        b,other,_=encode_joint(seed,ref,self.decoder,lam=.01,kind='music')
        self.assertEqual(a,b);np.testing.assert_array_equal(pcm,other);self.assertTrue(r['native_model_pcm_exact'])
        self.assertEqual(len(decode(a)[2]),161)
        self.assertEqual(sum(r['mode_counts'].values()),5)
        from rate_distortion import encode_rate
        zero,_,_=encode_rate(seed,np.zeros(161,np.int16),self.decoder,lam=1.,allow_zero=True,kind='music')
        nonzero,p,_=encode_joint(zero,ref,self.decoder,lam=.01,allow_zero=False,kind='music')
        self.assertEqual(len(p),161);self.assertTrue(all(b['bits'] for b in decode(nonzero)[1]))
        for options in ({'beam':2},{'lam':float('inf')},{'compact_features':4}):
            with self.assertRaises(ValueError):encode_joint(seed,ref,self.decoder,kind='music',**options)


if __name__=='__main__':unittest.main()

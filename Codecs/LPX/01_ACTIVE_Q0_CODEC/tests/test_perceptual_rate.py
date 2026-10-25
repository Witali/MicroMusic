"""Independent filter oracle, coding-payload roundtrip and native guard checks."""
from pathlib import Path
import sys,unittest
import numpy as np
from scipy.signal import lfilter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from batch_decoder import BatchSession
from test_beam_excitation import raw_fixture
from lpx4 import decode
from compact_format import pack
from joint_rate import encode_joint
from perceptual_rate import weight_error,expanded_v2,refine_perceptual,all_tokens


class PerceptualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.session=BatchSession('batch',v3_features=24);cls.decoder=cls.session.__enter__()
    @classmethod
    def tearDownClass(cls):cls.session.__exit__(None,None,None)

    def test_weighting_matches_independent_constant_filter_oracle(self):
        rng=np.random.default_rng(14);error=rng.normal(0,1000,641)
        row=np.array([-2200,500,0,0,0,0,0,0,0,0],np.int64);co=np.tile(row,(len(error),1))
        numerator=np.r_[1.,row/4096*.9**np.arange(1,11)]
        denominator=np.r_[1.,row/4096*.6**np.arange(1,11)]
        np.testing.assert_allclose(weight_error(error,co),lfilter(numerator,denominator,error),rtol=1e-12,atol=1e-10)
        identity=weight_error(error,np.zeros_like(co));np.testing.assert_array_equal(identity,error)

    def test_compact_sparse_payload_roundtrip_and_perfect_reference_rollback(self):
        seed=raw_fixture(samples=319);target=np.zeros(319,np.int16);target[30:37]=[500,-1000,2000,3000,-1000,1000,0]
        blob,pcm,_=encode_joint(seed,target,self.decoder,lam=.03,kind='music')
        v2=expanded_v2(blob);self.assertEqual(pack(v2,24)[0],blob)
        np.testing.assert_array_equal(self.decoder.decode_one_s16(v2,319),pcm)
        self.assertTrue(all_tokens(v2))
        out,p,r=refine_perceptual(blob,pcm,self.decoder,max_trials=32,kind='music')
        self.assertEqual(out,blob);np.testing.assert_array_equal(p,pcm);self.assertEqual(r['trials'],0)

    def test_partial_signal_guards_and_invalid_settings(self):
        seed=raw_fixture(samples=161);blob=pack(seed,24)[0]
        ref=np.resize(np.array([0,500,-300,1000],np.int16),161)
        out,pcm,r=refine_perceptual(blob,ref,self.decoder,max_trials=16,max_windows=2,kind='music')
        self.assertEqual(len(out),len(blob));self.assertLessEqual(r['weighted_sse_after'],r['weighted_sse_before']+1e-9)
        self.assertLessEqual(r['max_error_after'],r['peak_limit']);self.assertTrue(r['native_model_pcm_exact'])
        for opts in ({'gamma1':.5},{'max_ser_drop_db':4},{'peak_growth':1},{'max_trials':-1}):
            with self.assertRaises(ValueError):refine_perceptual(blob,ref,self.decoder,kind='music',**opts)


if __name__=='__main__':unittest.main()

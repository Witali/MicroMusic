import unittest
import numpy as np

from batch_decoder import BatchSession
from test_speech_v9 import sparse_fixture
from speech_v9 import repack
import speech_sparse80 as sparse
from refine_sparse80 import refine,voice_floor
from standard_metrics import pwm_duties
from refine_speech_compact import no_regression


class SparseFilterRefinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session=BatchSession('batch',speech=True,speech_compact=True,compact_only=True)
        cls.decoder=cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):cls.session.__exit__()

    def test_v8_v9_payload_and_admitted_improvement(self):
        original,_=sparse_fixture(3200,pre=8192,bright=0)
        n,sp,pa,pu,_,br=sparse.unpack(original)
        target=sparse.decode_model(sparse.pack(n,sp,pa,pu,6144,br))
        selected=[]
        for blob in (original,repack(original)[0]):
            output,pcm,report=refine(target,blob,self.decoder,speech=False)
            offset=7 if blob[:2]==b'L9' else 12
            self.assertEqual(output[:offset],blob[:offset])
            self.assertEqual(output[offset+4:],blob[offset+4:])
            self.assertEqual(len(output),len(blob))
            self.assertEqual(report['extra_bytes'],0)
            self.assertTrue(report['accepted'])
            self.assertTrue(no_regression(report['selected'],report['baseline']))
            self.assertLess(report['selected']['pcm16']['error_energy'],report['baseline']['pcm16']['error_energy'])
            self.assertLess(report['selected_score'],report['baseline_score'])
            canonical=repack(output,8)[0] if output[:2]==b'L9' else output
            np.testing.assert_array_equal(pcm,sparse.decode_model(canonical))
            np.testing.assert_array_equal(self.decoder.decode_one(sparse.expand(repack(output,8)[0] if output[:2]==b'L9' else output),n),pwm_duties(pcm))
            selected.append(report['output_header'])
        self.assertEqual(*selected)

    def test_exact_rollback_and_reject_other_profiles(self):
        blob,_=sparse_fixture(640,pre=8192,bright=0)
        target=sparse.decode_model(blob)
        output,pcm,report=refine(target,blob,self.decoder,trial_limit=1,metric_limit=1,speech=False)
        self.assertEqual(output,blob);self.assertFalse(report['accepted'])
        np.testing.assert_array_equal(pcm,target)
        for invalid in (b'L9\x04'+b'\0'*10,b'L4HY\x05\x06'+b'\0'*20):
            with self.assertRaises(ValueError):refine(target,invalid,self.decoder)
        for invalid in (target.astype(float),target[:-1],target[:,None]):
            with self.assertRaises(ValueError):refine(invalid,blob,self.decoder)

    def test_missing_period_metric_cannot_evade_a_floor(self):
        old=dict(within_tolerance_frames=3,decoded_collapsed_active_frames=1,fixed_decoded_period_error_mean=.2)
        for change in ({'within_tolerance_frames':2},{'decoded_collapsed_active_frames':2},
                       {'fixed_decoded_period_error_mean':None},{'fixed_decoded_period_error_mean':float('nan')},
                       {'fixed_decoded_period_error_mean':.21}):
            self.assertFalse(voice_floor(dict(old,**change),old))
        self.assertTrue(voice_floor(old,old))


if __name__=='__main__':unittest.main()

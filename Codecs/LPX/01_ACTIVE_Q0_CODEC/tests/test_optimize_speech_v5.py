import unittest
from unittest.mock import patch
import numpy as np
from batch_decoder import BatchSession
from test_speech_v4 import fixture
from speech_v4 import search
from speech_compact import repack, unpack, decode_model,components,pack
from optimize_speech_v5 import optimize, preserves_quality, lower_scale_search


def score(pcm_sse=100,pwm_sse=200,pcm_stoi=.7,pwm_stoi=.6):
    return {'pcm16':{'error_energy':pcm_sse,'stoi':pcm_stoi},
            'pwm8':{'error_energy':pwm_sse,'stoi':pwm_stoi}}


class OptimizeSpeechV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session=BatchSession('batch',v3_features=24,speech=True,speech_compact=True)
        cls.decoder=cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):cls.session.__exit__()

    def test_pcm_and_actual_pwm_quality_floors_are_independent(self):
        baseline=score()
        self.assertTrue(preserves_quality(baseline,score(90,190,.71,.61)))
        self.assertFalse(preserves_quality(baseline,score(90,201,.71,.61)))
        self.assertFalse(preserves_quality(baseline,score(90,190,.71,.59)))
        self.assertFalse(preserves_quality(baseline,score(101,190,.71,.61)))
        self.assertFalse(preserves_quality(baseline,score(90,190,.69,.61)))
        self.assertFalse(preserves_quality(baseline,score(100,190,.71,.61)))
        self.assertFalse(preserves_quality(baseline,score(90,190,float('nan'),.61)))

    def test_unavailable_stoi_is_never_treated_as_a_valid_numeric_floor(self):
        self.assertTrue(preserves_quality(score(pcm_stoi=None,pwm_stoi=None),
                                         score(90,190,None,None)))
        self.assertFalse(preserves_quality(score(),score(90,190,None,.6)))
        self.assertFalse(preserves_quality(score(),score(90,190,.7,None)))

    def test_lower_scale_probe_can_reach_silence_omitted_by_narrow_interval(self):
        x=np.zeros(320,np.int64);co=np.zeros((320,10),np.int64)
        steps=np.arange(256,dtype=np.int64)
        _,_,old=search(x,co,steps,0,4)
        params,_,new,count=lower_scale_search(x,co,steps,0,4)
        self.assertTrue(np.any(old))
        self.assertFalse(np.any(new))
        self.assertTrue(np.all(params[:,0]==0))
        self.assertGreater(count,0)

    def test_disabled_and_perfect_input_retain_plain_extras_and_partial_tails(self):
        for p in (4,6):
            for n in (1,319,321):
                count=((n+319)//320)*8
                for enhanced in (False,True):
                    blob,_=repack(fixture(p,n),extras=[(0,7)]*count if enhanced else None)
                    reference=decode_model(blob)
                    for enabled in (False,True):
                        selected,pcm,report=optimize(reference,blob,self.decoder,len(blob),enabled=enabled)
                        self.assertEqual(selected,blob)
                        np.testing.assert_array_equal(pcm,reference)
                        self.assertTrue(report['retained_baseline'])
                        self.assertEqual(report['trials'],0)

    def test_accepted_short_proposal_retains_geometry_and_native_model_output(self):
        for p in (4,6):
            n=321;blob,_=repack(fixture(p,n),extras=[(0,7)]*16)
            selected,pcm,report=optimize(np.zeros(n,np.int16),blob,self.decoder,len(blob),
                                       proposals=('lower_scales',))
            self.assertTrue(report['accepted'])
            self.assertTrue(report['selected_admissible'])
            self.assertLessEqual(len(selected),len(blob))
            self.assertEqual(unpack(selected)[:3],unpack(blob)[:3])
            self.assertFalse(np.any(pcm))
            np.testing.assert_array_equal(pcm,decode_model(selected))

    def test_invalid_geometry_caps_and_unbounded_proposals_are_rejected(self):
        blob,_=repack(fixture(4,321));ref=np.zeros(321,np.int16)
        for cap in (True,21,65536,len(blob)-1):
            with self.assertRaises(ValueError):optimize(ref,blob,self.decoder,cap)
        with self.assertRaises(ValueError):optimize(ref[:-1],blob,self.decoder,len(blob))
        for proposals in (('unknown',),('pre75','pre75'),('pre75','lower_scales','pre75'),'pre75'):
            with self.assertRaises(ValueError):optimize(ref,blob,self.decoder,len(blob),proposals=proposals)

    def test_candidate_no_fit_retains_exact_baseline_and_continues_other_proposals(self):
        n=640;candidate=fixture(4,n);args=list(components(candidate))
        args[2][1]=args[2][0].copy()
        baseline,_=pack(*args);cap=len(baseline)
        self.assertGreater(len(repack(candidate)[0]),cap)
        reference=np.zeros(n,np.int16)
        def passthrough(ref,blob,decoder,**kwargs):
            return blob,decoder.decode_one_s16(blob,len(ref)),{}
        with patch('optimize_speech_v5.encode',return_value=(candidate,None,{})), \
             patch('optimize_speech_v5.refine',side_effect=passthrough):
            selected,pcm,report=optimize(reference,baseline,self.decoder,cap,proposals=('pre75',))
            self.assertEqual(selected,baseline)
            np.testing.assert_array_equal(pcm,decode_model(baseline))
            self.assertTrue(report['retained_baseline'])
            self.assertEqual(report['trials'],1)
            self.assertEqual(report['checkpoints'][0]['rejection'],'candidate_no_fit')
            self.assertEqual(report['max_bytes'],cap)
            selected,pcm,report=optimize(reference,baseline,self.decoder,cap)
            self.assertEqual(report['trials'],2)
            self.assertEqual(report['checkpoints'][0]['rejection'],'candidate_no_fit')
            self.assertTrue(report['accepted'])
            self.assertEqual(report['selected_proposal'],'lower_scales')
            self.assertLessEqual(len(selected),cap)
            self.assertFalse(np.any(pcm))
            np.testing.assert_array_equal(pcm,decode_model(selected))

    def test_unrelated_candidate_value_error_is_not_suppressed(self):
        candidate=fixture(4,320);baseline,_=repack(candidate)
        with patch('optimize_speech_v5.encode',return_value=(candidate,None,{})), \
             patch('optimize_speech_v5.refine',return_value=(candidate,None,{})), \
             patch('optimize_speech_v5.enhance',side_effect=ValueError('Unrelated candidate range failure')):
            with self.assertRaisesRegex(ValueError,'Unrelated candidate range failure'):
                optimize(np.zeros(320,np.int16),baseline,self.decoder,len(baseline),proposals=('pre75',))


if __name__=='__main__':unittest.main()

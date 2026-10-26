import unittest
from unittest.mock import patch
import numpy as np
from batch_decoder import BatchSession
from test_speech_v4 import fixture
from speech_v4 import unpack,decode_model
from refine_speech_v4 import refine,advance
from q0_model import coefficient_trace,table
from wav_lpc import pack_frames


class RefineSpeechV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session=BatchSession('batch',v3_features=24,speech=True)
        cls.decoder=cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):cls.session.__exit__()

    def test_snapshot_synthesis_partial_bright_and_native(self):
        for profile in (4,6):
            for n in (1,19,161,321,641):
                b=bytearray(fixture(profile,n));b[14:16]=(4000).to_bytes(2,'little')
                n,pre,bright,vectors,params,pulses=unpack(bytes(b))
                co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n)
                args=(co,np.asarray(params,np.int64),np.asarray(pulses,np.int64),table('scale_table.inc'),pre,bright)
                full,h,d,c,ring=advance(*args,0,n,np.zeros(10,np.int64),0,0,np.zeros(256,np.int64))
                np.testing.assert_array_equal(full,self.decoder.decode_one_s16(bytes(b),n))
                cut=min(159,n)
                first,h,d,c,ring=advance(*args,0,cut,np.zeros(10,np.int64),0,0,np.zeros(256,np.int64))
                second,*_=advance(*args,cut,n,h,d,c,ring)
                np.testing.assert_array_equal(full,np.r_[first,second])

    def test_full_reference_floors_header_spectrum_and_partial_tail(self):
        for profile in (4,6):
            baseline=fixture(profile,6401)
            reference=(900*np.sin(np.arange(6401)*.2)).astype(np.int16)
            result,pcm,report=refine(reference,baseline,self.decoder,horizon=80,group_samples=320)
            self.assertEqual(result[:20],baseline[:20]);self.assertEqual(len(result),len(baseline))
            self.assertEqual(unpack(result)[3],unpack(baseline)[3])
            self.assertLessEqual(report['selected']['error_energy'],report['baseline']['error_energy'])
            self.assertGreaterEqual(report['selected']['stoi']+1e-12,report['baseline']['stoi'])
            np.testing.assert_array_equal(pcm,decode_model(result))

    def test_stoi_gate_rejects_a_lower_sse_candidate(self):
        from standard_metrics import error_metrics
        baseline=fixture(6,641);reference=np.zeros(641,np.int16);calls=[]
        def score(ref,pcm,speech):
            result=error_metrics(ref,pcm,False)
            result['stoi']=1. if not calls else 0.
            calls.append(result['error_energy']);return result
        with patch('refine_speech_v4.error_metrics',side_effect=score):
            result,_,report=refine(reference,baseline,self.decoder,horizon=80,group_samples=320)
        self.assertGreater(len(calls),1)
        self.assertTrue(any(sse<calls[0] for sse in calls[1:]))
        self.assertEqual(result,baseline);self.assertEqual(report['accepted_groups'],0)

    def test_perfect_baseline_is_preserved_and_invalid_arguments_reject(self):
        baseline=fixture(6,641);reference=decode_model(baseline)
        result,pcm,report=refine(reference,baseline,self.decoder,horizon=80,group_samples=320)
        self.assertEqual(result,baseline);self.assertEqual(report['accepted_groups'],0)
        for kwargs in ({'passes':0},{'horizon':20},{'group_samples':321}):
            with self.assertRaises(ValueError):refine(reference,baseline,self.decoder,**kwargs)
        with self.assertRaises(ValueError):refine(reference[:-1],baseline,self.decoder)


if __name__=='__main__':unittest.main()

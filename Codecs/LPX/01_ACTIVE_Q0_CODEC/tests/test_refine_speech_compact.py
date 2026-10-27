import unittest
import numpy as np
from batch_decoder import BatchSession
from test_speech_v4 import fixture
import speech_compact as compact
from refine_speech_compact import filter_signal, lpc_signal, errors, refine
from standard_metrics import pwm_pcm16
from tune_pcm16 import set_header
from q0_model import coefficient_trace, table
from wav_lpc import pack_frames


class CompactHeaderRefinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session=BatchSession('batch',speech=True,speech_compact=True,compact_only=True)
        cls.decoder=cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.session.__exit__()

    def test_cached_integer_signal_native_and_independent_model(self):
        for profile in (4,6):
            for n in (1,19,20,39,40,159,160,319,320,321,641,64000):
                extras=[(i%40,-8 if i&1 else 7) for i in range(((n+319)//320)*8)]
                blob=compact.repack(fixture(profile,n),extras=extras)[0]
                args=compact.unpack(blob);_,_,spectra,params,pulses,_,_,extra=args
                shift=5 if profile==4 else 4
                vectors=[[(v<<shift)+(1<<(shift-1)) for v in row] for row in spectra for _ in range(2)]
                co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n)
                signal=lpc_signal(co,np.asarray(params,np.int64),np.asarray(pulses,np.int64),
                                  np.asarray(extra,np.int64),table('scale_table.inc'))
                for pre,bright in ((0,0),(16384,11469),(13926,0)):
                    altered=set_header(blob,pre,bright);actual=filter_signal(signal,pre,bright)
                    np.testing.assert_array_equal(actual,self.decoder.decode_one_s16(altered,n))
                    np.testing.assert_array_equal(actual,compact.decode_model(altered))

    def test_saturating_postfilters_and_pwm_errors(self):
        signal=np.tile(np.asarray([-32768,32767,-16385,16385,0,1,-1],np.int64),100)
        self.assertGreater(np.max(np.abs(signal)),16384)
        reference=np.arange(len(signal),dtype=np.int64)*79-30000
        for pre,bright in ((0,0),(16384,0),(0,11469),(16384,11469)):
            expected=[];dd=cc=0
            for value in signal.tolist():
                dd=max(-32767,min(32767,value+((pre*dd)>>14)))
                clip=max(-16384,min(16384,dd))
                out=max(-16384,min(16384,clip-((bright*cc)>>14)));cc=clip
                expected.append(max(-32768,min(32767,out*2)))
            actual=filter_signal(signal,pre,bright)
            np.testing.assert_array_equal(actual,expected)
            a,b=errors(reference,signal,pre,bright)
            self.assertEqual(a,np.sum((reference-actual.astype(np.int64))**2))
            self.assertEqual(b,np.sum((reference-pwm_pcm16(actual).astype(np.int64))**2))

    def test_existing_extras_and_payload_survive_header_search(self):
        for profile in (4,6):
            extras=[(i%40,7 if i&1 else -8) for i in range(24)]
            blob=compact.repack(fixture(profile,641),extras=extras)[0]
            target=self.decoder.decode_one_s16(set_header(blob,11878,0),641)
            result,actual,report=refine(target,blob,self.decoder,trial_limit=128,metric_limit=16)
            np.testing.assert_array_equal(actual,target)
            self.assertEqual(result[:12],blob[:12]);self.assertEqual(result[16:],blob[16:])
            self.assertEqual(len(result),len(blob));self.assertEqual(report['extra_bytes'],0)
            self.assertTrue(report['native_model_pwm_exact'])
            again,_,_=refine(target,result,self.decoder,trial_limit=1,metric_limit=1)
            self.assertEqual(again,result)

    def test_validation_and_bounded_baseline_rollback(self):
        blob=compact.repack(fixture(4,320))[0]
        ref=self.decoder.decode_one_s16(blob,320)
        result,actual,report=refine(ref,blob,self.decoder,trial_limit=1,metric_limit=1)
        self.assertEqual(result,blob);np.testing.assert_array_equal(actual,ref)
        self.assertFalse(report['accepted']);self.assertEqual(report['candidate_evaluations'],1)
        for invalid in (ref.astype(float),ref.astype(np.int64)+65536,ref[:-1],ref[:,None]):
            with self.assertRaises(ValueError):refine(invalid,blob,self.decoder)
        for key in ('trial_limit','metric_limit'):
            for invalid in (True,0,-1,1.5,5000):
                with self.assertRaises(ValueError):refine(ref,blob,self.decoder,**{key:invalid})


if __name__=='__main__':unittest.main()

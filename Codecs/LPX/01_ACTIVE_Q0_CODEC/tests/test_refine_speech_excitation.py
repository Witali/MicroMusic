import unittest
import numpy as np
from batch_decoder import BatchSession
from test_speech_v4 import fixture
import speech_compact as compact
from refine_speech_excitation import refine


class CompactJointRefinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session=BatchSession('batch',speech=True,speech_compact=True,compact_only=True)
        cls.decoder=cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.session.__exit__()

    def test_exact_baseline_partial_tails_existing_extras_and_caps(self):
        for profile in (4,6):
            for n in (1,19,20,39,40,159,160,319,320,321,641):
                count=((n+319)//320)*8
                extras=[(i%40,-8 if i&1 else 7) for i in range(count)]
                blob=compact.repack(fixture(profile,n),extras=extras)[0]
                ref=self.decoder.decode_one_s16(blob,n)
                for limit in (len(blob),len(blob)+20):
                    result,pcm,report,raw=refine(ref,blob,self.decoder,limit,horizon=80,group_samples=160)
                    self.assertEqual(result,blob);self.assertEqual(raw,blob)
                    np.testing.assert_array_equal(pcm,ref);self.assertLessEqual(len(result),limit)
                    self.assertEqual(report['accepted_groups'],0)
                    self.assertTrue(report['native_model_pwm_exact'])

    def test_refinement_selects_known_modified_v5_target(self):
        for profile in (4,6):
            blob=compact.repack(fixture(profile,640),extras=[(i%40,4) for i in range(16)])[0]
            fields=list(compact.unpack(blob));fields[-1]=list(fields[-1]);fields[-1][0]=(0,7)
            target=compact.pack(*fields[:7],extras=fields[-1])[0]
            ref=self.decoder.decode_one_s16(target,640)
            result,pcm,report,raw=refine(ref,blob,self.decoder,len(blob)+20,horizon=160,group_samples=160)
            self.assertLess(report['selected']['pcm16']['error_energy'],report['baseline']['pcm16']['error_energy'])
            self.assertLessEqual(len(result),len(blob)+20)
            self.assertEqual(compact.unpack(result)[2],compact.unpack(blob)[2])
            np.testing.assert_array_equal(pcm,compact.decode_model(result))
            self.assertTrue(report['native_model_pwm_exact'])

    def test_changed_partial_final_chunk_uses_actual_sample_count(self):
        for profile in (4,6):
            extras=[(0,4)]*16
            blob=compact.repack(fixture(profile,321),extras=extras)[0]
            fields=list(compact.unpack(blob));fields[-1]=list(fields[-1]);fields[-1][8]=(0,7)
            target=compact.pack(*fields[:7],extras=fields[-1])[0]
            ref=self.decoder.decode_one_s16(target,321)
            result,pcm,report,raw=refine(ref,blob,self.decoder,len(blob),horizon=80,group_samples=160)
            np.testing.assert_array_equal(pcm,ref)
            self.assertEqual(report['selected']['pcm16']['error_energy'],0)
            self.assertLessEqual(len(result),len(blob))
            self.assertEqual(len(compact.unpack(result)[-1]),16)

    def test_parameter_and_reference_validation(self):
        blob=compact.repack(fixture(4,320))[0];ref=self.decoder.decode_one_s16(blob,320)
        for invalid in (ref.astype(float),ref.astype(np.int64)+65536,ref[:-1],ref[:,None]):
            with self.assertRaises(ValueError):refine(invalid,blob,self.decoder,len(blob))
        for cap in (True,len(blob)-1,65536,10.5):
            with self.assertRaises(ValueError):refine(ref,blob,self.decoder,cap)
        for kwargs in ({'horizon':40},{'passes':3},{'group_samples':161}):
            with self.assertRaises(ValueError):refine(ref,blob,self.decoder,len(blob),**kwargs)


if __name__=='__main__':unittest.main()

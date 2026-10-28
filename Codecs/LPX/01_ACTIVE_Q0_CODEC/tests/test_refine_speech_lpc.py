import unittest
from unittest.mock import patch
import numpy as np
from batch_decoder import BatchSession
from test_speech_v4 import fixture
import speech_compact as compact
from q0_model import coefficient_trace, table
from refine_speech_lpc import coefficient_patch, spectrum_bits, fit_capacity, refine
from wav_lpc import pack_frames


def trace(spectra,profile,n):
    shift=5 if profile==4 else 4
    vectors=[[(v<<shift)+(1<<(shift-1)) for v in row] for row in spectra for _ in range(2)]
    return coefficient_trace(pack_frames(vectors[:(n+159)//160]),n)


class JointLpcRefinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session=BatchSession('batch',speech=True,speech_compact=True,compact_only=True)
        cls.decoder=cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):cls.session.__exit__()

    def test_local_patch_exact_includes_next_frame_and_partial_tails(self):
        for profile in (4,6):
            for n in (1,159,160,319,320,321,479,480,481,641,960,64000):
                fields=compact.unpack(compact.repack(fixture(profile,n))[0]);spectra=fields[2]
                original=trace(spectra,profile,n)
                frames=sorted({0,len(spectra)//2,len(spectra)-1})
                for frame in frames:
                    altered=[row.copy() for row in spectra];altered[frame][4]+=1
                    changed=trace(altered,profile,n);actual=original.copy();start=frame*320
                    patch=coefficient_patch(altered,profile,frame,n,table('cos_table.inc'))
                    actual[start:start+len(patch)]=patch
                    np.testing.assert_array_equal(actual,changed)
                    if frame+1<len(spectra) and n>start+320:
                        self.assertTrue(np.any(changed[start+320:min(n,start+480)]!=original[start+320:min(n,start+480)]))

    def test_actual_spectral_bits_and_capacity_match_complete_serialization(self):
        rng=np.random.default_rng(20261027)
        for profile in (4,6):
            for n in (1,321,641,1280):
                blob=compact.repack(fixture(profile,n),extras=[(i%40,7) for i in range(((n+319)//320)*8)])[0]
                fields=compact.unpack(blob);_,_,spectra,params,pulses,pre,bright,extras=fields
                spectra=[sorted(rng.choice(32 if profile==4 else 64,10,replace=False).tolist()) for _ in spectra]
                cost=sum(spectrum_bits(row,None if i==0 else spectra[i-1],profile) for i,row in enumerate(spectra))
                for cap in (len(blob)-10,len(blob),len(blob)+17):
                    added,capacity,size,removed=fit_capacity(cost,len(spectra),profile,np.asarray(extras,np.int64),cap,0,n)
                    actual=compact.pack(n,profile,spectra,params,pulses,pre,bright,extras=added.tolist())[0]
                    self.assertEqual(size,len(actual))
                    self.assertLessEqual(np.count_nonzero(added[:,1]),capacity)
                    self.assertEqual(removed,np.count_nonzero(np.asarray(extras)[:,1])-np.count_nonzero(added[:,1]))

    def test_perfect_baseline_retains_all_stored_tail_extras_and_parameters(self):
        for profile in (4,6):
            for n in (1,19,20,39,40,159,160,319,320,321,641):
                blob=compact.repack(fixture(profile,n),extras=[(i%40,-8 if i&1 else 7) for i in range(((n+319)//320)*8)])[0]
                ref=self.decoder.decode_one_s16(blob,n)
                result,pcm,report,raw=refine(ref,blob,self.decoder,len(blob),frame_limit=2)
                self.assertEqual(result,blob);self.assertEqual(raw,blob)
                np.testing.assert_array_equal(pcm,ref)
                self.assertEqual(report['spectral_trials'],0)
                self.assertTrue(report['native_model_pwm_exact'])

    def test_known_changed_lsf_and_excitation_target_reduces_error(self):
        for profile in (4,6):
            initial=list(compact.unpack(compact.repack(fixture(profile,1280))[0]))
            initial[2]=[[2+3*i for i in range(10)] if profile==4 else [3+6*i for i in range(10)] for _ in range(4)]
            initial[3]=[(25,60,8)]*8;initial[5]=0;initial[6]=0
            blob=compact.pack(*initial[:7],extras=[(i%40,3) for i in range(32)])[0]
            fields=list(compact.unpack(blob));fields[2]=[row.copy() for row in fields[2]];fields[2][1][4]+=1
            fields[3]=list(fields[3]);scale,lag,gain=fields[3][2];fields[3][2]=(scale-1,lag,gain)
            target=compact.pack(*fields[:7],extras=fields[7])[0]
            ref=self.decoder.decode_one_s16(target,1280)
            result,pcm,report,raw=refine(ref,blob,self.decoder,max(len(blob),len(target))+30,
                                      frame_limit=4,spectral_candidates=4,passes=2)
            self.assertLess(report['selected']['pcm16']['error_energy'],report['baseline']['pcm16']['error_energy'])
            self.assertGreater(report['changed_spectral_indices'],0)
            self.assertGreater(report['excitation_trials'],0)
            self.assertLessEqual(len(result),max(len(blob),len(target))+30)
            self.assertEqual(result[12:16],blob[12:16])
            np.testing.assert_array_equal(pcm,compact.decode_model(result))

    def test_rejected_spectral_change_keeps_incumbent_and_preserves_raw(self):
        for profile in (4,6):
            fields=list(compact.unpack(compact.repack(fixture(profile,1280))[0]))
            fields[2]=[[2+3*i for i in range(10)] if profile==4 else [3+6*i for i in range(10)] for _ in range(4)]
            fields[3]=[(25,60,8)]*8;fields[5]=0;fields[6]=0
            blob=compact.pack(*fields[:7],extras=[(i%40,3) for i in range(32)])[0]
            changed=list(compact.unpack(blob));changed[2]=[row.copy() for row in changed[2]]
            changed[2][1][4]+=1
            target=compact.pack(*changed[:7],extras=changed[7])[0]
            reference=self.decoder.decode_one_s16(target,1280)
            with patch('refine_speech_lpc.no_regression',return_value=False):
                result,pcm,report,raw=refine(reference,blob,self.decoder,max(len(blob),len(target))+30,
                                           frame_limit=4,spectral_candidates=4,passes=2)
            self.assertEqual(result,blob);self.assertNotEqual(raw,blob)
            self.assertEqual(report['accepted_frames'],0)
            self.assertGreater(report['full_metric_evaluations'],0)
            self.assertLess(report['raw_best_sse']['pcm16']['error_energy'],report['baseline']['pcm16']['error_energy'])
            self.assertLessEqual(report['spectral_trials'],4*20*2)
            self.assertTrue(all(not c['conservative_floors_passed'] for c in report['checkpoints']))
            np.testing.assert_array_equal(pcm,self.decoder.decode_one_s16(blob,1280))
            np.testing.assert_array_equal(self.decoder.decode_one_s16(raw,1280),compact.decode_model(raw))

    def test_validation_and_bounded_trial_count(self):
        blob=compact.repack(fixture(4,320))[0];ref=self.decoder.decode_one_s16(blob,320)
        for bad in (ref.astype(float),ref.astype(np.int64)+65536,ref[:-1],ref[:,None]):
            with self.assertRaises(ValueError):refine(bad,blob,self.decoder,len(blob))
        for cap in (True,len(blob)-1,65536,100.5):
            with self.assertRaises(ValueError):refine(ref,blob,self.decoder,cap)
        for kwargs in ({'frame_limit':0},{'spectral_candidates':5},{'lookahead':480},
                       {'excitation_horizon':40},{'passes':3},{'refit':1}):
            with self.assertRaises(ValueError):refine(ref,blob,self.decoder,len(blob),**kwargs)


if __name__=='__main__':unittest.main()

import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np
from batch_decoder import BatchSession
from test_speech_v9 import sparse_fixture
import speech_sparse80 as sparse
import speech_compact as compact
from speech_v9 import repack
from q0_model import coefficient_trace,table
from wav_lpc import pack_frames
from standard_metrics import pwm_duties,pwm_pcm16
from refine_sparse80_pulses import refine,proposals,errors,_floors,band_diagnostics,band_error_floors


def snapshot_fields(blob):
    n,spectra,params,source,pre,bright=sparse.unpack(blob)
    expanded=sparse.expand(blob)
    _,_,_,parameters,pulses,_,_,extras=compact.unpack(expanded)
    vectors=[[(v<<4)+8 for v in row] for row in spectra for _ in range(2)]
    co=coefficient_trace(pack_frames(vectors),len(spectra)*320)[:n]
    return (n,spectra,params,source,pre,bright,co,np.asarray(parameters,np.int64),
            np.asarray(pulses,np.int64),np.asarray(extras,np.int64))


class SparsePulseRefinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session=BatchSession('batch',speech=True,speech_compact=True,compact_only=True)
        cls.decoder=cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):cls.session.__exit__()

    def test_snapshot_tail_cost_matches_complete_independent_model(self):
        for n in (1,79,80,81,319,321,641):
            blob,_=sparse_fixture(n,pre=8192,bright=11469)
            _,sp,pa,pu,pre,bright,co,parameters,pulses,extras=snapshot_fields(blob)
            changed=list(pu);index=max(0,(n-1)//80-1)
            position,amp=changed[index];code=sparse.POSITIONS.index(position)
            changed[index]=(sparse.POSITIONS[code+1 if code<63 else code-1],amp)
            target=sparse.decode_model(sparse.pack(n,sp,pa,changed,pre,bright)).astype(np.int64)
            preserved=[x.copy() for x in (target,parameters,pulses,extras)]
            ranked=proposals(target,co,parameters,pulses,extras,table('scale_table.inc'),pre,bright,np.asarray(pu,np.int64),320)
            base=sum(errors(target,sparse.decode_model(blob)))
            compared=0
            for benefit,packet,pos,amplitude in ranked:
                self.assertIn(pos,sparse.POSITIONS);self.assertIn(amplitude,(-8,7))
                self.assertLess(packet,(n+79)//80)
                if packet*80+320<n:continue
                trial=list(pu);trial[packet]=(pos,amplitude)
                full=sparse.decode_model(sparse.pack(n,sp,pa,trial,pre,bright))
                self.assertEqual(benefit,base-sum(errors(target,full)))
                compared+=1
            self.assertGreater(compared,0)
            for a,b in zip((target,parameters,pulses,extras),preserved):np.testing.assert_array_equal(a,b)

    def test_v8_v9_exact_rollback_including_brightness(self):
        for bright in (0,11469):
            original,_=sparse_fixture(641,pre=8192,bright=bright)
            target=sparse.decode_model(original)
            for blob in (original,repack(original)[0]):
                selected,pcm,report=refine(target,blob,self.decoder,speech=False)
                self.assertEqual(selected,blob);self.assertFalse(report['accepted'])
                self.assertFalse(report['pwm_bytes_changed']);self.assertEqual(report['pwm_changed_samples'],0)
                np.testing.assert_array_equal(pcm,target)
                self.assertEqual(report['pwm_joint_score_delta'],0)

    def test_accepted_change_preserves_metadata_native_output_and_hardware_floors(self):
        original,_=sparse_fixture(320,pre=8192,bright=0)
        n,sp,pa,pu,pre,bright=sparse.unpack(original)
        # A moderate-level hardware-domain target has no clipping tradeoff.
        # Its exact PWM candidate can satisfy every upper-band floor too.
        pa=[(20,lag,gain) for _,lag,gain in pa]
        original=sparse.pack(n,sp,pa,pu,pre,bright)
        changed=list(pu);_,amp=changed[0];changed[0]=(1,amp)
        target=pwm_pcm16(sparse.decode_model(sparse.pack(n,sp,pa,changed,pre,bright)))
        blob=repack(original)[0];selected,pcm,report=refine(target,blob,self.decoder,speech=False)
        self.assertTrue(report['accepted']);self.assertTrue(report['pwm_bytes_changed'])
        self.assertGreater(report['pwm_changed_samples'],0)
        self.assertLess(report['pwm_joint_score_delta'],0)
        self.assertLess(report['selected']['score'],report['baseline']['score'])
        self.assertTrue(_floors(report['selected'],report['baseline']))
        self.assertLessEqual(len(selected),len(blob))
        before=sparse.unpack(repack(blob,8)[0]);after=sparse.unpack(repack(selected,8)[0])
        self.assertEqual(before[:3],after[:3]);self.assertEqual(before[4:],after[4:])
        expanded=sparse.expand(repack(selected,8)[0])
        np.testing.assert_array_equal(self.decoder.decode_one_s16(expanded,n),pcm)
        np.testing.assert_array_equal(self.decoder.decode_one(expanded,n),pwm_duties(pcm))
        self.assertLessEqual(report['complete_candidates'],12)

    def test_inaudible_pcm_only_candidate_rolls_back(self):
        n=640;scale=next(i for i in range(32) if table('scale_table.inc')[i*8]>0)
        spectra=[[5,11,17,23,29,34,40,46,52,58]]*2
        params=[(scale,18,0)]*2;pulses=[(0,7)]*8
        blob=sparse.pack(n,spectra,params,pulses,0,0)
        changed=list(pulses);changed[0]=(1,7)
        target=sparse.decode_model(sparse.pack(n,spectra,params,changed,0,0))
        before=sparse.decode_model(blob)
        self.assertFalse(np.array_equal(target,before))
        np.testing.assert_array_equal(pwm_duties(target),pwm_duties(before))
        # Bypass proposal ranking to exercise the full hardware guard itself.
        with patch('refine_sparse80_pulses.proposals',return_value=[(1,0,1,7)]):
            selected,pcm,report=refine(target,blob,self.decoder,speech=False)
        self.assertEqual(selected,blob);np.testing.assert_array_equal(pcm,before)
        self.assertFalse(report['accepted']);self.assertEqual(report['alternatives'][0]['reason'],'unchanged_pwm')

    def test_validation_rejects_other_profiles_and_unbounded_settings(self):
        blob,_=sparse_fixture(320,pre=8192,bright=0);target=sparse.decode_model(blob)
        for invalid in (b'L9\x04'+b'\0'*10,b'L4HY\x05\x06'+b'\0'*20):
            with self.assertRaises(ValueError):refine(target,invalid,self.decoder)
        for invalid in (target.astype(float),target[:-1],target[:,None],target.astype(np.int64)+65536):
            with self.assertRaises(ValueError):refine(invalid,blob,self.decoder)
        for key,values in (('horizon',(True,0,80,321,1.5)),('full_candidates',(True,0,-1,33,1.5))):
            for invalid in values:
                with self.assertRaises(ValueError):refine(target,blob,self.decoder,**{key:invalid})
        for invalid in (1,'yes',None):
            with self.assertRaises(ValueError):refine(target,blob,self.decoder,frequency_guard=invalid)

    def test_lowband_gain_cannot_mask_highband_error(self):
        time=np.arange(6400)/8000
        source=np.rint(8000*np.sin(2*np.pi*200*time)+1000*np.sin(2*np.pi*2000*time)).astype(np.int16)
        baseline=np.rint(source+1000*np.sin(2*np.pi*200*time)+100*np.sin(2*np.pi*2000*time)).astype(np.int16)
        candidate=np.rint(source+200*np.sin(2*np.pi*2000*time)).astype(np.int16)
        before=band_diagnostics(source,baseline);after=band_diagnostics(source,candidate)
        # Aggregate error improves even on PWM, while the2kHz error grows.
        energy=lambda pcm:np.sum((source.astype(np.int64)-pwm_pcm16(pcm).astype(np.int64))**2)
        self.assertLess(energy(candidate),energy(baseline))
        self.assertGreater(after['pwm8']['band_error_totals'][0],before['pwm8']['band_error_totals'][0])
        self.assertFalse(band_error_floors(after['pwm8'],before['pwm8']))
        self.assertTrue(band_error_floors(before['pwm8'],before['pwm8']))

    def test_partial_tail_spike_and_missing_rows_fail_closed(self):
        for n in (1,2,159,160,161,639,640,641,801):
            source=np.zeros(n,np.int16);candidate=source.copy();candidate[-1]=10000
            before=band_diagnostics(source,source)['pwm8'];after=band_diagnostics(source,candidate)['pwm8']
            self.assertEqual(after['starts'],list(range(0,n,160)))
            self.assertEqual(after['valid_samples'][-1],n-after['starts'][-1])
            self.assertTrue(all(power>0 for power in after['error_power'][-1]))
            self.assertFalse(band_error_floors(after,before))
            corrupt=dict(before,error_power=before['error_power'][:-1],source_power=before['source_power'][:-1])
            self.assertFalse(band_error_floors(corrupt,before))

    def test_known_public_listening_rejection_fails_frequency_guard(self):
        # This tuning change was rejected as higher-frequency rasp. Catching
        # its aggregate/band tradeoff is a regression test, not a listening
        # preference claim for other clips or a perceptual validation set.
        from voice_input import load_voice_wav
        repo=Path(__file__).resolve().parents[4]
        source,_=load_voice_wav(repo/'web-player/audio/originals/chego.wav','preserve')
        original=(Path(__file__).parent/'fixtures/chego-2k-v8.lpx').read_bytes()
        n,sp,pa,pu,_,_=sparse.unpack(original)
        predecessor=sparse.pack(n,sp,pa,pu,13158,0)
        changed=list(pu)
        for packet,position,amplitude in ((85,11,-8),(59,15,7),(30,70,7),(84,25,7)):
            changed[packet]=(position,amplitude)
        rejected=sparse.pack(n,sp,pa,changed,13158,0)
        a=sparse.decode_model(predecessor);b=sparse.decode_model(rejected)
        for blob,pcm in ((predecessor,a),(rejected,b)):
            np.testing.assert_array_equal(self.decoder.decode_one_s16(sparse.expand(blob),n),pcm)
        before=band_diagnostics(source,a);after=band_diagnostics(source,b)
        self.assertFalse(band_error_floors(after['pwm8'],before['pwm8']))
        self.assertTrue(any(new>old for new,old in zip(after['pwm8']['band_error_totals'],before['pwm8']['band_error_totals'])))


if __name__=='__main__':unittest.main()

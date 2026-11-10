import unittest

import numpy as np
from batch_decoder import BatchSession
from test_speech_v9 import sparse_fixture
import speech_sparse80 as sparse
from speech_v9 import repack
from q0_model import coefficient_trace,table
from wav_lpc import pack_frames
from encode_low_bitrate_speech import trial_group
from enhance_sparse80 import beam,saturation_trial,enhance
from standard_metrics import pwm_duties


def geometry(blob):
    n,spectra,parameters,pulses,pre,bright=sparse.unpack(blob)
    vectors=[[(int(v)<<4)+8 for v in row] for row in spectra for _ in range(2)]
    co=coefficient_trace(pack_frames(vectors),len(spectra)*320)
    return n,spectra,np.asarray(parameters,np.int64),pulses,pre,bright,co


class SparseBeamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session=BatchSession('batch',speech=True,speech_compact=True,compact_only=True)
        cls.decoder=cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):cls.session.__exit__()

    def test_internal_guard_changes_only_proposal_cost(self):
        co=np.full((320,10),4096,np.int64)
        hist=np.full(10,32767,np.int64);ring=np.full(256,31,np.int64)
        target=np.arange(320,dtype=np.int64)*31
        for n in (1,19,79,80):
            ordinary=trial_group(target,co,hist,16384,0,ring,0,80,1024,18,14,0,7,13926,True,n)
            guarded=saturation_trial(target,co,hist,16384,0,ring,0,1024,18,14,0,7,13926,n)
            self.assertGreater(guarded[0],ordinary[0])
            for a,b in zip(guarded[1:],ordinary[1:]):np.testing.assert_array_equal(a,b)

    def test_unplayed_tail_cannot_change_pulse_decisions(self):
        for n in (1,79,80,81,319,321,641):
            blob,_=sparse_fixture(n,pre=8192,bright=0)
            _,_,parameters,_,pre,_,co=geometry(blob)
            target=np.zeros(len(co),np.int64);target[:n]=np.arange(n,dtype=np.int64)*71%30000-15000
            poisoned=target.copy();poisoned[n:]=32767
            for guard in (0,1,2):
                args=(co,parameters,table('scale_table.inc'),pre,2,guard,n)
                a,work=beam(target,*args);b,other_work=beam(poisoned,*args)
                np.testing.assert_array_equal(a,b);self.assertEqual(work,other_work)
                self.assertTrue(all(p in sparse.POSITIONS and amp in (-8,7) for p,amp in a))

    def test_first_group_matches_independent_exhaustive_trials(self):
        for n in (1,19,79,80):
            blob,_=sparse_fixture(n,pre=8192,bright=0)
            _,_,parameters,_,pre,_,co=geometry(blob);scale,lag,gain=parameters[0]
            target=np.zeros(len(co),np.int64);target[:n]=np.arange(n,dtype=np.int64)*113%30000-15000
            for guard in (0,1):
                scored=[]
                for code,position in enumerate(sparse.POSITIONS):
                    for sign,amplitude in enumerate((-8,7)):
                        result=trial_group(target,co,np.zeros(10,np.int64),0,0,np.zeros(256,np.int64),
                            0,80,table('scale_table.inc')[scale*8],lag,gain,position,amplitude,pre,guard,n)
                        scored.append((result[0],code,sign,position,amplitude))
                expected=min(scored)[3:]
                actual,_=beam(target,co,parameters,table('scale_table.inc'),pre,1,guard,n)
                self.assertEqual(tuple(actual[0]),expected)

    def test_native_v8_v9_rollback_and_complete_byte_budget(self):
        original,_=sparse_fixture(641,pre=8192,bright=0)
        target=sparse.decode_model(original)
        for blob in (original,repack(original)[0]):
            selected,pcm,report=enhance(target,blob,self.decoder,speech=False)
            self.assertEqual(selected,blob);self.assertFalse(report['accepted'])
            self.assertLessEqual(len(selected),len(blob))
            np.testing.assert_array_equal(pcm,target)
            canonical=repack(selected,8)[0] if selected[:2]==b'L9' else selected
            np.testing.assert_array_equal(self.decoder.decode_one(sparse.expand(canonical),len(target)),pwm_duties(pcm))

    def test_pulse_target_improvement_is_native_exact_and_preserves_metadata(self):
        original,_=sparse_fixture(1280,pre=8192,bright=0)
        n,sp,pa,pu,pre,bright=sparse.unpack(original)
        changed=[(p,-8 if amp==7 else 7) if i%3==0 else (p,amp) for i,(p,amp) in enumerate(pu)]
        target=sparse.decode_model(sparse.pack(n,sp,pa,changed,pre,bright))
        blob=repack(original)[0];selected,pcm,report=enhance(target,blob,self.decoder,speech=False)
        self.assertTrue(report['accepted']);self.assertLess(report['selected_score'],report['baseline_score'])
        self.assertLessEqual(len(selected),len(blob));self.assertFalse(report['decoder_changed'])
        canonical=repack(selected,8)[0];fields=sparse.unpack(canonical)
        # V9 intentionally omits inactive zero-gain lag fields. Compare the
        # actual v9 input's runtime metadata, not ignored v8-only values.
        self.assertEqual(fields[:3],sparse.unpack(repack(blob,8)[0])[:3])
        np.testing.assert_array_equal(pcm,self.decoder.decode_one_s16(sparse.expand(canonical),n))
        np.testing.assert_array_equal(self.decoder.decode_one(sparse.expand(canonical),n),pwm_duties(pcm))
        for invalid in (b'L9\x04'+b'\0'*10,b'L4HY\x05\x06'+b'\0'*20):
            with self.assertRaises(ValueError):enhance(target,invalid,self.decoder)


if __name__=='__main__':unittest.main()

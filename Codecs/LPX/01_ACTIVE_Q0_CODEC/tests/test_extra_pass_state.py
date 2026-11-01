"""Shared forward state preserves the full pass and owns its observations."""
import unittest

import numpy as np

from batch_decoder import BatchSession
from enhance_speech_compact import advance
import refine_speech_extras as extra
import speech_compact as compact
from standard_metrics import pwm_duties
from test_refine_speech_trajectory import seed, altered


def prefix_oracle(walk):
    return advance(walk._co,walk._pp,walk._ii,walk._working,walk._steps,
        walk._pre,walk._bright,0,walk.cursor,np.zeros(10,np.int64),0,0,np.zeros(256,np.int64))[1:]


def assert_prefix(test,walk):
    h,dd,cc,ring=prefix_oracle(walk)
    np.testing.assert_array_equal(walk._h,h)
    np.testing.assert_array_equal(walk._ring,ring)
    test.assertEqual((walk._dd,walk._cc),(dd,cc))


class ExtraPassStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session=BatchSession('batch',speech=True,speech_compact=True,compact_only=True)
        cls.decoder=cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):cls.session.__exit__()

    def test_manual_steps_match_complete_wrapper_with_gaps_and_stored_tail(self):
        fields=list(compact.unpack(seed(4,641)));fields[7][4]=fields[7][10]=(-1,0)
        blob=compact.pack(*fields[:7],extras=fields[7])[0]
        reference=compact.decode_model(altered(blob,[0,1]))
        for causal in (False,True):
            seen=[]
            _,_,report,_=extra.refine_existing_extras(reference,blob,self.decoder,max_bytes=len(blob),
                causal_positions=causal,speech=False,candidate_sink=lambda b,s:seen.append(b))
            walk=extra.ExistingExtraPass(reference,blob,max_bytes=len(blob),causal_positions=causal)
            self.assertEqual(walk.serialize(),blob)
            goals={row['target_active_groups']:row['candidate_id'] for row in report['checkpoints']}
            while walk.step():
                assert_prefix(self,walk)
                if walk.covered in goals:
                    self.assertEqual(walk.serialize(),seen[goals[walk.covered]])
            self.assertEqual(walk.trials,report['trial_evaluations'])
            self.assertEqual(walk.changed,report['changed_active_groups'])
            self.assertEqual(walk.visited,report['visited_group_indices'])
            self.assertEqual(walk.active,report['working_active_extras'])
            model=compact.decode_model(walk.serialize())
            np.testing.assert_array_equal(walk.synthesize(),model)
            np.testing.assert_array_equal(self.decoder.decode_one_s16(walk.serialize(),walk.n),model)
            np.testing.assert_array_equal(self.decoder.decode_one(walk.serialize(),walk.n),pwm_duties(model))

    def test_observations_and_returned_values_do_not_move_or_alias_prefix(self):
        blob=seed(4,641);reference=compact.decode_model(altered(blob,[0]))
        walk=extra.ExistingExtraPass(reference,blob,max_bytes=len(blob),causal_positions=True)
        self.assertTrue(walk.step())
        h,ring=walk._h.copy(),walk._ring.copy()
        scalars=(walk.cursor,walk.covered,walk.trials,walk.active,walk._dd,walk._cc)
        stream=walk.serialize();pcm=walk.synthesize();model=compact.decode_model(stream)
        pcm[:]=0
        self.assertEqual(walk.serialize(),stream)
        np.testing.assert_array_equal(walk.synthesize(),model)
        counts=walk.work_counts();counts['state_advances']=-1
        self.assertGreaterEqual(walk.work_counts()['state_advances'],1)
        np.testing.assert_array_equal(walk._h,h);np.testing.assert_array_equal(walk._ring,ring)
        self.assertEqual((walk.cursor,walk.covered,walk.trials,walk.active,walk._dd,walk._cc),scalars)
        self.assertTrue(walk.step());assert_prefix(self,walk)

    def test_atomic_trial_guard_does_not_change_progress_or_state(self):
        blob=seed(4,641);reference=compact.decode_model(altered(blob,[0]))
        walk=extra.ExistingExtraPass(reference,blob,max_bytes=len(blob),causal_positions=True,max_trial_evaluations=49)
        self.assertTrue(walk.step())
        before=(walk.covered,walk.trials,walk.cursor,list(walk.visited),walk.serialize())
        self.assertFalse(walk.step())
        self.assertEqual((walk.covered,walk.trials,walk.cursor,list(walk.visited),walk.serialize()),before)
        assert_prefix(self,walk)


if __name__=='__main__':unittest.main()

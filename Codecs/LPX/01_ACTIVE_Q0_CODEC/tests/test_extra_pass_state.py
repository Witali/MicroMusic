"""Shared forward state preserves the full pass and owns its observations."""
import unittest
from dataclasses import replace
from unittest.mock import patch

import numpy as np

from batch_decoder import BatchSession
from enhance_speech_compact import advance
import refine_speech_extras as extra
import speech_compact as compact
from standard_metrics import pwm_duties
from test_refine_speech_trajectory import seed, altered
from test_existing_extra_pass import cancellation


def prefix_oracle(walk):
    return advance(walk._co,walk._pp,walk._ii,walk._working,walk._steps,
        walk._pre,walk._bright,0,walk.cursor,np.zeros(10,np.int64),0,0,np.zeros(256,np.int64))[1:]


def assert_prefix(test,walk):
    h,dd,cc,ring=prefix_oracle(walk)
    np.testing.assert_array_equal(walk._h,h)
    np.testing.assert_array_equal(walk._ring,ring)
    test.assertEqual((walk._dd,walk._cc),(dd,cc))


def sparse():
    fields=list(compact.unpack(seed(4,961)))
    fields[5],fields[6]=8192,4096
    fields[7]=[(i%40,2) if i in (0,3,6,11,17,23) else (-1,0) for i in range(len(fields[7]))]
    fields[7][24]=(39,-8)  # Stored active pulse beyond the one-sample played tail.
    blob=compact.pack(*fields[:7],extras=fields[7])[0]
    return blob,compact.decode_model(altered(blob,[0,1]))


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

    def test_rejected_block_replays_restored_prefix_and_preserves_an_accepted_block(self):
        blob,reference=sparse()
        walk=extra.ExistingExtraPass(reference,blob,max_bytes=len(blob),causal_positions=True)
        with patch.object(extra,'refit_extra_group',side_effect=[(0,-4,0,1),(0,0,0,1),(0,7,0,1)]):
            self.assertTrue(walk.step())  # Accepted first group.
            accepted=walk.serialize();checkpoint=walk.snapshot()
            self.assertTrue(walk.step())  # Rejected next group, after a gap.
            cursor=walk.cursor;paid=(walk.covered,walk.trials,list(walk.visited),walk.changed)
            self.assertEqual(walk.active,walk.initial_active-1)
            walk.rollback(checkpoint)
            self.assertEqual(walk.serialize(),accepted)
            self.assertEqual(walk.cursor,cursor)
            self.assertEqual((walk.covered,walk.trials,list(walk.visited),walk.changed),paid)
            self.assertEqual(walk.active,walk.initial_active)
            self.assertEqual(walk.committed_changed_groups,1)
            assert_prefix(self,walk)
            self.assertTrue(walk.step())  # Next original group, never a revisit.
        self.assertEqual(walk.visited,[0,3,6])
        self.assertEqual(walk.changed,3)
        self.assertEqual(walk.committed_changed_groups,2)
        restored=compact.unpack(walk.serialize())
        self.assertEqual(restored[7][0],(0,-4))
        self.assertEqual(restored[7][3],compact.unpack(blob)[7][3])
        self.assertEqual(restored[7][6],(0,7))
        self.assertEqual(restored[7][24],(39,-8))
        self.assertEqual(walk.serialize()[:20],blob[:20])
        assert_prefix(self,walk)
        model=compact.decode_model(walk.serialize())
        np.testing.assert_array_equal(walk.synthesize(),model)
        np.testing.assert_array_equal(self.decoder.decode_one_s16(walk.serialize(),walk.n),model)
        np.testing.assert_array_equal(self.decoder.decode_one(walk.serialize(),walk.n),pwm_duties(model))
        counts=walk.work_counts()
        self.assertEqual((counts['rollback_attempts'],counts['rollback_calls'],counts['rollback_state_advances']),(1,1,1))
        self.assertEqual(counts['rollback_synthesized_samples'],cursor-checkpoint._cursor)
        self.assertGreaterEqual(counts['prefix_synthesized_samples'],counts['rollback_synthesized_samples'])

    def test_last_extra_removal_rollback_restores_active_count_and_original_bytes(self):
        blob,target=cancellation()
        walk=extra.ExistingExtraPass(compact.decode_model(target),blob,max_bytes=len(blob),causal_positions=True)
        checkpoint=walk.snapshot()
        with patch.object(extra,'refit_extra_group',return_value=(-1,0,0,1)):
            self.assertTrue(walk.step())
        self.assertEqual(walk.active,0)
        reduced=walk.serialize()
        self.assertTrue(reduced[5]&128)
        self.assertEqual(reduced[:20],blob[:20])
        self.assertLess(len(reduced),len(blob))
        walk.rollback(checkpoint)
        self.assertEqual(walk.active,1)
        self.assertEqual(walk.serialize(),blob)
        self.assertEqual(walk.committed_changed_groups,0)
        self.assertFalse(walk.step())
        self.assertEqual(walk.visited,[5])
        assert_prefix(self,walk)

    def test_rollback_never_refunds_trial_or_group_budget(self):
        blob,reference=sparse()
        walk=extra.ExistingExtraPass(reference,blob,max_bytes=len(blob),causal_positions=True,max_trial_evaluations=49)
        checkpoint=walk.snapshot()
        self.assertTrue(walk.step())
        paid=(walk.trials,walk.covered,list(walk.visited),walk.changed,walk.cursor)
        walk.rollback(checkpoint)
        self.assertEqual((walk.trials,walk.covered,list(walk.visited),walk.changed,walk.cursor),paid)
        self.assertFalse(walk.step())
        self.assertEqual(walk.serialize(),blob)
        self.assertEqual(walk.work_counts()['rollback_synthesized_samples'],walk.cursor)
        assert_prefix(self,walk)

    def test_checkpoint_is_owned_readonly_and_foreign_future_or_stale_restore_is_rejected(self):
        blob,reference=sparse()
        walk=extra.ExistingExtraPass(reference,blob,max_bytes=len(blob))
        other=extra.ExistingExtraPass(reference,blob,max_bytes=len(blob))
        checkpoint=walk.snapshot()
        for saved,live in ((checkpoint._extras,walk._working),(checkpoint._h,walk._h),(checkpoint._ring,walk._ring)):
            self.assertFalse(np.shares_memory(saved,live))
            self.assertFalse(saved.flags.writeable)
        self.assertTrue(walk.step())
        before=(walk.serialize(),walk.covered,walk.trials,walk.cursor)
        with self.assertRaisesRegex(ValueError,'another'):
            walk.rollback(other.snapshot())
        with self.assertRaisesRegex(ValueError,'ahead'):
            walk.rollback(replace(checkpoint,_covered=walk.covered+1))
        self.assertEqual((walk.serialize(),walk.covered,walk.trials,walk.cursor),before)
        walk.rollback(checkpoint)
        fresh=walk.snapshot()
        with self.assertRaisesRegex(ValueError,'Stale'):
            walk.rollback(checkpoint)
        self.assertEqual(walk.serialize(),blob)
        # A fresh checkpoint at the same paid boundary is a valid no-op restore.
        walk.rollback(fresh)
        self.assertEqual(walk.work_counts()['rollback_calls'],2)
        assert_prefix(self,walk)

    def test_failed_replay_does_not_partially_install_protected_fields_or_dsp_state(self):
        blob,reference=sparse()
        walk=extra.ExistingExtraPass(reference,blob,max_bytes=len(blob),causal_positions=True)
        checkpoint=walk.snapshot();self.assertTrue(walk.step())
        stream=walk.serialize();h,ring=walk._h.copy(),walk._ring.copy()
        scalars=(walk.active,walk.covered,walk.trials,walk.cursor,walk._dd,walk._cc)
        with patch.object(extra,'advance',side_effect=RuntimeError('Injected replay failure')):
            with self.assertRaisesRegex(RuntimeError,'Injected'):
                walk.rollback(checkpoint)
        self.assertEqual(walk.serialize(),stream)
        np.testing.assert_array_equal(walk._h,h);np.testing.assert_array_equal(walk._ring,ring)
        self.assertEqual((walk.active,walk.covered,walk.trials,walk.cursor,walk._dd,walk._cc),scalars)
        self.assertEqual(walk.work_counts()['rollback_attempts'],1)
        self.assertEqual(walk.work_counts()['rollback_calls'],0)
        walk.rollback(checkpoint)
        self.assertEqual(walk.serialize(),blob)
        self.assertEqual(walk.work_counts()['rollback_attempts'],2)
        self.assertEqual(walk.work_counts()['rollback_calls'],1)
        assert_prefix(self,walk)


if __name__=='__main__':unittest.main()

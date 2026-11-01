"""Pure negative controls for the independent saved-only decision audit."""
from copy import deepcopy
import unittest

from audit_saved import flags,choose,outcome,dominates


def baseline():
    return dict(metrics={k:dict(error_energy=100,stoi=.8) for k in ('pcm16','pwm8')},
        clipped_samples=1,voice=dict(within_tolerance_frames=10),pwm_voice=dict(within_tolerance_frames=9),score=1.)


class SavedAuditTests(unittest.TestCase):
    def test_period_missing_stoi_and_joint_floors_are_independent(self):
        old=baseline();new=deepcopy(old)
        self.assertTrue(all(flags(new,old).values()))
        new['metrics']['pwm8']['stoi']=None
        self.assertFalse(flags(new,old)['old_pcm_pwm_floors_passed'])
        new=deepcopy(old);new['voice']['within_tolerance_frames']=9
        self.assertFalse(flags(new,old)['pcm_period_coverage_floor_passed'])
        self.assertTrue(flags(new,old)['pwm_period_coverage_floor_passed'])
        new=deepcopy(old);new['score']+=5e-13
        self.assertTrue(flags(new,old)['joint_objective_nonregression'])
        new['score']+=1e-10
        self.assertFalse(flags(new,old)['joint_objective_nonregression'])

    def test_fitting_rejected_raw_is_not_a_no_fit_or_automatic_admission(self):
        rows=[dict(id=0,stream_bytes=100,score=1.,automatic_quality_eligible=True),
              dict(id=1,stream_bytes=90,score=.9,automatic_quality_eligible=False)]
        self.assertEqual(choose(rows,100)['selected_id'],0)
        lower=choose(rows,90)
        self.assertIsNone(lower['selected_id']);self.assertEqual(lower['raw_id'],1)
        self.assertFalse(lower['no_fit']);self.assertTrue(lower['no_automatic_admission'])
        self.assertTrue(choose(rows,80)['no_fit'])

    def test_own_arm_win_cannot_be_credited_as_a_context_frontier_extension(self):
        weaker=dict(score=1.,stream_bytes=100)
        new=dict(score=.9,stream_bytes=100)
        self.assertTrue(outcome(weaker,new,True,True)['exact_primary_success'])
        prior=dict(score=.8,stream_bytes=100,automatic_quality_eligible=True)
        self.assertTrue(dominates(prior,new))
        self.assertFalse(outcome(prior,new,True,True)['exact_primary_success'])
        self.assertFalse(outcome(weaker,new,False,True)['exact_primary_success'])
        self.assertFalse(outcome(weaker,new,True,False)['exact_primary_success'])


if __name__=='__main__':unittest.main()

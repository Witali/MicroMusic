"""Saved-result projection contracts; no codec execution or metric work."""
import unittest
from project_pilot import outcome,rejected,COMPARISONS


def row(score=1.,size=100):return dict(score=score,stream_bytes=size)


def value():
    return dict(old_pcm_pwm_floors_passed=True,clipped_sample_floor_passed=True,
        pcm_period_coverage_floor_passed=True,pwm_period_coverage_floor_passed=True,
        joint_objective_nonregression=True,metrics={d:dict(error_energy=100,stoi=.5) for d in ('pcm16','pwm8')})


class Projection(unittest.TestCase):
    def test_admission_and_no_fit_comparisons(self):
        self.assertEqual(outcome(None,None),'neither-admitted')
        self.assertEqual(outcome(row(),None),'left-only')
        self.assertEqual(outcome(None,row()),'right-only')

    def test_actual_byte_tie_break(self):
        self.assertEqual(outcome(row(),row()),'exact-rank-tie')
        self.assertEqual(outcome(row(size=99),row()),'left-smaller-score-tie')
        self.assertEqual(outcome(row(),row(size=99)),'right-smaller-score-tie')
        self.assertEqual(outcome(row(.9,101),row()),'left-lower-score')

    def test_period_failures_remain_explicit(self):
        base=value();new=value();new['pcm_period_coverage_floor_passed']=False
        self.assertEqual(rejected(new,base),['pcm_period_coverage_floor_passed'])

    def test_sse_stoi_details_and_tolerance(self):
        base=value();new=value();new['old_pcm_pwm_floors_passed']=False
        new['metrics']['pcm16']['error_energy']=101;new['metrics']['pwm8']['stoi']=.49
        self.assertEqual(set(rejected(new,base)),{'old_pcm_pwm_floors_passed','pcm16_sse','pwm8_stoi'})
        new=value();new['metrics']['pwm8']['stoi']=.5-5e-13
        self.assertEqual(rejected(new,base),[])

    def test_no_music_stoi_claim(self):
        base=value();new=value()
        for d in ('pcm16','pwm8'):base['metrics'][d]['stoi']=new['metrics'][d]['stoi']=None
        self.assertEqual(rejected(new,base),[])

    def test_fixed_primary_and_screening_comparisons(self):
        self.assertEqual(len(COMPARISONS),7)
        self.assertIn(('generation','T-full-0','G-full-0'),COMPARISONS)
        self.assertIn(('price-.1','G-full-0','G-full-.1'),COMPARISONS)
        self.assertIn(('screening-ablation','T-local-0','T-full-0'),COMPARISONS)


if __name__=='__main__':unittest.main()

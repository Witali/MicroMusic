"""Contracts for descriptive saved-value diagnostics, not relaxed admission."""
import unittest
from diagnose_pilot import non_sse


def point():
    return dict(metrics={d:dict(error_energy=100,stoi=.5) for d in ('pcm16','pwm8')},
        pcm_period_coverage_floor_passed=True,pwm_period_coverage_floor_passed=True,
        clipped_sample_floor_passed=True,joint_objective_nonregression=True,
        noise=dict(score=1.),pwm_noise=dict(score=1.))


class Diagnostics(unittest.TestCase):
    def test_sse_only_and_joint_are_separate(self):
        base=point();row=point();row['metrics']['pcm16']['error_energy']=101
        self.assertTrue(non_sse(row,base)['only_sse_common_gate_failure'])
        row['joint_objective_nonregression']=False
        result=non_sse(row,base)
        self.assertTrue(result['f0_stoi_clip_noise_pass'])
        self.assertFalse(result['only_sse_common_gate_failure'])

    def test_noise_diagnostic_cannot_replace_common_gates(self):
        base=point();row=point();row['noise']['score']=1.1
        self.assertFalse(non_sse(row,base)['f0_stoi_clip_noise_pass'])
        row['noise']['score']=1.;row['pwm_period_coverage_floor_passed']=False
        self.assertFalse(non_sse(row,base)['f0_stoi_clip_noise_pass'])

    def test_stoi_tolerance_and_nonspeech(self):
        base=point();row=point();row['metrics']['pcm16']['stoi']=.5-5e-13
        self.assertTrue(non_sse(row,base)['stoi_pass'])
        base['metrics']['pcm16']['stoi']=None;row['metrics']['pcm16']['stoi']=None
        self.assertTrue(non_sse(row,base)['stoi_pass'])


if __name__=='__main__':unittest.main()

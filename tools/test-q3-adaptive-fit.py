"""Protect exact baseline matching and upper selectors during refinement."""
import importlib.util
from copy import deepcopy
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('adaptive_fit_contracts',ROOT/'tools/refine-q3-adaptive.py')
fit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fit;spec.loader.exec_module(fit)
spec=importlib.util.spec_from_file_location('adaptive_joint_contracts',ROOT/'tools/search-q3-adaptive.py')
joint=importlib.util.module_from_spec(spec);sys.modules[spec.name]=joint;spec.loader.exec_module(joint)


class FitTests(unittest.TestCase):
    def test_repacking_preserves_the_upper_selected_wave_during_gain_edits(self):
        f=np.array([[40,m*16+3,0x88,0x88,0x88,0x88] for m in range(8)],np.uint8)
        d=np.full(8,128,np.uint16);b=np.zeros((8,16),np.int8);b[:,0]=np.arange(8)-7
        original=fit.probe.search.State(f,d,b,False,1)
        result=fit.apply(original,('gain',7,0,1))
        self.assertEqual(int(result.frames[7,1])&15,4)
        np.testing.assert_array_equal(result.book[int(result.frames[7,1])>>4],b[7])
        np.testing.assert_array_equal(original.frames,f)

    def test_exact_match_is_preserved_and_a_frequency_change_is_rejected(self):
        f,d,b,_=fit.probe.builder.load_model(ROOT/'ATtiny13A/Sound/research/q3-pulsebook8/refit-four-tap/guarded/model.json')
        original=fit.probe.codec.render(f,d,b)[0]
        reference=(original.astype(float)-128)/128
        objective=fit.Objective(reference);state=fit.probe.search.State(f,d,b,False,1)
        score=objective.evaluate(state)
        self.assertIsNotNone(score);self.assertAlmostEqual(score['spectrogram_loss'],0.,places=12)
        objective.limits=score
        self.assertEqual(objective.evaluate(state),score)
        index=int(np.flatnonzero((state.frames[:,0]>3)&((state.frames[:,1]&15)>0))[0])
        changed=fit.apply(state,('pitch',index,0,1))
        self.assertIsNone(objective.evaluate(changed))
        self.assertTrue(objective.rejected)

    def test_bounded_sweep_interleaves_source_filter_and_timing_changes(self):
        f,d,b,_=fit.probe.builder.load_model(ROOT/'ATtiny13A/Sound/research/q3-pulsebook8/refit-four-tap/guarded/model.json')
        sequence=fit.actions(fit.probe.search.State(f,d,b,False,1))
        self.assertEqual({a[0] for a in sequence[:9]},
            {'tap','tap_pair','pitch','gain','mode','coefficient_run','coefficient_frame','boundary','pitch_block'})

    def baseline(self):
        return dict(stoi=.85,estoi=.66,spectrogram_loss=.49,raw_mean=.07,partial_violation_power=.7,
            harmonic_metrics=dict(frequency_error_cents=57.,frequency_trajectory_error=1.1,
                level_error_db=7.5,harmonic_track_loss=1.,missing_reference_energy=.19))

    def test_a_better_global_spectrum_cannot_hide_worse_frequency_or_intelligibility(self):
        baseline=self.baseline();candidate=deepcopy(baseline);candidate['spectrogram_loss']=.48
        for key in ('stoi','estoi'):
            worse=deepcopy(candidate);worse[key]-=.001
            self.assertFalse(joint.guarded(worse,baseline))
        for key in baseline['harmonic_metrics']:
            worse=deepcopy(candidate);worse['harmonic_metrics'][key]+=.001
            self.assertFalse(joint.guarded(worse,baseline))

    def test_complete_matching_guard_keeps_the_baseline_and_accepts_joint_improvements(self):
        baseline=self.baseline();self.assertTrue(joint.guarded(baseline,baseline))
        better=deepcopy(baseline);better.update(stoi=.86,estoi=.67,spectrogram_loss=.48,raw_mean=-.06,partial_violation_power=.69)
        better['harmonic_metrics']={k:v*.99 for k,v in baseline['harmonic_metrics'].items()}
        self.assertTrue(joint.guarded(better,baseline))
        better['partial_violation_power']=.71
        self.assertFalse(joint.guarded(better,baseline))


if __name__=='__main__':unittest.main()

"""Meaningful pure planning/progress and fixed-scope contracts."""
import copy
import os
from pathlib import Path
import unittest

from anchor_policy import ARMS,settings,validate_counters,compare_nominated,validate_scope,priority_plan,repeat_savings
from anchor_runtime import Inputs,load_manifest,bind_production,bridge_native


def job(i):return dict(arm=ARMS[i],new_generation=i>=2,anchor_order='priority' if i%2 else 'time')


def report():
    return dict(anchor_order='priority',nominated_anchors=[0,1,4],planned_anchors=[4,0,1],
        started_anchors=[4,0],completed_anchors=[4],completed_windows=1,frame_limit=64,
        checkpoints=[dict(anchor=4,status='complete')],refit_calls_started=2,refit_calls_completed=2,
        repeat_spectrum_opportunities=2,repeat_spectrum_proposals=1,rate_allocation_calls_started=1,
        completed_rate_allocation_calls=0,joint_candidates_completed=3,refit_candidates_completed=1)


class AnchorPolicy(unittest.TestCase):
    def test_four_arms_share_full_sse_and_zero_price(self):
        rows=[settings(job(i)) for i in range(4)]
        self.assertEqual([r['rate_search'] for r in rows],[False,False,True,True])
        self.assertEqual([r['anchor_order'] for r in rows],['time','priority','time','priority'])
        self.assertTrue(all(r['screening']=='full' and r['rate_lambda']==0. and r['objective'] is None for r in rows))
        self.assertEqual([r['allocation_evaluations'] for r in rows],[0,0,256,256])

    def test_arm_mapping_cannot_change(self):
        bad=job(1);bad['anchor_order']='time'
        with self.assertRaises(ValueError):settings(bad)

    def test_interrupted_prefix_rebuild_has_no_checkpoint(self):
        validate_counters(report())
        r=report();r.update(started_anchors=[4],completed_anchors=[],completed_windows=0,checkpoints=[])
        validate_counters(r)

    def test_starts_and_completions_follow_the_static_plan(self):
        for key,value in (('started_anchors',[0]),('completed_anchors',[0]),('planned_anchors',[4,4,0])):
            r=report();r[key]=value
            with self.assertRaises(AssertionError):validate_counters(r)

    def test_temporal_order_is_ascending(self):
        r=report();r['anchor_order']='time'
        with self.assertRaises(AssertionError):validate_counters(r)
        r.update(planned_anchors=[0,1,4],started_anchors=[0],completed_anchors=[],completed_windows=0,checkpoints=[])
        validate_counters(r)

    def test_only_one_active_atomic_call_is_unfinished(self):
        for key in ('refit_calls_started','repeat_spectrum_opportunities','rate_allocation_calls_started'):
            r=report();r[key]+=3
            with self.assertRaises(AssertionError):validate_counters(r)

    def test_pair_uses_the_same_nominated_set(self):
        left,right=report(),report();right['planned_anchors']=[0,1,4]
        compare_nominated(left,right)
        right['nominated_anchors']=[0,1,5]
        with self.assertRaises(AssertionError):compare_nominated(left,right)

    def test_synthetic_bound_is_separate(self):
        r=settings(job(3),synthetic=True)
        self.assertEqual((r['frame_limit'],r['beam_width'],r['max_evaluations']),(1,1,32))
        self.assertEqual(r['allocation_evaluations'],256)

    def test_priority_queues_skip_duplicates_without_losing_turn(self):
        result=priority_plan([0,1,2,3],{0:20,1:30,2:40,3:10},{0:8,1:10,2:9})
        self.assertEqual(result,[1,2,0,3])

    def test_priority_ties_empty_rate_and_no_extra_anchors(self):
        self.assertEqual(priority_plan([1,3,5],{1:4,3:4,5:2},{}),[1,3,5])
        self.assertEqual(priority_plan([1,3,5],{1:4,3:4,5:2},{99:999,5:1}),[5,1,3])

    def test_repeat_feature_includes_changed_following_delta(self):
        # Toy exact field cost verifies the two-boundary feature independently.
        cost=lambda a,b,p:abs(a-b)
        self.assertEqual(repeat_savings([0,10,11],4,cost),{2:1})

    def test_refit_call_return_is_not_scored_candidate_completion(self):
        r=report();validate_counters(r)
        r['refit_candidates_completed']=3
        with self.assertRaises(AssertionError):validate_counters(r)

    @unittest.skipUnless(os.environ.get('ANCHOR_BASELINES'),'Private prepared binding is opt-in')
    def test_actual_saved_scope_and_no_individual_reset_cap(self):
        inputs=Inputs();m=load_manifest(Path(os.environ['ANCHOR_BASELINES']),inputs);bases=validate_scope(m)
        self.assertEqual(len(m['jobs']),48)
        for profile in (4,6):
            group=[j for j in m['jobs'] if j['profile']==profile]
            self.assertEqual(len(group),24);self.assertEqual(sum(len(j['reset_indices']) for j in group),40)
        multi=[j for j in m['jobs'] if len(j['reset_indices'])>1]
        self.assertTrue(all(j['local_byte_cap']>max(p['file_bytes'] for p in bases[j['baseline_id']]['segments']) for j in multi))
        bad=copy.deepcopy(m);bad['jobs'][0]['reset_indices']=[]
        with self.assertRaises(ValueError):validate_scope(bad)
        self.assertTrue(m['prior_pilot_winners_excluded'])
        source=Path(os.environ['ANCHOR_SOURCE'])
        bind_production(source,'55ebc0d94e919fa7aeec4819e3bf83cfaf81fa6a')
        native,bridge=bridge_native(source,Path(os.environ['ANCHOR_NATIVE_CASES']),inputs)
        self.assertEqual(set(native),{'common','v5-only'});self.assertEqual(bridge['new_native_builds'],0)
        inputs.verify()


if __name__=='__main__':unittest.main()

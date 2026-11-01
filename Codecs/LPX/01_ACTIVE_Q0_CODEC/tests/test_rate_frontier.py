"""Cross-rate endpoints, real serialized costs and interruption ownership."""
import unittest

import numpy as np

import speech_compact as compact
from batch_decoder import BatchSession
from search_cpu_budget import CpuBudgetExceeded
from speech_rate_allocation import allocation_frontier, bit_accounting, distortion_rate
from standard_metrics import pwm_duties
from test_speech_rate_allocation import fields, snapshot_renderer


def fixture(profile=4,n=320,active=((0,3,1),(1,7,7))):
    values=fields(profile,n)
    added=np.full((len(values[2])*8,2),(-1,0),np.int64)
    for index,position,amplitude in active:added[index]=(position,amplitude)
    values[7]=added
    return values


def callbacks(values,losses=None):
    def serialize(added):return compact.pack(*values[:7],extras=added)[0]
    def render(added):
        if losses is None:return snapshot_renderer(values)(added)
        state=tuple(int(v!=0) for v in added[:,1])
        pcm=np.zeros(values[0],np.int64);pcm[0]=losses(state)
        return pcm
    def objective(pcm):return int(pcm[0]) if losses is not None else int(np.sum(pcm.astype(np.int64)**2))
    return dict(render=render,objective=objective,serialize=serialize,stop=values[0])


class RateFrontierTests(unittest.TestCase):
    def test_weak_removal_wins_rd_below_cap_and_keeps_original_distortion_anchor(self):
        values=fixture()
        # Dropping the weak pulse costs 1 D; dropping the strong one costs 1000.
        args=callbacks(values,lambda state:(1-state[0])+1000*(1-state[1]))
        cap=len(args['serialize'](values[7]))
        pure=allocation_frontier(values[2],4,values[7],cap,rate_lambda=0,**args)
        priced=allocation_frontier(values[2],4,values[7],cap,rate_lambda=1,**args)
        self.assertEqual(pure.points[0].score,0)
        self.assertEqual(priced.points[0].score,1)
        self.assertLess(priced.points[0].file_bytes,cap)
        self.assertEqual(priced.unchanged.score,priced.control.score)
        self.assertEqual(priced.unchanged.score,0)
        self.assertTrue(priced.anchors_complete)
        self.assertEqual(priced.evaluations,priced.serialization_calls)
        self.assertEqual(priced.evaluations,priced.objective_evaluations)
        self.assertLess(distortion_rate(priced.points[0].score,priced.points[0].file_bytes,1),
                        distortion_rate(priced.unchanged.score,cap,1))

    def test_last_extra_marker_cliff_is_evaluated_before_the_removal_walk(self):
        values=fixture(6,641,((0,3,1),(8,4,2),(23,39,7)))
        def loss(state):return 0 if sum(state) else 20
        args=callbacks(values,loss);cap=len(args['serialize'](values[7]));events=[]
        result=allocation_frontier(values[2],6,values[7],cap,rate_lambda=1,
            max_evaluations=2,on_candidate=lambda point:events.append(point),**args)
        self.assertEqual(result.status,'evaluation_limit')
        self.assertEqual(len(events),2)
        self.assertIn('suffix-all-off',events[1].labels)
        self.assertEqual(result.points[0].cost['extra_marker_bits'],0)
        self.assertEqual(result.points[0].cost['extra_value_bits'],0)
        self.assertGreater(cap-result.points[0].file_bytes,3*10//8)
        self.assertEqual(result.suffix_all_off.stream,result.points[0].stream)

    def test_removal_ranking_refreshes_after_each_coupled_state(self):
        values=fixture(active=((0,0,1),(1,0,2),(2,0,3)))
        losses={(1,1,1):0,(0,1,1):1,(1,0,1):4,(1,1,0):9,
                (0,0,1):100,(0,1,0):16,(1,0,0):25,(0,0,0):200}
        args=callbacks(values,lambda state:losses[state[:3]])
        result=allocation_frontier(values[2],4,values[7],100,removal_steps=2,**args)
        self.assertEqual([row['removed_chunk'] for row in result.removal_rounds],[0,2])
        self.assertEqual(result.exhaustive_rounds,2)
        self.assertEqual(result.partial_rounds,0)
        self.assertEqual(result.status,'bounded_complete')

    def test_limits_keep_fitting_control_and_publish_partial_batch_without_exact_claim(self):
        values=fixture(active=((0,0,1),(1,0,2),(2,0,3),(3,0,4)))
        args=callbacks(values,lambda state:sum((i+1)*(not value) for i,value in enumerate(state)))
        cap=len(args['serialize'](values[7]))-1
        one=allocation_frontier(values[2],4,values[7],cap,max_evaluations=1,**args)
        self.assertIsNone(one.unchanged)
        self.assertIsNotNone(one.control)
        self.assertTrue(one.feasible)
        self.assertFalse(one.anchors_complete)
        self.assertEqual(one.status,'evaluation_limit')
        events=[]
        limited=allocation_frontier(values[2],4,values[7],cap,max_evaluations=4,
            candidate_batch=4,on_candidate=lambda point:events.append(point),**args)
        self.assertEqual(limited.evaluations,4)
        self.assertEqual(len(events),4)
        self.assertEqual(limited.partial_rounds,1)
        self.assertFalse(limited.removal_rounds[0]['exhaustive'])
        self.assertEqual(limited.removal_rounds[0]['partial_reason'],'evaluation_limit')
        bounded=allocation_frontier(values[2],4,values[7],cap,candidate_batch=1,removal_steps=2,**args)
        self.assertEqual(bounded.partial_rounds,2)
        self.assertTrue(all(row['partial_reason']=='candidate_batch' for row in bounded.removal_rounds))

    def test_completed_callback_precedes_next_deadline_and_owns_its_arrays(self):
        values=fixture();args=callbacks(values,lambda state:sum(state));events=[];checks=[]
        def checkpoint():
            checks.append(len(events))
            if len(events)==2:raise CpuBudgetExceeded
        def publish(point):
            events.append(point.stream)
            point.extras[:]=0;point.pcm[:]=30000;point.cost['file_bytes']=-1
        with self.assertRaises(CpuBudgetExceeded):
            allocation_frontier(values[2],4,values[7],100,checkpoint=checkpoint,on_candidate=publish,**args)
        self.assertEqual(checks,[0,1,2])
        self.assertEqual(len(events),2)
        self.assertNotEqual(events[0],events[1])
        seen=[]
        result=allocation_frontier(values[2],4,values[7],100,on_candidate=lambda point:seen.append(point),**args)
        original=result.unchanged.extras.copy()
        seen[0].extras[:]=0;seen[0].pcm[:]=1234;seen[0].cost['file_bytes']=-1
        np.testing.assert_array_equal(result.unchanged.extras,original)
        self.assertGreater(result.unchanged.file_bytes,0)
        for point in result.points:
            point.extras[:]=0;point.cost['file_bytes']=-1
        np.testing.assert_array_equal(result.unchanged.extras,original)

    def test_cached_prefix_tail_and_callback_arguments_are_owned(self):
        values=fixture(6,321,((0,3,7),(8,0,1),(15,39,2)))
        original=values[7].copy();spectra=np.asarray(values[2]).copy();events=[]
        args=callbacks(values,lambda state:sum(state))
        serialize=args['serialize'];render=args['render']
        def owned_serialize(added):
            stream=serialize(added);added[:]=0
            return stream
        def owned_render(added):
            pcm=render(added);added[:]=0
            return pcm
        result=allocation_frontier(values[2],6,values[7],1000,start=320,
            render=owned_render,objective=args['objective'],serialize=owned_serialize,
            stop=321,on_candidate=lambda point:events.append(point))
        for point in events+[result.suffix_all_off]:
            np.testing.assert_array_equal(point.extras[:8],original[:8])
            self.assertEqual(point.file_bytes,len(point.stream))
        self.assertEqual(result.suffix_all_off.cost['extra_marker_bits'],16)
        self.assertTrue(np.all(result.suffix_all_off.extras[8:,1]==0))
        np.testing.assert_array_equal(values[7],original)
        np.testing.assert_array_equal(values[2],spectra)

    def test_endpoint_roles_dedup_and_max_points_are_deterministic(self):
        values=fixture(active=((0,0,1),(1,0,2)))
        args=callbacks(values,lambda state:0 if sum(state)==2 else 1 if sum(state)==1 else 100)
        events=[]
        result=allocation_frontier(values[2],4,values[7],100,rate_lambda=1,
            on_candidate=lambda point:events.append(point),**args)
        self.assertEqual(len(result.points),3)
        self.assertEqual(len({point.stream for point in events}),result.evaluations)
        for limit in (1,2,3):
            other=allocation_frontier(values[2],4,values[7],100,rate_lambda=1,max_points=limit,**args)
            self.assertEqual([point.stream for point in other.points],
                             [point.stream for point in result.points[:limit]])
        all_off=fixture(active=());off_args=callbacks(all_off,lambda state:0);off_events=[]
        same=allocation_frontier(all_off[2],4,all_off[7],100,on_candidate=off_events.append,**off_args)
        self.assertEqual(same.evaluations,1)
        self.assertEqual(len(same.points),1)
        self.assertEqual(len(off_events),1)
        self.assertTrue(same.anchors_complete)

    def test_bad_inputs_and_wrong_same_length_serialized_fields_fail(self):
        values=fixture();args=callbacks(values,lambda state:0)
        for settings in ({'max_bytes':True},{'max_evaluations':0},{'max_evaluations':4097},{'candidate_batch':0},
                         {'removal_steps':-1},{'max_points':4},{'start':1},{'start':360},
                         {'stop':321},{'rate_lambda':float('nan')},{'checkpoint':False},
                         {'on_candidate':False}):
            options=dict(max_bytes=100,**args);options.update(settings)
            with self.assertRaises(ValueError):allocation_frontier(values[2],4,values[7],**options)
        options=dict(args);options['render']=lambda added:np.zeros(321,np.int64)
        with self.assertRaises(ValueError):allocation_frontier(values[2],4,values[7],100,**options)
        options=dict(args);options['objective']=lambda pcm:float('inf')
        with self.assertRaises(ValueError):allocation_frontier(values[2],4,values[7],100,**options)
        options=dict(args);options['serialize']=lambda added:b'bad'
        with self.assertRaises(AssertionError):allocation_frontier(values[2],4,values[7],100,**options)
        def wrong(added):
            added=added.copy();added[0,0]+=1
            return args['serialize'](added)
        options=dict(args);options['serialize']=wrong
        with self.assertRaisesRegex(AssertionError,'requested'):
            allocation_frontier(values[2],4,values[7],100,**options)
        calls=[]
        def moving_fixed_fields(added):
            calls.append(1);data=list(values)
            if len(calls)>1:
                data[3]=[(scale,lag+1,gain) for scale,lag,gain in data[3]]
            return compact.pack(*data[:7],extras=added)[0]
        options=dict(args);options['serialize']=moving_fixed_fields
        with self.assertRaisesRegex(AssertionError,'fixed parameters'):
            allocation_frontier(values[2],4,values[7],100,**options)

    def test_no_fit_is_a_finite_fixed_fields_result_with_no_promoted_points(self):
        values=fixture(6,641,((0,3,7),(8,0,1),(23,39,2)))
        args=callbacks(values,lambda state:sum(state))
        base=bit_accounting(values[2],6)['file_bytes']
        result=allocation_frontier(values[2],6,values[7],base-1,**args)
        self.assertFalse(result.feasible)
        self.assertEqual(result.points,[])
        self.assertIsNotNone(result.unchanged)
        self.assertIsNotNone(result.control)

    def test_actual_model_common_and_v5_native_pcm_pwm_include_partial_tail(self):
        with BatchSession('batch',speech=True,speech_compact=True) as common, \
             BatchSession('batch',speech=True,speech_compact=True,compact_only=True) as v5:
            for profile,n in ((4,321),(6,641)):
                values=fixture(profile,n,((0,3,1),(8,0,-2),(len(fields(profile,n)[2])*8-1,39,7)))
                args=callbacks(values);events=[];cap=len(args['serialize'](values[7]))-1
                result=allocation_frontier(values[2],profile,values[7],cap,
                    max_evaluations=16,on_candidate=events.append,**args)
                self.assertTrue(result.feasible)
                for point in events:
                    model=compact.decode_model(point.stream)
                    np.testing.assert_array_equal(point.pcm,model)
                    self.assertEqual(point.cost,bit_accounting(values[2],profile,point.extras))
                    for decoder in (common,v5):
                        np.testing.assert_array_equal(decoder.decode_one_s16(point.stream,n),model)
                        np.testing.assert_array_equal(decoder.decode_one(point.stream,n),pwm_duties(model))


if __name__=='__main__':unittest.main()

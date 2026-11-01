"""Exact stored costs and state-coupled marginal removals, independently rendered."""
import unittest
import numpy as np

import speech_compact as compact
from batch_decoder import BatchSession
from enhance_speech_compact import advance
from q0_model import coefficient_trace, table
from speech_rate_allocation import (bit_accounting, extra_capacity, fit_capacity,
    reclaim_extras, improve_extras, spectrum_bits, distortion_rate)
from test_speech_v4 import fixture
from wav_lpc import pack_frames


def fields(profile=6,n=960):
    values=list(compact.unpack(compact.repack(fixture(profile,n))[0]))
    values[3]=[(25,18,14)]*len(values[3]);values[5]=13926;values[6]=6000
    return values


def snapshot_renderer(values):
    n,profile,sp,params,pulses,pre,bright=values[:7]
    shift=5 if profile==4 else 4
    vectors=[[(int(v)<<shift)+(1<<(shift-1)) for v in row] for row in sp for _ in range(2)]
    co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n)
    pp=np.asarray(params,np.int64);ii=np.asarray(pulses,np.int64);steps=table('scale_table.inc')
    def render(ee):
        return advance(co,pp,ii,ee,steps,pre,bright,0,n,np.zeros(10,np.int64),0,0,np.zeros(256,np.int64))[0]
    return render


class SpeechRateAllocationTests(unittest.TestCase):
    def test_all_stored_bits_match_independent_serialization(self):
        for profile in (4,6):
            for n in (1,20,319,320,321,960):
                values=fields(profile,n);sp=values[2]
                if len(sp)>1:
                    sp[1]=sp[0].copy()
                for active in (0,1,len(sp)*8):
                    extras=np.full((len(sp)*8,2),(-1,0),np.int64)
                    for i in range(active):extras[i]=(i%40,-8 if i&1 else 7)
                    for force in (False,True):
                        blob,meta=compact.pack(*values[:7],extras=extras,force_extras=force)
                        cost=bit_accounting(sp,profile,extras,force_extras=force)
                        self.assertEqual(cost['file_bytes'],len(blob))
                        self.assertEqual(cost['payload_bits'],meta['payload_bits'])
                        self.assertEqual(cost['padding_bits'],(-meta['payload_bits'])%8)
                        self.assertEqual(cost['extra_marker_bits'],len(sp)*8 if force or active else 0)
                        self.assertEqual(cost['extra_value_bits'],10*active)
                        self.assertEqual(sum(spectrum_bits(v,None if i==0 else sp[i-1],profile) for i,v in enumerate(sp)),cost['spectrum_bits'])

    def test_preserved_amplitude_control_and_zero_extras_marker_transition(self):
        for profile in (4,6):
            values=fields(profile,321);sp=values[2];extras=np.full((16,2),(-1,0),np.int64)
            extras[0]=(3,1);extras[1]=(7,7);extras[15]=(39,-8)
            cost=bit_accounting(sp,profile,extras)
            trimmed,capacity,size,removed=fit_capacity(cost['spectrum_bits'],2,profile,extras,cost['file_bytes']-1,0,321)
            self.assertEqual(trimmed[15].tolist(),[-1,0])  # Unplayed stored tail precedes small amplitude.
            self.assertGreaterEqual(removed,1)
            self.assertEqual(size,len(compact.pack(*values[:7],extras=trimmed)[0]))
            self.assertEqual(capacity,extra_capacity(cost['spectrum_bits'],2,profile,cost['file_bytes']-1))
            base=bit_accounting(sp,profile)
            self.assertEqual(base['extra_marker_bits'],0)
            self.assertGreater(cost['file_bytes'],base['file_bytes'])

    def test_exact_greedy_choices_refresh_full_integer_reconstruction(self):
        for profile in (4,6):
            values=fields(profile);sp=values[2];extras=np.full((24,2),(-1,0),np.int64)
            for i,position,amp in ((0,4,7),(1,3,-6),(4,22,4),(8,6,-3),(15,1,2)):
                extras[i]=(position,amp)
            def serialize(ee):return compact.pack(*values[:7],extras=ee)[0]
            render=snapshot_renderer(values)
            reference=compact.decode_model(serialize(extras)).astype(np.int64)
            np.testing.assert_array_equal(render(extras),reference)
            def score(pcm):return int(np.sum((reference-pcm.astype(np.int64))**2))
            cap=bit_accounting(sp,profile,extras)['file_bytes']-3
            result=reclaim_extras(sp,profile,extras,cap,render=render,objective=score,serialize=serialize)
            current=extras.copy();previous=score(compact.decode_model(serialize(current)))
            self.assertGreaterEqual(result.removed,2)
            for step in result.trace:
                choices=[]
                for index in np.flatnonzero(current[:,1]):
                    candidate=current.copy();candidate[index]=(-1,0)
                    choices.append((score(compact.decode_model(serialize(candidate))),int(index)))
                best,index=min(choices)
                self.assertEqual(step['chunk'],index)
                self.assertEqual(step['before_score'],previous)
                self.assertEqual(step['after_score'],best)
                self.assertEqual(step['marginal_distortion'],best-previous)
                current[index]=(-1,0);previous=best
            self.assertTrue(result.feasible);self.assertLessEqual(len(result.stream),cap)
            np.testing.assert_array_equal(result.extras,current)
            np.testing.assert_array_equal(result.pcm,compact.decode_model(result.stream))
            for compact_only in (False,True):
                with BatchSession('batch',speech=True,speech_compact=True,compact_only=compact_only) as decoder:
                    np.testing.assert_array_equal(decoder.decode_one_s16(result.stream,values[0]),result.pcm)
            np.testing.assert_array_equal(extras[np.flatnonzero(extras[:,1]),1],[7,-6,4,-3,2])

    def test_coupled_removals_cannot_use_a_stale_additive_ranking(self):
        sp=fields(4,320)[2];extras=np.full((8,2),(-1,0),np.int64)
        extras[:3]=[(0,1),(0,2),(0,3)]
        # The states represent three coupled innovations. Removing0 is best
        # first; removing2 is then better than the originally second-ranked1.
        losses={(1,1,1):0,(0,1,1):1,(1,0,1):4,(1,1,0):9,
                (0,0,1):100,(0,1,0):16,(1,0,0):25,(0,0,0):200}
        def render(ee):
            state=tuple(int(v!=0) for v in ee[:3,1]);out=np.zeros(320,np.int64);out[0]=losses[state]
            return out
        def score(pcm):return int(pcm[0])
        one=extras.copy();one[1:3]=(-1,0)
        cap=bit_accounting(sp,4,one)['file_bytes']
        result=reclaim_extras(sp,4,extras,cap,render=render,objective=score)
        self.assertEqual([step['chunk'] for step in result.trace],[0,2])
        self.assertEqual(result.score,16)

    def test_oversized_seeds_complete_caps_limits_and_owned_callbacks(self):
        values=fields(6,641);sp=values[2];extras=np.full((24,2),(-1,0),np.int64)
        extras[0]=(3,7);extras[8]=(2,-3);extras[16]=(39,5)
        original=extras.copy()
        def serialize(ee):return compact.pack(*values[:7],extras=ee)[0]
        def render(ee):return compact.decode_model(serialize(ee))
        score=lambda pcm:int(np.sum(pcm.astype(np.int64)**2))
        seed=len(serialize(extras));base=bit_accounting(sp,6)['file_bytes']
        for percent in (100,95,90):
            cap=seed*percent//100
            result=reclaim_extras(sp,6,extras,cap,render=render,objective=score,serialize=serialize)
            self.assertEqual(result.file_bytes,len(result.stream))
            self.assertEqual(result.feasible,result.file_bytes<=cap)
        limited=reclaim_extras(sp,6,extras,seed-1,render=render,objective=score,max_evaluations=3)
        self.assertFalse(limited.feasible);self.assertEqual(limited.status,'evaluation_limit')
        self.assertEqual(limited.removed,0);self.assertEqual(limited.evaluations,1)
        nofit=reclaim_extras(sp,6,extras,base-1,render=render,objective=score,start=320)
        self.assertFalse(nofit.feasible);self.assertEqual(nofit.status,'no_removable_pulses')
        np.testing.assert_array_equal(nofit.extras[0],extras[0])
        np.testing.assert_array_equal(extras,original)

    def test_callback_and_bound_validation(self):
        sp=fields(4,320)[2];extras=np.full((8,2),(-1,0),np.int64);extras[0]=(0,1)
        render=lambda ee:np.zeros(320,np.int64);score=lambda pcm:0
        for kwargs in ({'max_bytes':True},{'max_bytes':21},{'max_bytes':65536},
                       {'max_bytes':40.5},{'start':1},{'max_evaluations':0},{'rate_lambda':float('nan')}):
            args=dict(max_bytes=100,render=render,objective=score);args.update(kwargs)
            with self.assertRaises(ValueError):reclaim_extras(sp,4,extras,**args)
        with self.assertRaises(ValueError):reclaim_extras(sp,4,extras,100,render=lambda ee:np.zeros(321,np.int64),objective=score)
        with self.assertRaises(ValueError):reclaim_extras(sp,4,extras,100,render=render,objective=lambda pcm:float('inf'))
        with self.assertRaises(AssertionError):reclaim_extras(sp,4,extras,100,render=render,objective=score,serialize=lambda ee:b'bad')
        self.assertEqual(distortion_rate(12,30,2),492)

    def test_bounded_swaps_preserve_feasibility_and_confirm_exact_improvement(self):
        for profile in (4,6):
            values=fields(profile)
            values[2]=[[2+3*i for i in range(10)] if profile==4 else [3+6*i for i in range(10)] for _ in values[2]]
            values[3]=[(18,60,8)]*len(values[3]);values[5]=values[6]=0
            sp=values[2];extras=np.full((24,2),(-1,0),np.int64)
            for i,position,amp in ((0,4,7),(1,3,-6),(4,22,4),(8,6,-3),(15,1,2)):
                extras[i]=(position,amp)
            def serialize(ee):return compact.pack(*values[:7],extras=ee)[0]
            render=snapshot_renderer(values);cost=bit_accounting(sp,profile,extras);cap=cost['file_bytes']-3
            control,_,_,_=fit_capacity(cost['spectrum_bits'],len(sp),profile,extras,cap,0,values[0])
            retained=np.flatnonzero(control[:,1]);removed=np.flatnonzero((extras[:,1]!=0)&(control[:,1]==0))
            baseline_pcm=compact.decode_model(serialize(control));reference=None
            for incoming in removed:
                for outgoing in retained:
                    target=control.copy();target[outgoing]=(-1,0);target[incoming]=extras[incoming]
                    candidate=compact.decode_model(serialize(target))
                    if not np.array_equal(candidate,baseline_pcm):reference=candidate.astype(np.int64);break
                if reference is not None:break
            self.assertIsNotNone(reference)
            def score(pcm):return int(np.sum((reference-pcm.astype(np.int64))**2))
            result=improve_extras(sp,profile,extras,cap,render=render,objective=score,serialize=serialize,
                stop=values[0],max_evaluations=100,candidate_batch=32)
            self.assertTrue(result.feasible);self.assertEqual(result.score,0)
            self.assertGreater(result.accepted_swaps,0)
            self.assertEqual(result.evaluations,1+result.candidate_evaluations+result.confirmation_evaluations)
            self.assertEqual(result.accepted_swaps,result.confirmation_evaluations)
            self.assertEqual(result.file_bytes,len(serialize(control)))
            self.assertLessEqual(len(result.stream),cap)
            self.assertEqual(bit_accounting(sp,profile,result.extras),bit_accounting(sp,profile,control))
            for step in result.trace:self.assertLess(step['after_score'],step['before_score'])
            np.testing.assert_array_equal(result.pcm,compact.decode_model(result.stream))
            for compact_only in (False,True):
                with BatchSession('batch',speech=True,speech_compact=True,compact_only=compact_only) as decoder:
                    np.testing.assert_array_equal(decoder.decode_one_s16(result.stream,values[0]),result.pcm)
            for limit in (1,2,3,6):
                bounded=improve_extras(sp,profile,extras,cap,render=render,objective=score,serialize=serialize,
                    stop=values[0],max_evaluations=limit,candidate_batch=2)
                self.assertTrue(bounded.feasible);self.assertLessEqual(bounded.evaluations,limit)
                self.assertLessEqual(bounded.score,score(render(control)))
                self.assertEqual(bounded.file_bytes,result.file_bytes)

    def test_swap_gate_no_fit_prefix_and_unstable_confirmation(self):
        values=fields(6,641);sp=values[2];extras=np.full((24,2),(-1,0),np.int64)
        extras[0]=(3,7);extras[8]=(1,1);extras[9]=(2,2);extras[10]=(3,3)
        cost=bit_accounting(sp,6,extras);cap=cost['file_bytes']-1
        control,_,_,_=fit_capacity(cost['spectrum_bits'],len(sp),6,extras,cap,320,641)
        missing=np.flatnonzero((extras[:,1]!=0)&(control[:,1]==0))[0]
        def serialize(ee):return compact.pack(*values[:7],extras=ee)[0]
        def render(ee):
            pcm=np.zeros(641,np.int64);pcm[0]=0 if ee[missing,1] else 10
            return pcm
        score=lambda pcm:int(pcm[0])
        denied=improve_extras(sp,6,extras,cap,render=render,objective=score,serialize=serialize,stop=641,start=320,
            max_evaluations=30,admissible=lambda pcm:False)
        self.assertTrue(denied.feasible);self.assertEqual(denied.accepted_swaps,0)
        self.assertFalse(denied.seed_admissible);self.assertFalse(denied.quality_admissible)
        self.assertGreater(denied.rejected_by_admissible,0)
        np.testing.assert_array_equal(denied.extras,control)
        allowed=improve_extras(sp,6,extras,cap,render=render,objective=score,serialize=serialize,stop=641,start=320)
        np.testing.assert_array_equal(allowed.extras[0],extras[0])
        nofit=improve_extras(sp,6,extras,22,render=render,objective=score,serialize=serialize,stop=641)
        self.assertFalse(nofit.feasible);self.assertEqual(nofit.status,'no_fit')
        publications=[]
        def unstable_serialize(ee):publications.append(1);return serialize(ee)
        def unstable_render(ee):
            pcm=render(ee)
            if len(publications)>1:pcm[0]+=1
            return pcm
        with self.assertRaises(AssertionError):
            improve_extras(sp,6,extras,cap,render=unstable_render,objective=score,serialize=unstable_serialize,
                stop=641,start=320,max_evaluations=30)


if __name__=='__main__':unittest.main()

"""Pure/mocked study contracts; no media, native loading, fitting or real pools."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'))
from speech_chain_rate import ChainRatePoint,allocate_exact_sse
import chain_study_policy as policy
import chain_study_runtime as runtime
import run_chain_study as runner


def row(identifier,size,score):return dict(id=identifier,stream=bytes([identifier+1])*size,sse=score)
def pool_rows(rows):return [dict(id=r['id'],blob=r['stream'],sse=r['sse']) for r in rows]


def temporary():
    folder=(ROOT/'build/chain-rate-study/contract-tmp').resolve()
    if not folder.is_relative_to((ROOT/'build').resolve()):raise AssertionError('Invalid test scratch root')
    folder.mkdir(parents=True,exist_ok=True)
    return tempfile.TemporaryDirectory(dir=folder)


class FixedPoolStudyTests(unittest.TestCase):
    def test_restriction_keeps_only_frontier_and_protected_rows_with_stable_ids(self):
        rows=[row(0,100,100),row(1,80,200),row(2,90,150),row(3,110,50),row(4,120,70),row(5,105,130)]
        frontier=policy.V1.local_frontier(pool_rows(rows),200)
        cut=policy.restrict_pool(pool_rows(rows),[p['id'] for p in frontier],rows[0]['stream'],5,4,200)
        self.assertEqual([r['id'] for r in cut['rows']],[0,1,2,3,4,5])
        without=policy.restrict_pool(pool_rows(rows),[p['id'] for p in frontier],rows[0]['stream'],None,None,200)
        self.assertEqual([r['id'] for r in without['rows']],[0,1,2,3])
        with self.assertRaisesRegex(ValueError,'frontier'):
            policy.restrict_pool(pool_rows(rows),[1,3],rows[0]['stream'],None,None,200)

    def test_exact_byte_dedup_preserves_protected_aliases_and_rejects_unverified_sse(self):
        rows=[row(0,30,10),dict(id=1,stream=bytes([1])*30,sse=10),row(2,22,20)]
        frontier=policy.V1.local_frontier(pool_rows(rows),100)
        cut=policy.restrict_pool(pool_rows(rows),[r['id'] for r in frontier],rows[0]['stream'],1,1,100)
        self.assertEqual(cut['baseline_id'],0)
        self.assertEqual(cut['selected_id'],0)
        self.assertEqual(cut['raw_id'],0)
        self.assertEqual([r['id'] for r in cut['rows']],[0,2])
        rows[1]['sse']=None
        with self.assertRaises(ValueError):policy.restrict_pool(pool_rows(rows),[r['id'] for r in frontier],rows[0]['stream'],1,1,100)

    def test_one_dp_call_at_B_answers_all_caps_without_widening_scope(self):
        pools=[[row(0,100,100),row(1,80,200),row(2,110,50)],
               [row(0,100,100),row(1,80,160),row(2,90,110),row(3,110,80)]]
        calls=[]
        def allocate(*args,**kwargs):calls.append((args,kwargs));return allocate_exact_sse(*args,**kwargs)
        result=policy.allocate_views(pools,(0,0),((0,0),),200,allocate)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][0][1],200)
        self.assertEqual(calls[0][1]['max_states'],250000)
        self.assertEqual(calls[0][1]['max_transitions'],10000000)
        self.assertEqual(result['winners'][100],ChainRatePoint((2,2),200,160))
        self.assertLessEqual(len(result['points']),3)
        self.assertEqual(result['caps'],{'100':200,'95':190,'90':180})

    def test_resource_limited_retained_complete_winners_are_explicitly_nonexact(self):
        pools=[[row(0,100,100),row(1,90,110)]]
        def limited(*args,**kwargs):
            kwargs['max_states']=1
            return allocate_exact_sse(*args,**kwargs)
        result=policy.allocate_views(pools,(0,),((0,),),100,limited)
        self.assertFalse(result['result'].exact)
        self.assertIsNone(result['result'].best)
        self.assertTrue(result['points'])
        self.assertTrue(all('retained-nonexact' in label for point in result['points'] for label in point['labels']))

    def test_exception_exposes_owned_retained_state_without_a_partial_prefix(self):
        class Stop(Exception):pass
        state={}
        def stopped(*args,**kwargs):
            kwargs['on_candidate'](ChainRatePoint((0,),100,10))
            kwargs['on_candidate'](ChainRatePoint((1,),90,11))
            raise Stop
        with self.assertRaises(Stop):policy.allocate_views([[row(0,100,10),row(1,90,11)]],(0,),(),100,stopped,state)
        self.assertEqual(state['callback_completed'],2)
        self.assertEqual(state['best']['100']['ids'],[0])
        self.assertEqual(state['best']['95']['ids'],[1])
        self.assertEqual(state['best']['90']['ids'],[1])
        def partial(*args,**kwargs):kwargs['on_candidate'](ChainRatePoint((),0,0))
        with self.assertRaisesRegex(AssertionError,'partial prefix'):
            policy.allocate_views([[row(0,100,10)]],(0,),(),100,partial)

    def test_single_reset_identity_is_direct_cap_selection_not_extreme_recipe_identity(self):
        result=policy.allocate_views([[row(0,100,10),row(1,95,11),row(2,90,12)]],(0,),((0,),),100,allocate_exact_sse)
        self.assertEqual([result['winners'][p].ids for p in policy.PERCENTS],[(0,),(1,),(2,)])
        self.assertEqual(len(result['points']),3)

    def test_primary_success_excludes_old_tuples_and_nonexact_results(self):
        old=dict(score=1.,stream_bytes=100);new=dict(score=.9,stream_bytes=100)
        self.assertTrue(policy.new_outcome(old,new,True,True)['exact_primary_success'])
        self.assertFalse(policy.new_outcome(old,new,False,True)['exact_primary_success'])
        partial=policy.new_outcome(old,new,True,False)
        self.assertFalse(partial['exact_primary_success']);self.assertTrue(partial['nonexact_retained_success'])
        self.assertFalse(policy.new_outcome(old,dict(score=1.1,stream_bytes=90),True,True)['new_admitted_win'])

    def test_context_frontier_secondary_does_not_credit_a_weaker_arm_control(self):
        originals=[dict(score=.8,stream_bytes=100,automatic_quality_eligible=True),
                   dict(score=1.,stream_bytes=90,automatic_quality_eligible=True)]
        already_known=dict(score=.8,stream_bytes=100,automatic_quality_eligible=True)
        self.assertFalse(policy.extends_context_frontier(originals,already_known,False))
        dominated=dict(score=.9,stream_bytes=100,automatic_quality_eligible=True)
        self.assertFalse(policy.extends_context_frontier(originals,dominated,True))
        # This is a new rate/score tradeoff even though the 100-byte minimum-score original is lower.
        tradeoff=dict(score=.9,stream_bytes=95,automatic_quality_eligible=True)
        self.assertTrue(policy.extends_context_frontier(originals,tradeoff,True))
        tradeoff['automatic_quality_eligible']=False
        self.assertFalse(policy.extends_context_frontier(originals,tradeoff,True))

    def test_saved_secondary_uses_all_added_points_without_new_metric_or_dp_calls(self):
        job,C,value,pools=self.job_fixture()
        def whole(identifier,size,score):
            return dict(deepcopy(job['originals'][0]['old_value']),id=identifier,stream_bytes=size,score=score)
        original=whole(0,100,1.)
        known=whole(1,90,.9)
        added=whole(2,80,.95)
        source_pools=[[row(0,100,100),row(1,90,90),row(2,80,95)]]
        jobs=[];results=[]
        for identifier,originals,values in ((0,1,[original,known,added]),(1,2,[original,known])):
            jobs.append(dict(id=identifier,baseline_id=0,arm=policy.ARMS[identifier],profile=4,baseline_bytes=100,
                caps={'100':100,'95':95,'90':90},pools=[dict(rows=source_pools[0])]))
            results.append(dict(id=identifier,original_recipes=originals,exact=True,decisions=[
                dict(percent=p,new=dict(selected_id=1),absent_from_original_five=identifier==0) for p in policy.PERCENTS]))
        def choose(rows,cap):
            fits=[r for r in rows if r['automatic_quality_eligible'] and r['stream_bytes']<=cap]
            selected=min(fits,key=lambda r:(r['score'],r['stream_bytes'],r['id'])) if fits else None
            return dict(selected_id=None if selected is None else selected['id'])
        fake=SimpleNamespace(chain=SimpleNamespace(choose_budget=choose))
        with temporary() as folder:
            out=Path(folder)
            for item,values in zip(results,([original,known,added],[original,known])):
                runtime.save(out/'arms'/('job-%03d'%item['id'])/'result-private.json',dict(public=item,
                    complete_whole_rows=values,tuples=[dict(ids=[i]) for i in range(len(values))]))
            secondary=runner.context_secondary(dict(jobs=jobs),results,fake,SimpleNamespace(stream=lambda meta:meta),out)
        self.assertEqual(secondary['new_dp_decode_metric_native_calls'],0)
        self.assertEqual(sum(r['known_other_arm_point'] for r in secondary['rows']),3)
        self.assertEqual(secondary['exact_distinct_context_cap_tuples'],3)
        extensions=[r for r in secondary['frontier_rows'] if r['exact_context_frontier_extension']]
        self.assertEqual([r['chain_id'] for r in extensions],[2,2,2])

    def test_origin_guard_checks_exact_module_path_and_source_bytes(self):
        path=ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/speech_chain_rate.py'
        C=SimpleNamespace(chain_rate=SimpleNamespace(__file__=str(path)))
        inventory={runtime.PREFIX+'tools/speech_chain_rate.py':runtime.sha(path.read_bytes())}
        runtime.check_allocator_origin(C,ROOT,inventory)
        with self.assertRaisesRegex(ValueError,'origin'):
            runtime.check_allocator_origin(SimpleNamespace(chain_rate=SimpleNamespace(__file__=str(path.with_name('other.py')))),ROOT,inventory)
        inventory[next(iter(inventory))]='0'*64
        with self.assertRaisesRegex(ValueError,'origin'):runtime.check_allocator_origin(C,ROOT,inventory)

    def test_forbidden_guard_catches_search_pack_build_and_process_launch(self):
        modules={}
        def module(name):
            if name not in modules:
                modules[name]=SimpleNamespace(**{attr:(lambda:None) for attr in
                    ('encode','search','pack','repack','refine_candidates','select_candidates',
                     'refine','_expand','_rate_children','adapt_excitation','coefficient_patch','assemble','build_library')})
            return modules[name]
        with temporary() as folder:
            out=Path(folder);attempt=dict(forbidden_work_attempts=0)
            with patch.object(runtime.importlib,'import_module',side_effect=module):
                with runtime.forbid_search_and_build(None,attempt,out):
                    for name,attr in (('speech_compact','pack'),('refine_speech_lpc','refine'),('batch_decoder','build_library')):
                        with self.assertRaises(AssertionError):getattr(modules[name],attr)()
                    with self.assertRaises(AssertionError):runtime.subprocess.run(['forbidden'])
            self.assertEqual(attempt['forbidden_work_attempts'],4)

    def test_validation_rejects_changed_scope_caps_or_missing_reset(self):
        jobs=[]
        for baseline in range(12):
            for arm in policy.ARMS:
                # Eight extra reset slots, repeated across five arms =100 total.
                count=5 if baseline<2 else 1
                jobs.append(dict(id=len(jobs),baseline_id=baseline,arm=arm,profile=4 if baseline%2==0 else 6,
                    baseline_bytes=200,caps={'100':200,'95':190,'90':180},baseline=[{}]*count,
                    pools=[dict(index=i) for i in range(count)],originals=[dict(labels=['baseline'])]))
        policy.validate_jobs(jobs)
        jobs[0]['originals'][0]['labels'].extend(['selected','raw'])
        policy.validate_jobs(jobs)
        jobs[0]['caps']['95']=191
        with self.assertRaisesRegex(ValueError,'caps'):policy.validate_jobs(jobs)

    def job_fixture(self):
        flags=dict(old_pcm_pwm_floors_passed=True,clipped_sample_floor_passed=True,
            pcm_period_coverage_floor_passed=True,pwm_period_coverage_floor_passed=True,joint_objective_nonregression=True)
        value=dict(metrics=dict(pcm16=dict(error_energy=100),pwm8=dict(error_energy=100)),
            voice=dict(within_tolerance_frames=1),pwm_voice=dict(within_tolerance_frames=1),
            noise={},pwm_noise={},domain_scores=[1.,1.],score=1.,clipped_samples=0,
            voice_components={},pwm_voice_components={})
        old=dict(id=0,labels=['baseline'],stream_bytes=100,**value,**flags,automatic_quality_eligible=True)
        job=dict(id=0,baseline_id=0,source_ordinal=0,arm='T-full-0',profile=4,nonspeech=True,mode='preserve',
            base=dict(profile=4,samples=1,segments=[dict(samples=1)]),baseline_bytes=100,
            caps={'100':100,'95':95,'90':90},pools=[dict(baseline_id=0)],
            originals=[dict(ids=[0],labels=['baseline'],old_value=old)])
        C=SimpleNamespace(chain_rate=SimpleNamespace(allocate_exact_sse=allocate_exact_sse),
            chain=SimpleNamespace(_admission=lambda *args:flags.copy()))
        return job,C,value,[[row(0,100,100),row(1,90,110)]]

    def test_allocation_persistence_failure_keeps_active_callback_winners(self):
        job,C,value,pools=self.job_fixture();evaluator=SimpleNamespace(measure=lambda *args:value)
        attempt=dict(dp_calls_started=0,dp_calls_returned=0,active_dp=None,arm_records=[])
        real=runner.save
        def failed(path,value):
            if path.name=='allocation-private.json':raise OSError('synthetic persistence fault')
            return real(path,value)
        with temporary() as folder,patch.object(runner,'save',side_effect=failed):
            with self.assertRaises(OSError):runner.run_job(job,C,evaluator,None,pools,attempt,Path(folder))
        self.assertEqual(attempt['dp_calls_returned'],1)
        self.assertTrue(attempt['active_dp']['returned'])
        self.assertGreater(attempt['active_dp']['retained']['callback_completed'],0)
        self.assertTrue(attempt['active_dp']['retained']['best'])

    def test_completed_full_whole_rows_survive_a_later_measurement_failure(self):
        job,C,value,pools=self.job_fixture();events=[]
        def measure(*args):
            events.append(1)
            if len(events)==3:raise RuntimeError('synthetic later row failure')
            return value
        evaluator=SimpleNamespace(measure=measure,context='synthetic',counts=Counter(),provenance=[])
        attempt=dict(dp_calls_started=0,dp_calls_returned=0,active_dp=None,arm_records=[])
        with temporary() as folder,patch.object(runner,'check_integer_sse',return_value=100):
            with self.assertRaises(RuntimeError):runner.run_job(job,C,evaluator,None,pools,attempt,Path(folder))
            saved=json.loads((Path(folder)/'arms/job-000/whole-progress-private.json').read_bytes())
            self.assertEqual(len(saved['complete_whole_rows']),1)
            self.assertEqual(saved['complete_whole_rows'][0]['voice']['within_tolerance_frames'],1)
            self.assertEqual(saved['complete_whole_rows'][0]['pwm_voice']['within_tolerance_frames'],1)
            self.assertTrue(saved['complete_whole_rows'][0]['automatic_quality_eligible'])


if __name__=='__main__':unittest.main()

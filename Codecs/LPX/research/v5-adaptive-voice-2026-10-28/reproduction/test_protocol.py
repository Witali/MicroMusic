"""Contracts for bounded seed reuse, honest coverage and complete-chain caps."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_corpus as study


def entry(role,sizes,score=1.,eligible=True):
    return dict(role=role,stream_bytes=sum(sizes),score=score,automatic_quality_eligible=eligible,
                segments=[dict(stream_sha256=str(n)) for n in sizes])


def row(*,score=1.,pcm_periods=10,pwm_periods=10,clipped=0,metric_ok=True):
    return dict(score=score,voice=dict(within_tolerance_frames=pcm_periods),
        pwm_voice=dict(within_tolerance_frames=pwm_periods),clipped_samples=clipped,
        metrics=dict(ok=metric_ok))


class AdaptiveProtocolTests(unittest.TestCase):
    def owned_temp(self):
        owned = Path(__file__).resolve().parents[5]/'build/adaptive-protocol-tests'
        owned.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=owned)

    def test_single_stream_cap_and_whole_long_cap_are_separate(self):
        for whole,expected in ((22,22),(65534,65534),(65535,65535),(65536,65535),(299058,65535)):
            self.assertEqual(study.local_cap(whole),expected)
        for bad in (True,21,22.,None):
            with self.assertRaises(ValueError):
                study.local_cap(bad)
        whole = study.choose_budget([entry('control',[60000]*5)],300000,100)
        self.assertEqual(whole['cap'],300000)
        self.assertEqual(whole['selected'],'control')

    def test_transient_windows_atomic_save_does_not_repeat_operator_work(self):
        with self.owned_temp() as directory:
            target = Path(directory)/'attempt-private.json'
            failure = PermissionError('synthetic sharing failure')
            failure.winerror = 32
            original = study._save_once
            calls = []
            def flaky(path, value):
                calls.append(1)
                if len(calls) == 1:
                    raise failure
                return original(path, value)
            with patch.object(study,'_save_once',side_effect=flaky), patch.object(study.time,'sleep'):
                study.save(target,dict(status='complete',operator_calls=1))
            self.assertEqual(len(calls),2)
            self.assertEqual(json.loads(target.read_text()),dict(status='complete',operator_calls=1))

    def test_persistent_atomic_permission_failure_is_bounded(self):
        failure = PermissionError('synthetic persistent failure')
        failure.winerror = 5
        with patch.object(study,'_save_once',side_effect=failure) as writes, patch.object(study.time,'sleep'), self.assertRaises(PermissionError):
            study.save(Path('unused-private.json'),{})
        self.assertEqual(writes.call_count,6)
        with patch.object(study,'_save_once',side_effect=ValueError('alias rejected')) as writes, self.assertRaises(ValueError):
            study.save(Path('unused-private.json'),{})
        self.assertEqual(writes.call_count,1)

    def test_predeclared_representatives_use_lengths_ordinals_and_exclusion(self):
        records = [dict(samples=n) for n in (30,10,20,20,50,40)]
        groups = [[i] for i in range(len(records))]
        self.assertEqual(study.representative_ordinals(records,groups),[1,0,4])
        self.assertEqual(study.representative_ordinals(records,groups,[0,4]),[1,3,5])
        with self.assertRaises(ValueError):
            study.representative_ordinals(records,groups,[0,1,2,3])

    def test_oversized_local_chain_and_bad_whole_quality_cannot_displace_rollback(self):
        rows = [entry('control',[50,50],2),entry('concat-selected',[60,50],.1),
                entry('concat-raw',[45,45],.05,False),None]
        self.assertEqual(study.choose_budget(rows,100,100)['selected'],'control')
        for percent in (95,90):
            result = study.choose_budget(rows,100,percent)
            self.assertIsNone(result['selected'])
            self.assertEqual(result['raw_tradeoff'],'concat-raw')
        no_fit = study.choose_budget([entry('control',[22])],22,90)
        self.assertTrue(no_fit['no_fit'])
        self.assertIsNone(no_fit['selected'])
        self.assertIsNone(no_fit['raw_tradeoff'])

    def test_duplicate_roles_are_one_measured_signal_and_control_wins_tie(self):
        rows = [entry(role,[50,50]) for role in ('concat-raw','concat-selected','control')]
        result = study.choose_budget(rows,100,100)
        self.assertEqual(result['selected'],'control')
        self.assertEqual(result['distinct_fitting_chain_count'],1)
        self.assertEqual(result['fitting_chain_count'],3)

    def test_vanished_pitch_cannot_pass_via_a_better_objective(self):
        core = SimpleNamespace(no_regression=lambda a,b:a['ok'])
        baseline = row()
        vanished = row(score=0.,pcm_periods=0,pwm_periods=0)
        flags = study.admission(vanished,baseline,core)
        self.assertTrue(flags['joint_objective_nonregression'])
        self.assertFalse(flags['pcm_period_coverage_floor_passed'])
        self.assertFalse(flags['pwm_period_coverage_floor_passed'])
        # Source/control-unassessed coverage remains zero, not a claimed success.
        unknown = row(pcm_periods=0,pwm_periods=0)
        self.assertTrue(all(study.admission(unknown,unknown,core).values()))
        self.assertEqual(unknown['voice']['within_tolerance_frames'],0)

    def test_pwm_metric_clip_and_objective_floors_remain_separate(self):
        core = SimpleNamespace(no_regression=lambda a,b:a['ok'])
        baseline = row()
        bad = row(score=2.,clipped=1,metric_ok=False)
        flags = study.admission(bad,baseline,core)
        self.assertFalse(flags['old_pcm_pwm_floors_passed'])
        self.assertFalse(flags['clipped_sample_floor_passed'])
        self.assertFalse(flags['joint_objective_nonregression'])
        self.assertTrue(flags['pcm_period_coverage_floor_passed'])

    def test_worst_segment_uses_exact_rate_tie_and_keeps_final_tail(self):
        reference = np.array([1,1,1,1,0,0,0],np.int16)
        record = dict(segments=[dict(start=0,samples=2),dict(start=2,samples=2),dict(start=4,samples=3)])
        outputs = [np.zeros(2,np.int16),np.zeros(2,np.int16),np.zeros(3,np.int16)]
        core = SimpleNamespace(np=np,compact=SimpleNamespace(decode_model=lambda index:outputs[index]))
        edited,errors = study.worst_and_tail(reference,[0,1,2],record,core)
        self.assertEqual(edited,[0,2])
        self.assertEqual(errors,[2,2,0])
        outputs[2] = np.array([1,1,1],np.int16)
        reference[:] = 0
        edited,_ = study.worst_and_tail(reference,[0,1,2],record,core)
        self.assertEqual(edited,[2])

    def test_wrong_cached_module_or_alias_cannot_attest_frozen_root(self):
        root = Path(__file__).resolve().parents[5]
        tools = root/study.PREFIX/'tools'
        modules = {n:SimpleNamespace(__file__=str(tools/(n+'.py'))) for n in study.REQUIRED_MODULES}
        study.assert_origins(root,modules)
        for name in ('adaptive_speech_voice','cached_alias'):
            bad = dict(modules)
            bad[name] = SimpleNamespace(__file__=str(root/'another-checkout'/study.PREFIX/'tools/adaptive_speech_voice.py'))
            with self.assertRaises(ValueError):
                study.assert_origins(root,bad)

    def test_operator_attempt_journal_records_start_before_work_and_seed_fit_guard(self):
        with self.owned_temp() as directory:
            folder = Path(directory)
            path,_,attempt,prior = study.start_attempt(folder,'fixed-epoch')
            self.assertEqual(prior,[])
            def operation():
                saved = json.loads(path.read_text())
                self.assertEqual(saved['operator_events'][-1]['status'],'started')
                return 'done'
            core = SimpleNamespace(adaptive=SimpleNamespace(enhance=operation,refine_header=operation,refine=operation),
                                   speech_v4=SimpleNamespace(encode=lambda:'forbidden'))
            with study.operator_context(core,attempt,path):
                self.assertEqual(core.adaptive.enhance(),'done')
                self.assertEqual(core.adaptive.refine_header(),'done')
                with self.assertRaises(AssertionError):
                    core.speech_v4.encode()
            self.assertEqual([e['operator'] for e in attempt['operator_events']],['extras','header_filters'])
            self.assertTrue(all(e['status']=='complete' for e in attempt['operator_events']))
            self.assertEqual(attempt['new_seed_fit_attempts'],1)
            self.assertEqual(json.loads(path.read_text())['new_seed_fit_attempts'],1)

    def test_failed_operator_remains_started_and_incomplete_attempt_is_preserved(self):
        with self.owned_temp() as directory:
            path,_,attempt,_ = study.start_attempt(Path(directory),'epoch')
            def fail():
                raise RuntimeError('bounded synthetic failure')
            core = SimpleNamespace(adaptive=SimpleNamespace(enhance=fail,refine_header=fail,refine=fail),
                                   speech_v4=SimpleNamespace(encode=fail))
            with study.operator_context(core,attempt,path),self.assertRaises(RuntimeError):
                core.adaptive.enhance()
            self.assertEqual(json.loads(path.read_text())['operator_events'][0]['status'],'started')
            _,_,_,prior = study.start_attempt(Path(directory),'epoch')
            self.assertEqual(len(prior),1)
            self.assertEqual(prior[0]['status'],'running')
            with self.assertRaises(ValueError):
                study.start_attempt(Path(directory),'different-epoch')

    def test_complete_cache_binds_attempt_status_as_well_as_streams(self):
        with self.owned_temp() as directory:
            folder = Path(directory)
            report = folder/'record-private.json'
            stream = folder/'segment/pool.l4hy'
            attempt = folder/'attempts/attempt-000-private.json'
            study.immutable_bytes(stream,b'synthetic stream')
            study.save(report,dict(ok=True))
            study.save(attempt,dict(status='complete'))
            marker = dict(identity='epoch',report_sha256=study.sha(report.read_bytes()),
                artifacts_sha256={p.relative_to(folder).as_posix():study.sha(p.read_bytes()) for p in (stream,attempt)})
            study.save(folder/'complete-private.json',marker)
            self.assertEqual(study.V1.inspect_cache(folder,'epoch'),dict(ok=True))
            study.save(attempt,dict(status='running'))
            with self.assertRaises(ValueError):
                study.V1.inspect_cache(folder,'epoch')

    def test_pool_validation_rejects_false_missing_pitch_admission(self):
        measured = [dict(**row(),domain_scores=[1.,1.],noise={},pwm_noise={}),
                    dict(**row(score=.5,pcm_periods=0,pwm_periods=0),domain_scores=[.5,.5],noise={},pwm_noise={})]
        claimed = []
        for index,value in enumerate(measured):
            claimed.append(dict(**copy.deepcopy(value),id=index,file_bytes=1,
                fits_complete_cap=True,full_flash_bytes=None,fits_flash_cap=True,admissible=True))
        report = dict(candidates=claimed,profile=4,complete_byte_cap=22,selected_id=1,raw_id=1)
        core = SimpleNamespace(no_regression=lambda a,b:True)
        with patch.object(study,'evaluators',return_value=None), patch.object(study.V1,'verify_chain',return_value=None), patch.object(study,'measure',side_effect=measured):
            with self.assertRaises(ValueError):
                study.validate_pool([b'a',b'b'],report,np.zeros(640,np.int16),True,core,None,None,{})

    def test_actual_pool_rows_selected_raw_and_frontier_are_independently_rederived(self):
        actual = [dict(**row(),domain_scores=[1.,1.],noise={},pwm_noise={}),
                  dict(**row(score=.5),domain_scores=[.5,.5],noise={},pwm_noise={}),
                  dict(**row(score=.25,pcm_periods=0,pwm_periods=0),domain_scores=[.25,.25],noise={},pwm_noise={})]
        claims = [dict(**copy.deepcopy(value),id=i,file_bytes=i+1,fits_complete_cap=True,
            full_flash_bytes=None,fits_flash_cap=True,admissible=i != 2) for i,value in enumerate(actual)]
        description = dict(voice={},noise={},domains=['native_pcm16','fixed_pwm8'],aggregation='mean of voice + noise')
        report = dict(candidates=claims,profile=4,complete_byte_cap=22,selected_id=1,raw_id=2,
                      frontier=[0,1],objective=description)
        evaluator = (None,SimpleNamespace(describe=lambda:{}),SimpleNamespace(describe=lambda:{}))
        core = SimpleNamespace(no_regression=lambda a,b:True)
        def run(value):
            with patch.object(study,'evaluators',return_value=evaluator),patch.object(study.V1,'verify_chain',return_value=None),patch.object(study,'measure',side_effect=copy.deepcopy(actual)):
                return study.validate_pool([b'a',b'bb',b'ccc'],value,np.zeros(640,np.int16),True,core,None,None,{})
        self.assertEqual(len(run(report)),3)
        bad = copy.deepcopy(report)
        bad['selected_id'] = 2
        with self.assertRaises(ValueError):
            run(bad)
        bad = copy.deepcopy(report)
        bad['candidates'][1]['domain_scores'][1] += .001
        with self.assertRaises(AssertionError):
            run(bad)
        bad = copy.deepcopy(report)
        bad['frontier'] = [2]
        with self.assertRaises(AssertionError):
            run(bad)


if __name__ == '__main__':
    unittest.main()

"""Injected later failures preserve completed callbacks and whole admissions."""
from collections import Counter
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from extra_runtime import HISTORICAL_RESEARCH_COMMIT,Inputs,SOURCE_COMMIT,VALUE_KEYS,historical_preflight,sha
from run_existing import local_call,retaining_sink,run_record


class LaterFailure(RuntimeError):pass


def fixture(root):
    blob=b'original'
    base=dict(id=0,profile=4,nonspeech=False,samples=8,stream_bytes=len(blob),
        segments=[dict(path=str(root/'input.l4hy'),index=0,start=0,samples=8,profile=4,
            file_bytes=len(blob),stream_sha256=sha(blob))],
        existing_extra_plan=[dict(eligible_group_indices=[0],initial_active_extras=1,max_trial_evaluations=49)])
    attempt=dict(records=[],helper_calls=[],synthetic_calls=[])
    return blob,base,attempt


class FailureRetention(unittest.TestCase):
    def test_historical_six_calls_remain_bound_separately_from_current_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);baseline=root/'old-metadata/binding-private.json'
            baseline.parent.mkdir()
            def write(path,value):path.write_text(json.dumps(value))
            write(baseline,dict(preparation_commit=HISTORICAL_RESEARCH_COMMIT,original_binding_sha256='original',
                preparation_cost={'cpu_seconds':3,'wall_seconds':4}))
            write(baseline.parent/'complete-private.json',dict(status='complete',binding_sha256=sha(baseline.read_bytes())))
            write(root/'summary.json',dict(status='PASS',preflight_only=True,synthetic_helper_calls=6,
                corpus_helper_calls=0,arm_records=0,actual_cap_views=0,total_cost={'cpu_seconds':9,'wall_seconds':10}))
            write(root/'binding-private.json',dict(source_commit=SOURCE_COMMIT,production_sources={},runtime={},native_bridge={},
                research_sources={'old_recipe.py':'old bound bytes'},baselines_path=str(baseline.resolve()),
                input_files_sha256={str(baseline.resolve()):sha(baseline.read_bytes())}))
            write(root/'attempt-private.json',dict(status='complete',helper_calls=[],
                synthetic_calls=[{'status':'complete'} for _ in range(6)],forbidden_fit_or_build_attempts=0))
            write(root/'synthetic-private.json',dict(status='PASS',helper_calls=6))
            proof=historical_preflight(root,Inputs(),{},{},{},'original')
            self.assertEqual(proof['synthetic_helper_calls'],6)
            self.assertEqual(proof['historical_research_sources'],{'old_recipe.py':'old bound bytes'})
            self.assertEqual(proof['preflight_cost']['cpu_seconds'],9)
            with self.assertRaises(ValueError):historical_preflight(root,Inputs(),{'changed':'current'},{},{},'original')

    def test_every_callback_is_durable_before_the_producer_continues_then_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);blob,base,attempt=fixture(root);seen=[]
            def helper(reference,original,decoder,**settings):
                for stream,score in ((original,10),(b'changed',4)):
                    settings['candidate_sink'](stream,score)
                    journal=json.loads((root/'attempt-private.json').read_bytes())
                    captured=journal['helper_calls'][0]['captured_streams'][-1]
                    self.assertEqual(Path(captured['path']).read_bytes(),stream)
                    self.assertEqual(captured['reported_full_sse'],score)
                    self.assertEqual(captured['id'],len(seen));seen.append(captured)
                raise LaterFailure('Later native or metric work failed')
            C=SimpleNamespace(extras=SimpleNamespace(refine_existing_extras=helper))
            with self.assertRaises(LaterFailure):
                local_call(base,0,blob,None,C,None,None,root/'local',attempt,root,'corpus',True,Counter())
            journal=json.loads((root/'attempt-private.json').read_bytes());event=journal['helper_calls'][0]
            self.assertEqual(event['status'],'helper-failed');self.assertEqual(len(event['captured_streams']),2)
            self.assertEqual(event['callback_persistence_cost']['callback_calls'],2)
            self.assertTrue(event['callback_persistence_cost']['included_in_actual_helper_time'])
            self.assertIn('helper_cost',event)
            self.assertTrue(all(Path(meta['path']).read_bytes() in (blob,b'changed') for meta in seen))

    def test_callback_files_are_immutable_and_duplicate_publication_does_not_rewrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);blob,base,attempt=fixture(root);event={};attempt['helper_calls'].append(event)
            sink=retaining_sink(base,0,root/'local',attempt,root,event,[])
            sink(blob,10);meta=event['captured_streams'][0];path=Path(meta['path']);before=path.stat().st_mtime_ns
            with self.assertRaises(AssertionError):sink(blob,10)
            self.assertEqual(path.read_bytes(),blob);self.assertEqual(path.stat().st_mtime_ns,before)
            self.assertEqual(len(event['captured_streams']),1)

    def test_completed_whole_admission_survives_the_next_measurement_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);blob,base,attempt=fixture(root)
            value={key:0 for key in VALUE_KEYS};base['stored_expected_whole_value']=value
            job=dict(id=0,reset_indices=[0],causal_positions=True)
            folder=root/'records/job-00'
            class Evaluator:
                calls=0
                def measure(self,*args):
                    self.calls+=1
                    if self.calls==3:
                        receipt=json.loads((folder/'whole/chain-00/admission-private.json').read_bytes())
                        self_outer.assertEqual(receipt['whole_row']['score'],0)
                        self_outer.assertEqual(receipt['whole_row']['stream_bytes'],len(blob))
                        self_outer.assertEqual(Path(receipt['whole_chain']['segments'][0]['path']).read_bytes(),blob)
                        self_outer.assertEqual(json.loads((folder/'whole-progress-private.json').read_bytes())['whole_rows'][0],receipt['whole_row'])
                        raise LaterFailure('The next whole metric failed')
                    return value.copy()
            self_outer=self
            C=SimpleNamespace(chain=SimpleNamespace(_admission=lambda actual,anchor:{'gate':True}))
            inputs=SimpleNamespace(stream=lambda meta:blob)
            roles=[('baseline',(blob,)),('coverage-slot-1',(b'changed',))]
            with patch('run_existing.local_call',return_value=({},{})),patch('run_existing.whole_roles',return_value=roles):
                with self.assertRaises(LaterFailure):
                    run_record(job,base,[0]*8,C,None,Evaluator(),inputs,root,attempt,Counter(),[])
            journal=json.loads((root/'attempt-private.json').read_bytes())
            self.assertEqual(journal['records'][0]['completed_whole_ids'],[0])
            self.assertEqual(len(json.loads((folder/'whole-progress-private.json').read_bytes())['whole_chains']),1)
            self.assertFalse((folder/'result-private.json').exists())


if __name__=='__main__':unittest.main()

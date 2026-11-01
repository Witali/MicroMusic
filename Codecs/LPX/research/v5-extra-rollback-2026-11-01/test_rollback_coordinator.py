"""Injected policy/failure wiring with fake sessions; no numerical DSP."""
from collections import Counter
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from rollback_coordinator import run_record
from rollback_policy import GATES
from rollback_runtime import Inputs,sha


class Budget:
    limit_seconds=None
    def finish_search(self):pass
    def report(self):return {'limit_seconds':None}


class Session:
    def __init__(self,reference,blob,**settings):
        self.original=blob;self.n=len(reference);self.profile=4;self.eligible=(0,1,2,3)
        self.initial_active=self.active=4;self.trial_limit=settings['max_trial_evaluations'];self.atomic_bound=49
        self.horizon=160;self.causal_positions=True;self.budget=Budget();self.visited=[]
        self.covered=self.trials=self.cursor=self.changed=self.level=self.current_changes=self.epoch=0
        self.counts=Counter()
    @property
    def committed_changed_groups(self):return self.current_changes
    def step(self):
        self.visited.append(self.covered);self.covered+=1;self.trials+=1;self.changed+=1
        self.cursor=40*self.covered;self.level=self.covered;self.active-=1;self.current_changes+=1
        return True
    def serialize(self):return self.original if not self.level else str(self.level).encode()*(30 if self.level==4 else 32)
    def synthesize(self):return [self.level]*self.n
    def snapshot(self):
        self.counts['snapshot_calls']+=1
        return self,self.epoch,self.level,self.active,self.current_changes,self.cursor
    def rollback(self,snapshot):
        owner,epoch,level,active,changes,cursor=snapshot
        if owner is not self or epoch!=self.epoch:raise ValueError('Invalid fake snapshot lineage')
        self.level,self.active,self.current_changes=level,active,changes;self.epoch+=1
        self.counts['rollback_calls']+=1;self.counts['rollback_synthesized_samples']+=self.cursor-cursor
    def work_counts(self):return dict(self.counts)


def admission(value,anchor):
    flags=dict.fromkeys(GATES,True)
    flags['old_pcm_pwm_floors_passed']=value.get('gate_ok',True)
    flags['joint_objective_nonregression']=value['score']<=anchor['score']+1e-12
    return flags


def choose(rows,cap):
    fitting=[r for r in rows if r['stream_bytes']<=cap];eligible=[r for r in fitting if r['automatic_quality_eligible']]
    best=lambda values:None if not values else min(values,key=lambda r:(r['score'],r['stream_bytes'],r['id']))['id']
    return dict(cap=cap,full_flash_cap=None,selected_id=best(eligible),raw_id=best(fitting),
        fitting_chains=len(fitting),eligible_chains=len(eligible),no_fit=not fitting,no_automatic_admission=not eligible)


class Evaluator:
    def decode(self,blob,n,profile):return [0 if blob[:1]==b'B' else int(blob[:1])]*n
    def measure(self,parts,*args):
        level=0 if parts[0][:1]==b'B' else int(parts[0][:1])
        return dict(score=(10.,11.,9.,8.,9.5)[level],gate_ok=level!=3)


def fixture(root,arm):
    blob=b'B'*32;path=root/'input.l4hy';path.write_bytes(blob)
    base=dict(id=-1,profile=4,nonspeech=False,samples=160,stream_bytes=32,
        segments=[dict(path=str(path.resolve()),index=0,start=0,samples=160,profile=4,file_bytes=32,stream_sha256=sha(blob))],
        reset_plans=[dict(eligible_group_indices=[0,1,2,3],initial_eligible=4,initial_active=4,trial_limit=196)])
    job=dict(id='fake-'+arm,arm=arm,local_byte_cap=32,whole_caps={'100':32,'95':30,'90':28})
    attempt=dict(records=[],real_instances=[],synthetic_instances=[])
    C=SimpleNamespace(extras=SimpleNamespace(ExistingExtraPass=Session),np=SimpleNamespace(array_equal=lambda a,b:a==b),
        chain=SimpleNamespace(_admission=admission,choose_budget=choose))
    return job,base,attempt,C


class Controller(unittest.TestCase):
    def test_rejections_restore_fields_without_refunding_and_keep_smaller_tradeoff(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);job,base,attempt,C=fixture(root,'rollback')
            with patch('rollback_coordinator.validate_frozen_fields',lambda *args:None):
                result=run_record(job,base,[0]*160,C,Evaluator(),Inputs(),root,attempt,'synthetic')
            self.assertEqual([r['action'] for r in result['stage_events']],['rollback','continue','rollback','rollback'])
            state=result['instances'][0]
            self.assertEqual(state['progress']['visited'],[0,1,2,3]);self.assertEqual(state['progress']['trials'],4)
            self.assertEqual(state['progress']['cumulative_changed'],4);self.assertEqual(state['progress']['committed_changed_groups'],1)
            self.assertEqual(state['work_counts']['rollback_calls'],3)
            self.assertEqual(result['protected_final_id'],2)
            self.assertEqual([d['selected_id'] for d in result['decisions']],[2,4,None])
            self.assertTrue((root/'synthetic/record-fake-rollback/whole/candidate-04/admission-private.json').is_file())

    def test_continue_never_rolls_back_a_bad_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);job,base,attempt,C=fixture(root,'continue')
            with patch('rollback_coordinator.validate_frozen_fields',lambda *args:None):
                result=run_record(job,base,[0]*160,C,Evaluator(),Inputs(),root,attempt,'synthetic')
            self.assertTrue(all(r['action']=='continue' for r in result['stage_events']))
            self.assertEqual(result['instances'][0]['work_counts'].get('rollback_calls',0),0)
            self.assertEqual(len(result['whole_rows']),5)

    def test_tuple_and_previous_complete_value_survive_later_metric_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);job,base,attempt,C=fixture(root,'rollback')
            class Failure(Evaluator):
                def measure(self,parts,*args):
                    if parts[0]!=b'B'*32:
                        published=root/'synthetic/record-fake-rollback/whole/candidate-01'
                        self_outer.assertEqual((published/'reset-00.l4hy').read_bytes(),b'1'*32)
                        self_outer.assertEqual(json.loads((published/'tuple-private.json').read_bytes())['status'],'serialized-unverified')
                        raise RuntimeError('Injected later metric failure')
                    return super().measure(parts,*args)
            self_outer=self
            with patch('rollback_coordinator.validate_frozen_fields',lambda *args:None):
                with self.assertRaises(RuntimeError):run_record(job,base,[0]*160,C,Failure(),Inputs(),root,attempt,'synthetic')
            folder=root/'synthetic/record-fake-rollback/whole'
            self.assertTrue((folder/'candidate-00/admission-private.json').is_file())
            self.assertFalse((folder/'candidate-01/admission-private.json').exists())
            self.assertEqual(attempt['records'][0]['status'],'failed')
            self.assertEqual(attempt['synthetic_instances'][0]['progress']['trials'],1)


if __name__=='__main__':unittest.main()

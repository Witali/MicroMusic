"""Full forward existing-extra pass, frozen fields and retained interruptions."""
import json
import unittest
from unittest.mock import patch

import numpy as np

from batch_decoder import BatchSession
from enhance_speech_compact import sse
import refine_speech_extras as extra
import speech_compact as compact
from standard_metrics import pwm_duties
from test_refine_speech_trajectory import seed


def cancellation():
    spectra=[[1,2,4,6,8,10,13,17,23,29] for _ in range(2)]
    params=[(8,40,0)]*4
    pulses=[(5,8 if not i%2 else -8) for i in range(32)];pulses[10]=(0,8)
    extras=[(-1,0)]*16;extras[5]=(30,-8)
    blob=compact.pack(640,4,spectra,params,pulses,0,0,extras=extras)[0]
    extras[5]=(0,-8)
    target=compact.pack(640,4,spectra,params,pulses,0,0,extras=extras)[0]
    return blob,target


class ExistingExtraPassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session=BatchSession('batch',speech=True,speech_compact=True,compact_only=True)
        cls.decoder=cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):cls.session.__exit__()

    def run_pass(self,reference,blob,**settings):
        return extra.refine_existing_extras(reference,blob,self.decoder,max_bytes=len(blob),
                                            speech=False,**settings)

    def test_same_byte_cancellation_and_complete_checkpoint_aliases(self):
        blob,target=cancellation();reference=compact.decode_model(target)
        results={}
        for causal in (False,True):
            seen=[]
            chosen,pcm,report,raw=self.run_pass(reference,blob,causal_positions=causal,
                candidate_sink=lambda stream,score:seen.append((stream,score)))
            results[causal]=(chosen,raw,report)
            self.assertTrue(report['all_eligible_groups_visited'])
            self.assertEqual(report['completed_active_groups'],1)
            self.assertEqual(report['eligible_active_groups'],1)
            self.assertEqual(len(report['checkpoints']),4)
            self.assertTrue(all(c['status']=='complete' for c in report['checkpoints']))
            self.assertEqual(len(set(c['candidate_id'] for c in report['checkpoints'])),1)
            self.assertEqual(len(chosen),57)
            self.assertEqual(chosen[:20],blob[:20])
            self.assertEqual(compact.unpack(chosen)[:7],compact.unpack(blob)[:7])
            self.assertEqual(len(seen),len({stream for stream,score in seen}))
            self.assertEqual(len(seen),len(report['candidates']))
            self.assertEqual(seen[0][0],blob)
            for stream,score in seen:
                model=compact.decode_model(stream)
                self.assertEqual(score,int(sse(reference,model)))
                np.testing.assert_array_equal(self.decoder.decode_one_s16(stream,len(reference)),model)
                np.testing.assert_array_equal(self.decoder.decode_one(stream,len(reference)),pwm_duties(model))
        self.assertNotEqual(results[False][1],target)
        self.assertEqual(results[False][2]['trial_evaluations'],29)
        self.assertEqual(results[True][1],target)
        self.assertEqual(results[True][2]['trial_evaluations'],43)

    def test_full_walk_preserves_inactive_and_unplayed_slots_with_live_future_state(self):
        fields=list(compact.unpack(seed(4,641)))
        fields[7][4]=fields[7][10]=(-1,0)
        blob=compact.pack(*fields[:7],extras=fields[7])[0]
        changed=list(fields[7]);changed[3]=(0,-4);changed[7]=(20,4);changed[12]=(-1,0)
        target=compact.pack(*fields[:7],extras=changed,force_extras=True)[0]
        reference=compact.decode_model(target);seen=[]
        _,_,report,_=self.run_pass(reference,blob,causal_positions=True,
            candidate_sink=lambda stream,score:seen.append(stream))
        self.assertEqual(report['eligible_active_groups'],14)
        self.assertEqual(report['preserved_unplayed_extras'],8)
        self.assertEqual(report['completed_active_groups'],14)
        self.assertTrue(report['all_eligible_groups_visited'])
        self.assertEqual(report['visited_group_indices'],report['eligible_group_indices'])
        self.assertEqual(report['visited_group_indices'],[i for i in range(16) if i not in (4,10)])
        self.assertEqual([c['target_active_groups'] for c in report['checkpoints']],[4,7,11,14])
        self.assertEqual(report['validation']['prefix_synthesized_samples'],640)
        for stream in seen:
            restored=compact.unpack(stream)
            self.assertEqual(stream[:20],blob[:20])
            self.assertEqual(restored[:7],tuple(fields[:7]))
            self.assertLessEqual(len(stream),len(blob))
            for index in (4,10,*range(16,24)):self.assertEqual(restored[7][index],fields[7][index])

    def test_cpu_stop_before_fixed_checkpoint_retains_completed_final_candidate(self):
        blob=seed(4,641);fields=list(compact.unpack(blob));fields[7][0]=(0,-8)
        target=compact.pack(*fields[:7],extras=fields[7],force_extras=True)[0]
        reference=compact.decode_model(target);clock=[0.];seen=[]
        def group(*args,**kwargs):
            clock[0]=2.
            return 0,-8,0,1
        with patch('search_cpu_budget.time.process_time',side_effect=lambda:clock[0]), \
             patch.object(extra,'refit_extra_group',side_effect=group):
            _,_,report,raw=self.run_pass(reference,blob,cpu_seconds=1,
                candidate_sink=lambda stream,score:seen.append(stream))
        self.assertEqual(report['stopped_by'],'cpu_limit')
        self.assertEqual(report['completed_active_groups'],1)
        self.assertFalse(report['all_eligible_groups_visited'])
        self.assertEqual(raw,target)
        self.assertIn(target,seen)
        self.assertTrue(all(c['status']=='partial_fallback' for c in report['checkpoints']))
        self.assertTrue(all(c['candidate_id']==report['raw_id'] for c in report['checkpoints']))
        self.assertIn('interrupted-final',report['candidates'][report['raw_id']]['labels'])

    def test_zero_cpu_quota_keeps_baseline_and_no_false_coverage(self):
        blob,target=cancellation();seen=[]
        chosen,pcm,report,raw=self.run_pass(compact.decode_model(target),blob,cpu_seconds=0,
            candidate_sink=lambda stream,score:seen.append(stream))
        self.assertEqual((chosen,raw),(blob,blob))
        self.assertEqual(seen,[blob])
        self.assertEqual(report['completed_active_groups'],0)
        self.assertEqual(report['trial_evaluations'],0)
        self.assertTrue(report['cpu_budget']['exhausted'])
        self.assertTrue(all(c['status']=='partial_fallback' for c in report['checkpoints']))

    def test_trial_stop_obeys_atomic_bound_and_preserves_last_complete_snapshot(self):
        blob=seed(4,641);fields=list(compact.unpack(blob));fields[7][0]=(0,-8)
        target=compact.pack(*fields[:7],extras=fields[7],force_extras=True)[0]
        _,_,report,_=self.run_pass(compact.decode_model(target),blob,
                                  causal_positions=True,max_trial_evaluations=49)
        self.assertEqual(report['stopped_by'],'trial_limit')
        self.assertEqual(report['completed_active_groups'],1)
        self.assertLessEqual(report['trial_evaluations'],49)
        self.assertLessEqual(len(report['candidates']),2)
        self.assertTrue(all(c['status']=='partial_fallback' for c in report['checkpoints']))

    def test_last_extra_removal_preserves_original_flag_and_frozen_header(self):
        blob,_=cancellation();fields=list(compact.unpack(blob));fields[7][5]=(-1,0)
        target=compact.pack(*fields[:7],extras=fields[7],force_extras=True)[0]
        _,_,report,raw=self.run_pass(compact.decode_model(target),blob,causal_positions=True)
        self.assertEqual(raw,target)
        self.assertEqual(raw[:20],blob[:20])
        self.assertTrue(raw[5]&128)
        self.assertEqual(report['working_active_extras'],0)
        self.assertLess(len(raw),len(blob))

    def test_no_active_and_zero_error_modes_are_explicit_and_p6_is_rejected(self):
        fields=list(compact.unpack(seed(4,641)));fields[7]=[(-1,0)]*len(fields[7])
        blob=compact.pack(*fields[:7],extras=fields[7])[0]
        reference=compact.decode_model(seed(4,641))
        chosen,_,report,raw=self.run_pass(reference,blob,max_trial_evaluations=np.int64(0),
                                         horizon=np.int64(160),max_checkpoints=np.int64(4))
        self.assertEqual((chosen,raw),(blob,blob))
        self.assertEqual(report['stopped_by'],'no_active_played_extras')
        self.assertEqual(report['trial_evaluations'],0)
        json.dumps(report,allow_nan=False)
        before=report['baseline']['pcm16']['error_energy']
        report['selected']['pcm16']['error_energy']=-1
        self.assertEqual(report['baseline']['pcm16']['error_energy'],before)
        self.assertEqual(report['raw_best']['pcm16']['error_energy'],before)
        self.assertEqual(report['candidates'][0]['metrics']['pcm16']['error_energy'],before)
        blob=seed(4,641)
        report=self.run_pass(compact.decode_model(blob),blob)[2]
        self.assertEqual(report['stopped_by'],'zero_error')
        self.assertEqual(report['completed_active_groups'],0)
        p6=seed(6,641)
        with self.assertRaisesRegex(ValueError,'profile 4'):
            self.run_pass(compact.decode_model(p6),p6)

    def test_final_native_error_is_not_hidden_by_cpu_stop(self):
        blob,target=cancellation();reference=compact.decode_model(target)
        real=self.decoder.decode_one_s16;calls=[]
        def corrupt(stream,n):
            calls.append(1)
            return real(stream,n) if len(calls)==1 else None
        with patch.object(self.decoder,'decode_one_s16',side_effect=corrupt):
            with self.assertRaisesRegex(AssertionError,'native/model'):
                self.run_pass(reference,blob,cpu_seconds=0)


if __name__=='__main__':unittest.main()

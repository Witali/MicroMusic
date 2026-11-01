"""Source/secondary/coverage contracts without codec execution or corpus input."""
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

from extra_runtime import MEASUREMENT_TOOLS,PREFIX,SOURCE_COMMIT,measurement_bridge,source_snapshot
from run_existing import validate_report,check_extra_origin
from secondary import choose_secondary,same_context


def bridge_fixture():
    inventory={PREFIX+'src/core.cpp':'unchanged'}
    inventory.update({PREFIX+'tools/'+name:'unchanged' for name in MEASUREMENT_TOOLS})
    native={key:True for key in ('library_sha256','unchanged_native_source_closure',
        'callback_enabled','rom_pointer','assembly','build_receipts')}
    runtime={'python':'same','packages':{},'threads':{}}
    old=dict(production_sources=inventory.copy(),runtime=runtime.copy(),native_bridge=native.copy(),source_commit='older')
    return old,inventory,runtime,native


def report_fixture():
    plan=dict(eligible_group_indices=[0,5],initial_active_extras=3)
    report=dict(eligible_group_indices=[0,5],eligible_active_groups=2,initial_active_extras=3,
        max_trial_evaluations=98,atomic_trial_bound=49,causal_positions=True,horizon=160,max_checkpoints=4,
        visited_group_indices=[0,5],completed_active_groups=2,all_eligible_groups_visited=True,
        preserved_unplayed_extras=1,trial_evaluations=77,cpu_budget={'limit_seconds':None},stopped_by='complete')
    return plan,report


class RuntimeContracts(unittest.TestCase):
    def test_standalone_runtime_loads_no_production_module_before_explicit_root(self):
        script=('import sys; import run_existing; '
            'assert not any(getattr(m,"__file__",None) and "/01_ACTIVE_Q0_CODEC/tools/" in '
            'str(m.__file__).replace(chr(92),"/") for m in list(sys.modules.values()))')
        subprocess.run([sys.executable,'-c',script],cwd=Path(__file__).parent,check=True,capture_output=True)

    def test_source_binding_covers_shared_persistence_and_voice_objective(self):
        self.assertIn('speech_voice_objective.py',MEASUREMENT_TOOLS)
        self.assertTrue(any(name.endswith('/run_pilot.py') for name in source_snapshot()))
        self.assertEqual(len(SOURCE_COMMIT),40)

    def test_new_operator_origin_checks_exact_root_and_file_bytes(self):
        from extra_runtime import sha
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);name=PREFIX+'tools/refine_speech_extras.py';path=root/name
            path.parent.mkdir(parents=True);path.write_bytes(b'bound operator')
            C=SimpleNamespace(extras=SimpleNamespace(__file__=str(path)))
            inventory={name:sha(path.read_bytes())};check_extra_origin(C,root,inventory)
            path.write_bytes(b'changed operator')
            with self.assertRaises(ValueError):check_extra_origin(C,root,inventory)
            C.extras.__file__=str(root/'different.py')
            with self.assertRaises(ValueError):check_extra_origin(C,root,inventory)

    def test_unchanged_measurement_bridge_is_explicitly_saved_not_fresh(self):
        args=bridge_fixture();proof=measurement_bridge(*args)
        self.assertTrue(proof['old_measurements_remain_saved_not_fresh'])
        for part in ('production_sources','runtime','native_bridge'):
            changed=list(copy.deepcopy(args))
            if part=='production_sources':changed[0][part][PREFIX+'tools/speech_voice_objective.py']='changed'
            elif part=='runtime':changed[0][part]['python']='changed'
            else:changed[0][part]['library_sha256']='changed'
            with self.assertRaises(ValueError):measurement_bridge(*changed)

    def test_complete_coverage_rejects_unpaid_missing_group(self):
        plan,report=report_fixture();validate_report(report,plan,True,1)
        report['visited_group_indices']=[0];report['completed_active_groups']=1;report['all_eligible_groups_visited']=False
        with self.assertRaises(AssertionError):validate_report(report,plan,True,1)

    def test_zero_error_is_explicitly_not_visited(self):
        plan,report=report_fixture();report.update(visited_group_indices=[],completed_active_groups=0,
            all_eligible_groups_visited=False,trial_evaluations=0,stopped_by='zero_error')
        validate_report(report,plan,True,0)
        with self.assertRaises(AssertionError):validate_report(report,plan,True,1)

    def test_secondary_filters_current_cap_and_fresh_gates_before_fixed_ties(self):
        rows=[dict(study='joint-rate-v1',arm='G-full-0',job_id=1,candidate_id=1,
            stream_bytes=n,value={'score':score,'allowed':ok}) for n,score,ok in
            ((101,0,True),(95,1,False),(100,2,True))]
        alternate=copy.deepcopy(rows[-1]);alternate.update(study='anchor-order',arm='G-time-0')
        rows.append(alternate)
        admission=lambda value,anchor:dict(gate=value['allowed'])
        self.assertIsNone(choose_secondary(rows,95,admission,{}))
        self.assertIs(choose_secondary(rows,100,admission,{}),rows[2])
        self.assertIs(choose_secondary(rows,101,admission,{}),rows[0])

    def test_secondary_cannot_change_source_level_target_or_reset_geometry(self):
        base={name:0 for name in ('source_ordinal','nonspeech','profile','mode','samples','reference','level',
            'target_reference_pcm16_sha256')};base['segments']=[dict(start=0,samples=5,profile=4)]
        base['prepared_target']=dict(pcm16_sha256='same',samples=5,sample_rate=8000)
        same_context(base,copy.deepcopy(base))
        for name in ('level','target_reference_pcm16_sha256','segments','prepared_target'):
            other=copy.deepcopy(base)
            if name=='segments':other[name][0]['samples']=4
            elif name=='prepared_target':other[name]['pcm16_sha256']='different'
            else:other[name]=1
            with self.assertRaises(ValueError):same_context(base,other)


if __name__=='__main__':unittest.main()

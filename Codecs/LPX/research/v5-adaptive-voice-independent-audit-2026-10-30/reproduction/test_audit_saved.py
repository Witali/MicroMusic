import ast
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name('audit_saved.py')
SPEC = importlib.util.spec_from_file_location('independent_adaptive_auditor',SOURCE)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def row(identifier=0, size=100, score=1., error=100., stoi=.8, periods=10, clips=0):
    return dict(id=identifier,file_bytes=size,score=score,clipped_samples=clips,
        metrics={d:dict(error_energy=error,stoi=stoi) for d in ('pcm16','pwm8')},
        voice=dict(within_tolerance_frames=periods),pwm_voice=dict(within_tolerance_frames=periods))


class IndependentAuditContracts(unittest.TestCase):
    def test_missing_pitch_cannot_win_by_disappearing_from_comparison(self):
        anchor = row()
        lost = row(1,90,.1,10.,.9,0)
        actual,allowed = audit.rank_pool([anchor,lost],100)
        self.assertEqual(actual['selected_id'],0)
        self.assertEqual(actual['raw_id'],1)
        self.assertEqual(allowed,[True,False])

    def test_unavailable_metric_cannot_pass_a_known_stoi_floor(self):
        self.assertFalse(audit.metric_floor(row(stoi=None)['metrics'],row()['metrics']))
        self.assertTrue(audit.metric_floor(row(stoi=None)['metrics'],row(stoi=None)['metrics']))

    def test_joint_score_remains_a_floor_even_when_anchor_does_not_fit(self):
        anchor,shorter = row(size=101),row(1,90,1.1,10.,.9)
        actual,allowed = audit.rank_pool([anchor,shorter],100)
        self.assertIsNone(actual['selected_id'])
        self.assertEqual(actual['raw_id'],1)
        self.assertFalse(any(allowed))

    def test_clipping_and_both_pwm_pcm_floors_are_independent(self):
        anchor = row()
        for candidate in (row(1,90,.9,90.,.9,10,1),row(1,90,.9,110.,.9)):
            self.assertFalse(all(audit.floors(candidate,anchor).values()))
        candidate = row(1,90,.9,90.,.9)
        candidate['pwm_voice']['within_tolerance_frames'] = 9
        self.assertFalse(all(audit.floors(candidate,anchor).values()))

    def test_serialized_byte_frontier_and_stable_ties(self):
        rows = [row(),row(1,90,.9,90.,.9),row(2,95,.8,80.,.9),row(3,95,.8,80.,.9)]
        actual,allowed = audit.rank_pool(rows,100)
        self.assertEqual(actual,dict(selected_id=2,raw_id=2,frontier=[1,2]))
        self.assertTrue(all(allowed))

    def test_whole_chain_budget_counts_all_bytes_and_distinct_choices(self):
        def chain(role,size,score,identity):
            return dict(role=role,stream_bytes=size,score=score,identity=identity,automatic_quality_eligible=True)
        entries = [chain('control',200,1.,['a','b']),chain('concat-selected',201,.5,['c','d']),
                   chain('concat-raw',200,1.,['a','b'])]
        result = audit.budget_choice(entries,200,100)
        self.assertEqual(result['selected'],'control')
        self.assertEqual(result['distinct_fitting_chain_count'],1)
        self.assertEqual(result['fitting_chain_count'],2)
        self.assertIsNone(audit.budget_choice(entries,200,95)['selected'])

    def test_source_pairs_and_representatives_keep_both_profiles(self):
        records = [dict(private_case_id=str(i//2),profile=4 if i%2==0 else 6,samples=10+i//2,
                        reference=dict(pcm16_sha256=str(i//2))) for i in range(10)]
        pairs = audit.groups(records)
        self.assertEqual(pairs,[[0,1],[2,3],[4,5],[6,7],[8,9]])
        self.assertEqual(audit.representatives(records,pairs),[0,2,4])
        corrupted = deepcopy(records)
        corrupted[1]['samples'] += 1
        with self.assertRaises(AssertionError):
            audit.groups(corrupted)

    def test_forbidden_study_or_search_apis_are_not_invoked(self):
        tree = ast.parse(SOURCE.read_text())
        forbidden = {'refine_candidates','refine','enhance','choose_budget','validate_pool','admission'}
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                name = node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else None
                self.assertNotIn(name,forbidden)
                if name == 'encode':
                    # UTF-8 encoding of canonical JSON is unrelated to audio
                    # seed fitting. It is the only permitted encode() call.
                    self.assertIsInstance(node.func,ast.Attribute)
                    self.assertIsInstance(node.func.value,ast.Call)
                    self.assertIsInstance(node.func.value.func,ast.Attribute)
                    self.assertEqual(node.func.value.func.attr,'dumps')
        self.assertNotIn('run_corpus',SOURCE.read_text())


if __name__ == '__main__':
    unittest.main()

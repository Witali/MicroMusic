"""Pure saved-frontier contracts, without media, metrics, search or decoding."""
import unittest
from pathlib import Path
import subprocess
import sys
from frontier_policy import classify,dominates,equivalent,frontier,outcome


def point(size,score,order=0,eligible=True):
    return dict(stream_bytes=size,score=score,order=order,origin=order,automatic_quality_eligible=eligible)


class Frontier(unittest.TestCase):
    def test_projection_import_does_not_load_production_before_explicit_root(self):
        script=('import sys; import project_existing; '
            'assert not any(getattr(m,"__file__",None) and "/01_ACTIVE_Q0_CODEC/tools/" in '
            'str(m.__file__).replace(chr(92),"/") for m in list(sys.modules.values()))')
        subprocess.run([sys.executable,'-c',script],cwd=Path(__file__).parent,check=True,capture_output=True)

    def test_complete_frontier_includes_nonselected_lower_budget_tradeoff(self):
        rows=[point(90,12),point(100,10,1),point(110,15,2)]
        self.assertEqual(frontier(rows),rows[:2])
        self.assertEqual(classify(point(95,11),frontier(rows))['status'],'extends-prior-frontier')
        self.assertEqual(outcome(point(100,11),rows[1]),'prior-lower-joint')

    def test_score_tolerance_is_rank_equivalence_not_stream_identity(self):
        old=point(100,10);same=point(100,10+5e-13)
        self.assertTrue(equivalent(old,same));self.assertFalse(dominates(old,same))
        self.assertEqual(classify(same,[old])['status'],'prior-frontier-rank-tie')
        self.assertEqual(classify(point(101,10-5e-13),[old])['status'],'dominated-by-prior')

    def test_gate_failure_cannot_be_promoted_by_better_proxy_or_smaller_bytes(self):
        value=classify(point(80,1,eligible=False),[point(100,10)])
        self.assertEqual(value['status'],'not-admissible');self.assertEqual(value['new_dominates_prior'],0)

    def test_every_nondominated_actual_tuple_is_retained(self):
        a,b=point(100,10),point(100,10,1)
        self.assertEqual(frontier([a,b]),[a,b])
        self.assertEqual(outcome(point(99,10),a),'new-smaller-rank-tie')
        self.assertEqual(classify(point(99,9),[a])['new_dominates_prior'],1)


if __name__=='__main__':unittest.main()

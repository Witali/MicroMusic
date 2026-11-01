"""No corpus inputs, production imports, decoding or numerical helper calls."""
import copy
import unittest
from rollback_policy import GATES,accept_block,coverage_targets,retained_attempts,validate_contexts


def point(score,size):return dict(score=score,stream_bytes=size)
def gates():return dict.fromkeys(GATES,True)


class RollbackPolicy(unittest.TestCase):
    def test_coverage_is_per_reset_initial_set_with_repeated_goals(self):
        self.assertEqual(coverage_targets(0),(0,0,0,0))
        self.assertEqual(coverage_targets(1),(1,1,1,1))
        self.assertEqual(coverage_targets(5),(2,3,4,5))
        self.assertEqual(coverage_targets(78),(20,39,59,78))
        for value in (True,-1,1601,2.0):
            with self.assertRaises(ValueError):coverage_targets(value)

    def test_exact_lex_order_accepts_better_score_or_equal_score_smaller_bytes(self):
        old=point(1.,100)
        self.assertTrue(accept_block(point(.9,101),gates(),old)['accepted'])
        self.assertTrue(accept_block(point(1.,99),gates(),old)['accepted'])
        self.assertTrue(accept_block(old,gates(),old)['accepted'])
        self.assertFalse(accept_block(point(1.,101),gates(),old)['accepted'])

    def test_descriptive_tolerance_cannot_admit_a_worse_protected_score(self):
        decision=accept_block(point(1.+5e-13,99),gates(),point(1.,100))
        self.assertFalse(decision['accepted']);self.assertFalse(decision['protected_pair_not_worse'])

    def test_every_original_anchor_gate_is_required_even_for_a_better_pair(self):
        for name in GATES:
            flags=gates();flags[name]=False
            result=accept_block(point(.1,90),flags,point(1.,100))
            self.assertFalse(result['accepted']);self.assertTrue(result['protected_pair_not_worse'])
        with self.assertRaises(ValueError):accept_block(point(.1,90),{},point(1.,100))
        with self.assertRaises(ValueError):accept_block(point(float('nan'),90),gates(),point(1.,100))

    def test_whole_dedup_keeps_every_stage_and_reset_order(self):
        a,b=b'a'*22,b'b'*22
        catalogue,events=retained_attempts([(0,(a,b)),(1,(a,b)),(2,(b,a)),(3,(a,b)),(4,(b,a))])
        self.assertEqual(len(catalogue),2);self.assertEqual([e['candidate_id'] for e in events],[0,0,1,0,1])
        self.assertEqual(catalogue[0]['slots'],[0,1,3]);self.assertEqual(catalogue[1]['parts'],(b,a))

    def test_no_independent_mixture_extra_stage_or_reset_change(self):
        a=b'a'*22
        for entries in ([(1,(a,))],[(0,(a,)),(2,(a,))],[(i,(a,)) for i in range(6)],[(0,(a,)),(1,(a,a))]):
            with self.assertRaises(ValueError):retained_attempts(entries)

    def test_retained_bytes_do_not_alias_mutable_producer_input(self):
        a=bytearray(b'a'*22);catalogue,events=retained_attempts([(0,(a,))]);a[0]=ord('z')
        self.assertEqual(catalogue[0]['parts'],(b'a'*22,))

    def test_fixed_contexts_keep_all_six_reset_boundaries(self):
        bases=[]
        for ordinal,count in ((20,1),(42,5)):
            bases.append(dict(source_ordinal=ordinal,profile=4,nonspeech=False,samples=160*count,stream_bytes=30*count,
                segments=[dict(index=i,start=160*i,samples=160,profile=4,file_bytes=30) for i in range(count)]))
        self.assertEqual(validate_contexts(bases)['cap_views'],12)
        changed=copy.deepcopy(bases);changed[1]['segments'].pop()
        with self.assertRaises(ValueError):validate_contexts(changed)
        changed=copy.deepcopy(bases);changed[0]['nonspeech']=True
        with self.assertRaises(ValueError):validate_contexts(changed)


if __name__=='__main__':unittest.main()

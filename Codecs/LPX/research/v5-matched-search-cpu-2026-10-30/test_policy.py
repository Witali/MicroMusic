"""Pure contracts for symmetric finite assembly and honest CPU accounting."""
import unittest

from study_policy import distinct_whole,local_frontier,metric_key,pair_cpu,whole_views


def point(index,size,sse):
    return dict(id=index,blob=bytes([index%256])*size,sse=sse)


class PolicyContracts(unittest.TestCase):
    def test_frontier_ties_dominance_and_extrema(self):
        first=point(0,22,100)
        rows=[first,point(1,22,100),point(2,23,101),point(3,24,90)]
        self.assertEqual([p['id'] for p in local_frontier(rows,24)],[0,3])
        many=[point(i,22+i,100-i) for i in range(30)]
        kept=local_frontier(many,100)
        self.assertEqual(len(kept),16)
        self.assertEqual([kept[0]['id'],kept[-1]['id']],[0,29])

    def test_sparse_reset_assembly_and_absent_view(self):
        base=(b'a'*22,b'b'*22,b'c'*22)
        rows=[dict(index=1,selected=b'd'*22,raw=None,frontier=[point(4,22,50),point(5,23,40)])]
        views=dict(whole_views(base,rows))
        self.assertEqual(views['selected'],(base[0],b'd'*22,base[2]))
        self.assertIsNone(views['raw'])
        self.assertEqual(views['minimum-byte'][1],bytes([4])*22)
        self.assertEqual(views['minimum-sse'][1],bytes([5])*23)

    def test_no_independent_reset_mixture_and_max5_roles(self):
        base=(b'a'*22,b'b'*22)
        locals=[dict(index=i,selected=bytes([i])*22,raw=bytes([i+2])*22,
            frontier=[point(i+4,22,100),point(i+6,23,50)]) for i in range(2)]
        views=whole_views(base,locals)
        self.assertEqual(len(views),5)
        self.assertEqual(dict(views)['minimum-byte'],(bytes([4])*22,bytes([5])*22))
        self.assertEqual(dict(views)['minimum-sse'],(bytes([6])*23,bytes([7])*23))

    def test_ordered_dedup_and_prior_cost(self):
        rows=distinct_whole([('x',(b'ab',b'cd')),('y',(b'abcd',))],[(b'ab',b'cd')])
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['labels'],['x','prior2-0'])
        standalone=pair_cpu(8.,8.)
        cumulative=pair_cpu(8.,8.,prior_a=2.,prior_b=.1)
        self.assertTrue(standalone['matched_total_cpu'])
        self.assertAlmostEqual(cumulative['total_cpu_ratio'],10/8.1)
        self.assertTrue(cumulative['includes_prior2'])
        self.assertFalse(pair_cpu(8.,8.,prior_a=4.,prior_b=.1)['matched_total_cpu'])
        self.assertFalse(pair_cpu(0.,0.)['matched_total_cpu'])

    def test_metric_cache_binds_serialized_tuple_target_and_context(self):
        one=metric_key('target',True,'epoch',(b'ab',b'cd'))
        self.assertNotEqual(one,metric_key('target',True,'epoch',(b'abcd',)))
        self.assertNotEqual(one,metric_key('other',True,'epoch',(b'ab',b'cd')))
        self.assertNotEqual(one,metric_key('target',False,'epoch',(b'ab',b'cd')))
        self.assertNotEqual(one,metric_key('target',True,'other',(b'ab',b'cd')))


if __name__=='__main__':
    unittest.main()

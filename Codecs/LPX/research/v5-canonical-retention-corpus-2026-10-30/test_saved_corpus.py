"""Driver contracts independent of codec fitting and native libraries."""
import unittest

from saved_corpus import Inputs, assert_incumbent, histories, player_status


class DriverContracts(unittest.TestCase):
    def test_ordered_reset_identity(self):
        baseline = (b'ab',b'cd')
        self.assertEqual(player_status((b'abcd',),baseline,{baseline}),'requires-new-proof')
        self.assertEqual(player_status(baseline,baseline,{baseline}),'unchanged-baseline')
        self.assertEqual(player_status((b'x',),baseline,{(b'x',)}),'old-union')

    def test_incumbent_tie_and_byte_cost(self):
        old = dict(automatic_quality_eligible=True,stream_bytes=100,score=.2)
        assert_incumbent(dict(score=.2,stream_bytes=99),old,100)
        with self.assertRaises(AssertionError):
            assert_incumbent(dict(score=.2,stream_bytes=101),old,101)
        with self.assertRaises(AssertionError):
            assert_incumbent(None,old,100)
        assert_incumbent(None,old,99)
        assert_incumbent(None,{**old,'automatic_quality_eligible':False},100)

    def test_sparse_histories_keep_indices(self):
        class BytesOnly:
            def stream(self,meta):
                return meta['blob']
        report = dict(candidates=[dict(id=0,file_bytes=3,admissible=True)],
            complete_byte_cap=3,selected_id=0,raw_id=0,frontier=[0],stages=[],refinement_calls=0)
        item = dict(saved=dict(segment_searches=[dict(index=35,pool=[dict(id=0,blob=b'abc')],report=report)]),
            job=dict(max_refinement_calls=4))
        def rank(*args):
            return dict(selected_id=0,raw_id=0,frontier=[0]),[True]
        def equal(a,b,*args):
            self.assertEqual(a,b)
        result = histories(item,BytesOnly(),rank,equal)
        self.assertEqual([h['index'] for h in result],[35])
        self.assertEqual(result[0]['pool'],[b'abc'])

    def test_pool_actual_cost_is_required(self):
        class BytesOnly:
            def stream(self,meta):
                return b'abc'
        item = dict(saved=dict(segment_searches=[dict(index=0,pool=[dict(id=0)],
            report=dict(candidates=[dict(id=0,file_bytes=4)]))]),job={})
        with self.assertRaises(ValueError):
            histories(item,BytesOnly(),None,None)


if __name__ == '__main__':
    unittest.main()

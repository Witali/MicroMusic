import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prefixes import (prefix_pool_ids, ranked_prefix_ids, common_prefix_descriptors,
                      retain_distinct, choose_budget, assert_incumbents_retained)


def report():
    return dict(complete_byte_cap=40, candidates=[
        dict(id=0, origin='control', score=4., file_bytes=30, admissible=True),
        dict(id=1, origin='seed', score=3., file_bytes=31, admissible=True),
        dict(id=2, origin='header_filters', score=1., file_bytes=32, admissible=True),
        dict(id=3, origin='joint_lpc_excitation', score=.1, file_bytes=41, admissible=False),
        dict(id=4, origin='joint_lpc_excitation', score=.5, file_bytes=34, admissible=False)],
        stages=[dict(parent=1, operator='header_filters', outputs=[1, 2]),
                dict(parent=2, operator='joint_lpc_excitation', outputs=[3, 4])])


class PrefixContracts(unittest.TestCase):
    def test_future_candidates_do_not_leak_into_shorter_prefixes(self):
        saved = report()
        self.assertEqual(prefix_pool_ids(saved, 0), [0, 1])
        self.assertEqual(prefix_pool_ids(saved, 1), [0, 1, 2])
        self.assertEqual(prefix_pool_ids(saved, 2), [0, 1, 2, 3, 4])
        self.assertEqual(prefix_pool_ids(saved, 4), prefix_pool_ids(saved, 2))
        self.assertEqual(ranked_prefix_ids(saved, 0), dict(selected=1, raw=1))
        self.assertEqual(ranked_prefix_ids(saved, 1), dict(selected=2, raw=2))
        self.assertEqual(ranked_prefix_ids(saved, 4), dict(selected=2, raw=4))

    def test_equal_score_uses_bytes_then_discovery_order(self):
        saved = report()
        saved['candidates'][0].update(score=3., file_bytes=30)
        self.assertEqual(ranked_prefix_ids(saved, 0)['selected'], 0)
        saved['candidates'][0]['file_bytes'] = 31
        self.assertEqual(ranked_prefix_ids(saved, 0)['selected'], 0)

    def test_bad_history_or_orphan_candidate_is_rejected(self):
        for change in ('parent', 'output', 'orphan', 'origin'):
            saved = report()
            if change == 'parent': saved['stages'][0]['parent'] = 4
            if change == 'output': saved['stages'][1]['outputs'].append(7)
            if change == 'orphan': saved['stages'][1]['outputs'].remove(4)
            if change == 'origin': saved['candidates'][2]['origin'] = 'extras'
            with self.assertRaises(ValueError): prefix_pool_ids(saved, 4)

    def test_common_depth_never_enumerates_mixed_segment_depths(self):
        saved = report()
        record = dict(segment_searches=[dict(index=i, report=copy.deepcopy(saved),
            pool=[dict(id=j, path='generic') for j in range(5)]) for i in range(3)])
        self.assertEqual([row['id'] for row in common_prefix_descriptors(record, 1, 'selected')], [2, 2, 2])
        for row in record['segment_searches'][1]['report']['candidates']:
            row['admissible'] = False
        self.assertIsNone(common_prefix_descriptors(record, 1, 'selected'))

    def test_exact_ordered_resets_are_the_dedup_key(self):
        unique = retain_distinct([('a', [b'a', b'bc']), ('same', [b'a', b'bc']),
                                  ('different-reset', [b'ab', b'c']), ('missing', None)])
        self.assertEqual(len(unique), 2)
        self.assertEqual(unique[0]['labels'], ['a', 'same'])
        self.assertEqual(unique[0]['stream_bytes'], unique[1]['stream_bytes'])

    def test_complete_cap_missing_quality_and_no_fit_remain_explicit(self):
        rows = [dict(id=0, score=1., stream_bytes=100, automatic_quality_eligible=True),
                dict(id=1, score=.1, stream_bytes=90, automatic_quality_eligible=False)]
        self.assertEqual(choose_budget(rows, 100, 100)['selected_id'], 0)
        result = choose_budget(rows, 100, 95)
        self.assertIsNone(result['selected_id'])
        self.assertEqual(result['raw_id'], 1)
        self.assertTrue(choose_budget(rows, 22, 90)['no_fit'])

    def test_retained_screen_winner_prevents_deeper_budget_regression(self):
        rows = [dict(id=0, score=2., stream_bytes=100, automatic_quality_eligible=True),
                dict(id=1, score=1., stream_bytes=100, automatic_quality_eligible=True),
                dict(id=2, score=.5, stream_bytes=110, automatic_quality_eligible=True)]
        chosen = choose_budget(rows, 100, 100)
        self.assertEqual(chosen['selected_id'], 1)
        assert_incumbents_retained(rows, chosen, [0, 1])
        with self.assertRaises(AssertionError):
            assert_incumbents_retained(rows, dict(chosen, selected_id=0), [1])

    def test_invalid_depth_and_caps_are_not_coerced(self):
        for depth in (True, -1, 5, 1.5):
            with self.assertRaises(ValueError): prefix_pool_ids(report(), depth)
        for cap in (True, 21, 22.):
            with self.assertRaises(ValueError): choose_budget([], cap, 100)


if __name__ == '__main__':
    unittest.main()

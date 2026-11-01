"""Pure metadata/recipe contracts; no corpus reads or codec execution."""
import unittest
from extra_policy import eligible_groups,slot_views,whole_roles,validate_caps


def catalogue():
    return [dict(id=0,blob=b'baseline',sse=10,labels=['baseline']),
        dict(id=1,blob=b'first',sse=8,labels=['checkpoint-1']),
        dict(id=2,blob=b'final',sse=7,labels=['interrupted-final'])]


class Policy(unittest.TestCase):
    def test_played_eligibility_keeps_partial_and_unplayed_rows_distinct(self):
        extras=[[-1,0] for _ in range(8)];extras[0]=[0,-8];extras[5]=[30,4]
        self.assertEqual(eligible_groups(201,extras),[0])
        extras[5]=[0,4];self.assertEqual(eligible_groups(201,extras),[0,5])

    def test_interrupted_final_is_honest_fallback(self):
        cps=[dict(slot=1,target_active_groups=2,completed_active_groups=2,candidate_id=1,status='complete')]
        cps += [dict(slot=i,target_active_groups=i*2,completed_active_groups=3,candidate_id=2,status='partial_fallback') for i in (2,3,4)]
        views,proof=slot_views(catalogue(),cps)
        self.assertEqual(views,[b'first',b'final',b'final',b'final'])
        self.assertEqual(proof[-1]['actual_id'],None);self.assertEqual(proof[-1]['fallback_reason'],'interrupted_final')

    def test_real_baseline_slot_is_not_missing(self):
        cat=[dict(id=0,blob=b'baseline',sse=0,labels=['baseline']+['checkpoint-'+str(i) for i in range(1,5)])]
        cps=[dict(slot=i,target_active_groups=1,completed_active_groups=1,candidate_id=0,status='complete') for i in range(1,5)]
        _,proof=slot_views(cat,cps);self.assertTrue(all(p['actual_id']==0 and p['fallback_reason'] is None for p in proof))

    def test_no_work_is_not_visited(self):
        cat=[dict(id=0,blob=b'baseline',sse=0,labels=['baseline'])]
        cps=[dict(slot=i,target_active_groups=1,completed_active_groups=0,candidate_id=0,status='no_work') for i in range(1,5)]
        _,proof=slot_views(cat,cps);self.assertTrue(all(p['actual_id'] is None for p in proof))

    def test_exactly_nine_whole_roles_and_no_product(self):
        cat=catalogue();rows=[dict(index=i,slot_blobs=[b'first']*4,selected=b'first',raw=b'final',catalogue=cat) for i in range(2)]
        roles=whole_roles((b'a',b'b'),rows)
        self.assertEqual(len(roles),9);self.assertEqual(roles[0],('baseline',(b'a',b'b')))
        self.assertEqual(roles[-1],('minimum-sse',(b'final',b'final')))

    def test_caps_must_be_real_ordered_views(self):
        rows=[dict(id=i,decisions=[dict(percent=p) for p in (100,95,90)]) for i in range(12)]
        self.assertEqual(validate_caps(rows),36)
        rows[0]['decisions'][1]['percent']=100
        with self.assertRaises(ValueError):validate_caps(rows)


if __name__=='__main__':unittest.main()

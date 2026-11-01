"""Pure fixed-policy contracts plus an opt-in actual saved-input contract."""
import copy
import os
from pathlib import Path
import unittest
from pilot_policy import ARMS,settings,local_frontier,whole_views,distinct_whole,frontier_summary,validate_scope
from pilot_runtime import Inputs,load_manifest,bridge_native,bind_production


def job(index):
    return dict(arm=ARMS[index],alpha=(0.,0.,0.,.1,1.)[index],new_generation=index>=2,
        screening='local' if index==0 else 'full')


class Policy(unittest.TestCase):
    def test_same_full_record_price_every_reset(self):
        a=settings(job(3),8000,1000)
        self.assertEqual(a['rate_lambda'],.1)
        self.assertEqual(a,settings(job(3),8000,1000))
        self.assertEqual(settings(job(4),8000,1000)['rate_lambda'],1.)

    def test_five_distinct_fixed_arms(self):
        values=[settings(job(i),1000,100) for i in range(5)]
        self.assertEqual([v['rate_search'] for v in values],[False,False,True,True,True])
        self.assertEqual([v['allocation_evaluations'] for v in values],[0,0,256,256,256])
        self.assertEqual([v['screening'] for v in values],['local','full','full','full','full'])
        self.assertTrue(all(v['objective'] is None and v['max_evaluations']==4096 for v in values))

    def test_no_fitting_api_in_settings(self):
        self.assertTrue(all('encode' not in settings(job(i),1,22) for i in range(5)))
        bad=job(0);bad['alpha']=.1
        with self.assertRaises(ValueError):settings(bad,1,22)

    def test_zero_sse_price(self):
        self.assertTrue(all(settings(job(i),0,100)['rate_lambda']==0 for i in range(5)))

    def test_local_frontier_actual_bytes_dominance_and_ties(self):
        a,b,c=b'a'*22,b'b'*23,b'c'*24
        rows=[dict(id=0,blob=a,sse=5),dict(id=1,blob=b,sse=5),dict(id=2,blob=c,sse=4)]
        self.assertEqual([r['id'] for r in local_frontier(rows,24)],[0,2])
        self.assertEqual([r['id'] for r in local_frontier(rows,23)],[0])

    def test_frontier_bounded_with_both_extremes(self):
        rows=[dict(id=i,blob=bytes([i])* (22+i),sse=100-i) for i in range(40)]
        ids=[r['id'] for r in local_frontier(rows,100)]
        self.assertEqual(len(ids),16);self.assertEqual((ids[0],ids[-1]),(0,39))

    def test_five_recipes_no_product_preserve_tails(self):
        a,b,c=b'a'*22,b'b'*23,b'c'*24
        point=dict(id=0,blob=c,sse=1)
        local=[dict(index=0,selected=b,raw=c,frontier=[point])]
        views=whole_views((a,a),local)
        self.assertEqual(len(views),5)
        self.assertTrue(all(v[1] is None or v[1][1]==a for v in views))
        self.assertEqual(len(distinct_whole(views)),3)

    def test_no_fit_and_duplicate_role_labels(self):
        a=b'a'*22
        rows=distinct_whole(whole_views((a,),[dict(index=0,selected=None,raw=None,frontier=[])]))
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['labels'],['baseline'])
        rows=distinct_whole(whole_views((a,),[dict(index=0,selected=a,raw=a,frontier=[dict(id=0,blob=a,sse=1)])]))
        self.assertEqual(len(rows),1);self.assertEqual(len(rows[0]['labels']),5)

    def test_frontier_requires_all_whole_gates(self):
        rows=[dict(id=0,stream_bytes=100,score=1.,automatic_quality_eligible=True),
            dict(id=1,stream_bytes=90,score=.9,automatic_quality_eligible=False),
            dict(id=2,stream_bytes=99,score=1.,automatic_quality_eligible=True)]
        result=frontier_summary(rows)
        self.assertEqual(result['minimum_preserved_quality_id'],2)
        self.assertEqual(result['bounded_preserved_quality_frontier_ids'],[2])

    @unittest.skipUnless(os.environ.get('JOINT_RATE_BASELINES'),'Private actual-input paths are opt-in')
    def test_actual_saved_scope_and_native_closure(self):
        inputs=Inputs()
        manifest=load_manifest(Path(os.environ['JOINT_RATE_BASELINES']),inputs)
        bases=validate_scope(manifest)
        for profile in (4,6):
            jobs=[j for j in manifest['pilot_jobs'] if j['profile']==profile]
            self.assertEqual(len(jobs),30)
            self.assertEqual(sum(len(j['reset_indices']) for j in jobs),50)
        bad=copy.deepcopy(manifest);bad['pilot_jobs'][0]['reset_indices']=[]
        with self.assertRaises(ValueError):validate_scope(bad)
        root=Path(os.environ['JOINT_RATE_SOURCE'])
        bind_production(root,'b21cb028bdb2ae3c285fbc2d9ccac96ca3c447d0')
        native,bridge=bridge_native(root,Path(os.environ['JOINT_RATE_NATIVE_CASES']),inputs)
        self.assertEqual(set(native),{'common','v5-only'})
        self.assertTrue(bridge['callback_enabled']);self.assertEqual(bridge['new_native_builds'],0)
        inputs.verify()


if __name__=='__main__':unittest.main()

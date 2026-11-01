"""Exact supplied-pool allocation, large integer costs and honest limits."""
import itertools
import random
import unittest

from speech_chain_rate import ChainRatePoint, allocate_exact_sse


def row(identifier,size,score,tag=None):
    return dict(id=identifier,stream=bytes([identifier if tag is None else tag])*size,sse=score)


def exhaustive(pools,cap):
    rates={}
    for combination in itertools.product(*pools):
        size=sum(len(p['stream']) for p in combination)
        value=(sum(p['sse'] for p in combination),tuple(p['id'] for p in combination))
        if size<=cap and (size not in rates or value<rates[size]):rates[size]=value
    frontier=[];best=None
    for size,(score,ids) in sorted(rates.items()):
        if best is None or score<best:
            frontier.append(ChainRatePoint(ids,size,score));best=score
    return tuple(frontier)


class ChainRateTests(unittest.TestCase):
    def test_mixed_allocation_beats_both_extremes_at_the_same_cap(self):
        pools=[[row(0,100,100),row(1,80,200),row(2,110,50)],
               [row(0,100,100),row(1,80,160),row(2,90,110),row(3,110,80)]]
        result=allocate_exact_sse(pools,200,baseline_ids=(0,0))
        self.assertTrue(result.exact)
        self.assertEqual(result.best,ChainRatePoint((2,2),200,160))
        self.assertEqual(result.frontier,exhaustive(pools,200))
        self.assertEqual(result.protected,(ChainRatePoint((0,0),200,200),))

    def test_small_pools_and_all_derived_caps_match_exhaustive(self):
        rng=random.Random(143)
        for case in range(50):
            pools=[[row(j+1,rng.randrange(3,14),rng.randrange(100))
                    for j in range(rng.randrange(1,5))] for _ in range(rng.randrange(1,5))]
            cap=rng.randrange(0,50)
            result=allocate_exact_sse(pools,cap,baseline_ids=(1,)*len(pools))
            self.assertTrue(result.exact)
            self.assertEqual(result.frontier,exhaustive(pools,cap),case)
            for subcap in (cap,cap*95//100,cap*90//100,cap//2):
                self.assertEqual(tuple(p for p in result.frontier if p.file_bytes<=subcap),
                                 exhaustive(pools,subcap),case)

    def test_large_integer_costs_never_round_to_float_ties(self):
        huge=1<<65
        pools=[[row(0,2,huge+1),row(1,2,huge)],[row(0,2,huge)]]
        result=allocate_exact_sse(pools,4,baseline_ids=(0,0))
        self.assertEqual(result.best.ids,(1,0))
        self.assertEqual(result.best.sse,huge*2)
        self.assertIs(type(result.best.sse),int)

    def test_stable_ids_break_exact_ties_regardless_of_input_order(self):
        pools=[[row(8,2,10),row(1,2,10)],[row(5,2,10),row(2,2,10)]]
        result=allocate_exact_sse(pools,4,baseline_ids=(8,5))
        self.assertEqual(result.best.ids,(1,2))
        self.assertEqual(result.protected[0].ids,(8,5))
        reverse=allocate_exact_sse([list(reversed(p)) for p in pools],4,baseline_ids=(8,5))
        self.assertEqual(result.frontier,reverse.frontier)

    def test_protected_whole_choices_survive_dominance_and_oversize(self):
        pools=[[row(0,4,10),row(1,2,5)],[row(0,4,10),row(1,2,5)]]
        result=allocate_exact_sse(pools,4,baseline_ids=(0,0),
                                  protected_chains=((1,0),(0,0),(1,1)))
        self.assertEqual([p.ids for p in result.protected],[(0,0),(1,0),(1,1)])
        self.assertEqual(result.protected[0].file_bytes,8)
        self.assertEqual(result.best.ids,(1,1))
        self.assertEqual(result.frontier,exhaustive(pools,4))

    def test_duplicate_serialized_bytes_must_have_consistent_scores(self):
        a=row(5,2,10,tag=7);b=row(1,2,10,tag=7)
        result=allocate_exact_sse([[a,b]],2,baseline_ids=(5,))
        self.assertEqual(result.best.ids,(1,))
        self.assertEqual(result.protected[0].ids,(5,))
        self.assertEqual(result.work['transitions'],1)
        b['sse']=11
        with self.assertRaisesRegex(ValueError,'inconsistent SSE'):
            allocate_exact_sse([[a,b]],2,baseline_ids=(5,))

    def test_state_limit_publishes_completed_whole_choices_without_exact_winner(self):
        seen=[]
        result=allocate_exact_sse([[row(0,2,10),row(1,3,5)]],3,
            baseline_ids=(0,),max_states=1,on_candidate=seen.append)
        self.assertEqual(result.status,'state_limit')
        self.assertFalse(result.exact)
        self.assertIsNone(result.best)
        self.assertEqual(result.frontier,())
        self.assertEqual(seen,[ChainRatePoint((0,),2,10),ChainRatePoint((1,),3,5)])
        self.assertEqual(result.work['completed_candidates'],2)
        self.assertEqual(result.work['peak_states'],1)
        self.assertEqual(result.protected,(ChainRatePoint((0,),2,10),))

    def test_transition_limit_never_labels_a_partial_prefix_as_whole(self):
        seen=[]
        pools=[[row(0,2,10),row(1,3,5)],[row(0,2,10)]]
        result=allocate_exact_sse(pools,6,baseline_ids=(0,0),max_transitions=2,on_candidate=seen.append)
        self.assertEqual(result.status,'transition_limit')
        self.assertFalse(result.exact)
        self.assertIsNone(result.best)
        self.assertEqual(result.frontier,())
        self.assertEqual(result.work['processed_resets'],1)
        self.assertEqual(result.work['transitions'],2)
        self.assertEqual(seen,[])

    def test_completed_candidate_is_published_before_the_next_checkpoint(self):
        seen=[];calls=[]
        class Stop(Exception):pass
        def checkpoint():
            calls.append(1)
            if len(calls)==2:raise Stop
        with self.assertRaises(Stop):
            allocate_exact_sse([[row(0,2,10),row(1,3,5)]],3,baseline_ids=(0,),
                checkpoint=checkpoint,on_candidate=seen.append)
        self.assertEqual(seen,[ChainRatePoint((0,),2,10)])

    def test_complete_no_fit_requires_no_dp_work_and_keeps_baseline(self):
        result=allocate_exact_sse([[row(0,3,0)],[row(0,3,0)]],5,baseline_ids=(0,0))
        self.assertTrue(result.exact)
        self.assertEqual(result.status,'no_pool_combination_fits')
        self.assertEqual(result.frontier,())
        self.assertEqual(result.work['transitions'],0)
        self.assertEqual(result.work['states_created'],0)
        self.assertEqual(result.work['peak_states'],0)
        self.assertEqual(result.protected,(ChainRatePoint((0,0),6,0),))

    def test_invalid_integer_costs_ids_and_protection_are_rejected(self):
        for patch in ({'id':True},{'id':-1},{'sse':1.0},{'sse':False},{'sse':-1},
                      {'stream':b''},{'stream':bytearray(b'x')}):
            candidate=row(0,2,10);candidate.update(patch)
            with self.assertRaises(ValueError):allocate_exact_sse([[candidate]],2,baseline_ids=(0,))
        for pools,ids in (([],()),([[]],(0,)),([[row(0,2,0),row(0,3,1)]],(0,)),
                          ([[row(0,2,0)]],()),([[row(0,2,0)]],(9,))):
            with self.assertRaises(ValueError):allocate_exact_sse(pools,2,baseline_ids=ids)
        for name,value in (('max_bytes',True),('max_bytes',-1),('max_states',0),
                           ('max_transitions',0),('checkpoint',1),('on_candidate',False)):
            args=dict(max_bytes=2,baseline_ids=(0,));args[name]=value
            with self.assertRaises(ValueError):allocate_exact_sse([[row(0,2,0)]],**args)


if __name__=='__main__':unittest.main()

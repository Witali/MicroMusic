"""Quality floors, rollback and measured time/size tradeoffs are independent."""
import unittest
from select_avr_candidates import select,sha

def point(blob,error,stoi=.9):return blob,None,{'full_sse':error,'quality':{'stoi':stoi}}
def timing(accepted=True,flash=9000,mean=1000,burst=170000):
    return {'accepted':accepted,'flash_bytes':flash,'mean_decode_wall_cycles':mean,
        'decode_wall_cycles_max_160':burst,'underruns':0}

class AvrSelectionTests(unittest.TestCase):
    def test_size_is_not_a_cpu_proxy_and_faster_quality_candidate_wins(self):
        baseline=point(b'baseline',100);small=point(b's',50);fast=point(b'fast',60)
        reports={b'baseline':timing(),b's':timing(False,flash=8994,mean=1100),b'fast':timing(mean=950)}
        chosen,r=select([small,fast],baseline,8,lambda b:reports[b])
        self.assertEqual(chosen[0],b'fast');self.assertEqual(len(r['measured']),3)
        self.assertNotIn(sha(b's'),r['frontier_sha256'])
    def test_stoi_cap_and_sse_floors_and_explicit_rollback(self):
        baseline=point(b'base',100)
        rejected=[point(b'x',20,.89),point(b'longer',1,.99),point(b'y',101,.99)]
        chosen,r=select(rejected,baseline,4,lambda b:timing())
        self.assertEqual(chosen[0],b'base');self.assertEqual(r['eligible_unique'],1)
        chosen,_=select([point(b'a',1)],baseline,4,lambda b:timing(b==b'base'))
        self.assertEqual(chosen[0],b'base')
        with self.assertRaises(ValueError):select([],baseline,1,lambda b:timing())
        with self.assertRaises(ValueError):select([],baseline,4,lambda b:timing(False))
    def test_limit_counts_baseline_and_equal_quality_prefers_full_elf(self):
        baseline=point(b'base',100,None);other=point(b'abc',100,None)
        chosen,r=select([other],baseline,4,lambda b:timing(flash=10000 if b==b'abc' else 9000))
        self.assertEqual(chosen[0],b'base');self.assertEqual(len(r['frontier_sha256']),2)
        chosen,r=select([point(b'a',1,None)],baseline,4,lambda b:timing(),max_measurements=1)
        self.assertEqual(chosen[0],b'base');self.assertEqual(len(r['measured']),1)
        with self.assertRaises(ValueError):select([],baseline,4,lambda b:timing(),0)

if __name__=='__main__':unittest.main()

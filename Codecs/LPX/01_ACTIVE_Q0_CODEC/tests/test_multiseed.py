"""Target-specific floors and content-verified persistent joint cache."""
from pathlib import Path
import sys,tempfile,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from benchmark_multiseed import choose,JointCache


def item(raw,error,stoi):return raw,np.zeros(4,np.int16),{'full_sse':error,'quality':{'stoi':stoi}}


class MultiseedTests(unittest.TestCase):
    def test_target_stoi_floor_is_not_relaxed_by_another_feasible_seed(self):
        baseline=item(b'baseline',100,.9)
        other=item(b'less',50,.7);good=item(b'good',80,.92);oversize=item(b'x'*40,1,.99)
        self.assertEqual(choose([other,good,oversize],baseline,10)[0],b'good')
        self.assertEqual(choose([other],baseline,10)[0],b'baseline')
        self.assertEqual(choose([],baseline,10)[0],b'baseline')
        with self.assertRaises(ValueError):choose([],baseline,1)

    def test_equal_sse_prefers_smaller_file_without_changing_sample_count(self):
        baseline=item(b'baseline',0,None);short=item(b'ok',0,None)
        chosen=choose([short],baseline,len(baseline[0]));self.assertEqual(chosen[0],b'ok')
        self.assertEqual(len(chosen[1]),4)

    def test_cache_checks_pcm_stream_input_seed_and_source_revision(self):
        ref=np.array([1,2,3,4],np.int16);calls=[]
        def encoder(seed,reference,decoder,lam,**options):
            calls.append((seed,lam));return b'encoded:'+seed,np.asarray(reference).copy(),{'quality':{'stoi':None}}
        with tempfile.TemporaryDirectory() as td:
            cache=JointCache(td,ref,'source1',encoder);a=cache(b'seed',ref,None,.01,kind='music')
            self.assertEqual(len(calls),1)
            warm=JointCache(td,ref,'source1',encoder);b=warm(b'seed',ref,None,.01,kind='music')
            self.assertEqual(len(calls),1);self.assertEqual(a[0],b[0]);np.testing.assert_array_equal(a[1],b[1])
            pcm=next(Path(td).glob('*.pcm16le'));pcm.write_bytes(b'broken')
            JointCache(td,ref,'source1',encoder)(b'seed',ref,None,.01,kind='music');self.assertEqual(len(calls),2)
            raw=next(Path(td).glob('*.l4hy'));raw.write_bytes(b'changed')
            JointCache(td,ref,'source1',encoder)(b'seed',ref,None,.01,kind='music');self.assertEqual(len(calls),3)
            JointCache(td,ref,'source2',encoder)(b'seed',ref,None,.01,kind='music');self.assertEqual(len(calls),4)
            JointCache(td,ref,'source2',encoder)(b'newseed',ref,None,.01,kind='music');self.assertEqual(len(calls),5)
            with self.assertRaises(ValueError):cache(b'seed',ref+1,None,.01,kind='music')


if __name__=='__main__':unittest.main()

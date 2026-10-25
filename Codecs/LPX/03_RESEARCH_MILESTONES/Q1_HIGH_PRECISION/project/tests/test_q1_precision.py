"""LPX4 experimental fractional-Q1 regression. No private voices required.

The Q1 split-multiply optimization MUST be exactly the same as Q1 64-bit
reference on the same L4HY stream. No claim about audio fidelity is implied.
"""
import sys, unittest, subprocess, tempfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tests')]
from lpx4 import encode
from l3av_parse import unpack
from fuzzer import gen

class Q1PrecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='lpx4q1test_')
        cls.root=Path(cls.tmp.name)
        cls.exes={}
        for tag,extra in [
            ('legacy',[]),
            ('q1wide',['-DLPX4_WIDE_FRAC=1']),
            ('q1split',['-DLPX4_WIDE_FRAC=1','-DLPX4_FAST_SPLIT_Q1=1']),
            ('q8',['-DLPX4_WIDE_FRAC=8'])
        ]:
            dst=cls.root/tag
            subprocess.run(['g++','-O3','-std=c++11',*extra,'-I'+str(ROOT/'src'),
                str(ROOT/'src/Lpx4HybridCore.cpp'),str(ROOT/'tests/decode_s16_host.cpp'),
                '-o',str(dst)],capture_output=True,text=True,check=True)
            cls.exes[tag]=dst
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def decode(self,tag,data):
        inp=self.root/'input.l4hy';out=self.root/(tag+'.raw')
        inp.write_bytes(data)
        p=subprocess.run([str(self.exes[tag]),str(inp),str(out)],capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr.decode(errors='replace'))
        return np.fromfile(out,dtype='<i2')
    def test_synthetic(self):
        blob=(ROOT/'examples/SYNTHETIC_CELP_BUDGET/synthetic_celp_budget.l4hy').read_bytes()
        a=self.decode('q1wide',blob); b=self.decode('q1split',blob)
        self.assertTrue(np.array_equal(a,b))
        self.assertEqual(len(a),int.from_bytes(blob[8:12],'little'))
        q8=self.decode('q8',blob)
        self.assertEqual(a.shape,q8.shape)
    def test_random_fuzz(self):
        good=0
        for seed in range(32):
            try:
                doc=unpack(gen(seed))
                b,*_=encode(doc,min_snr=float('inf'),fast=True)
                x=self.decode('q1wide',b)
                y=self.decode('q1split',b)
            except ValueError:
                continue
            self.assertTrue(np.array_equal(x,y),f'seed={seed}')
            good+=1
        self.assertGreaterEqual(good,16)
    def test_pcm16_gains_a_sub_bit(self):
        odd=False
        for seed in range(32):
            doc=unpack(gen(seed))
            blob,*_=encode(doc,min_snr=float('inf'),fast=True)
            s=self.decode('q1split',blob)
            odd |= bool(np.any((s&1)==1))
            if odd:break
        self.assertTrue(odd, 'No generated test exercised a fractional PCM16 output')
    def test_standard_legacy_stays_even(self):
        blob=(ROOT/'examples/SYNTHETIC_CELP_BUDGET/synthetic_celp_budget.l4hy').read_bytes()
        s=self.decode('legacy',blob)
        self.assertTrue(np.all((s&1)==0))

if __name__=='__main__': unittest.main()

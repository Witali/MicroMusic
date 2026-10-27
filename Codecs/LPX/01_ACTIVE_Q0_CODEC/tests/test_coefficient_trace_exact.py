"""Compare compiled coefficient arithmetic with the frozen Python model."""
import hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
import numpy as np
from q0_model import coefficient_trace
from wav_lpc import pack_frames

def inputs():
    rng=np.random.default_rng(20261027)
    for n in (1,19,20,39,40,159,160,161,319,320,321,641,1280):
        for pattern in range(4):
            vectors=[]
            for i in range((n+159)//160):
                if pattern==0:v=[0]*10 if i%2==0 else [1023]*10
                elif pattern==1:v=[k+(1014 if i%2 else 0) for k in range(10)]
                elif pattern==2:v=sorted(map(int,rng.integers(0,1024,10)))
                else:v=[int(k*1023//11)+(i%3) for k in range(1,11)]
                vectors.append(v)
            yield f'n{n}-pattern{pattern}',pack_frames(vectors),n

def output_hash(co):return hashlib.sha256(np.asarray(co,dtype='<i8').tobytes()).hexdigest()

class CoefficientTraceExactTests(unittest.TestCase):
    def test_frozen_outputs_and_original_reference(self):
        expected=json.loads(Path(__file__).with_name('coefficient_trace_golden.json').read_text())['output_sha256']
        observed={}
        for name,frames,n in inputs():
            actual=coefficient_trace(frames,n)
            np.testing.assert_array_equal(actual,coefficient_trace(frames,n,reference=True))
            observed[name]=output_hash(actual)
        self.assertEqual(len(observed),52)
        self.assertEqual(observed,expected)

    def test_native_anchor_conversion_matches_frozen_baseline(self):
        # Frozen from decoder commit 5dea80be, not the implementation under test.
        # 2048 ten-coefficient vectors * 17 anchor positions * 10 s16 outputs.
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'anchor-coefficients.exe'
            subprocess.run(['g++','-O2','-std=c++11','-I'+str(root/'src'),
                str(root/'tests/anchor_coefficients.cpp'),'-o',str(exe)],
                check=True,capture_output=True)
            data=subprocess.check_output([str(exe)])
        self.assertEqual(len(data),2048*17*10*2)
        self.assertEqual(hashlib.sha256(data).hexdigest(),
            'f1058263c4dfa7d1860259b97d367086018653c67d49c4cd5f3fd55054f94588')

    def test_same_invalid_frames_and_counts(self):
        bad=[([],1),([b'\0'],0),([b'\0'],1),([b'\x06'+bytes(10)],1),([b'\x07'],1),
             (pack_frames([[1023]*10])+[b'\x06'+bytes([127]*10)],320)]
        for frames,n in bad:
            for reference in (False,True):
                with self.assertRaises(ValueError):coefficient_trace(frames,n,reference=reference)

if __name__=='__main__':unittest.main()

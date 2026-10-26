"""Frozen pre-optimization outputs cover state, ties, clipping and all modes."""
import hashlib,json,struct,unittest
from pathlib import Path
import numpy as np
from joint_rate import trellis
from lpx4 import decode
from q0_model import coefficient_trace,table
from test_beam_excitation import raw_fixture

def inputs():
    rng=np.random.default_rng(20261026)
    co=coefficient_trace(decode(raw_fixture(samples=40))[0],40)
    steps=table('scale_table.inc');index=0
    for beam in (1,4,8):
        for n in (1,19,20,39,40):
            for bits in (0,2,3,6):
                modes=[(0,0,0,0)] if not bits else [(0,0,0,0),(0,0,0,2),(1,18,31,1),(1,145,14,6),(2,18,31,0),(2,145,0,0)]
                if bits==3:modes.append((0,0,0,7))
                for mode in modes:
                    target=rng.integers(-32768,32768,n,dtype=np.int64)
                    if index%4==0:target[:]=0
                    if index%4==1:target[:]=np.resize(np.asarray([-32768,32767],np.int64),n)
                    hist=rng.integers(-20000,20001,10,dtype=np.int64)
                    qh=rng.integers(-32,32,145,dtype=np.int64)
                    dd=(0,-32767,32767)[index%3];cc=(0,-16384,16384)[index%3]
                    pre=(0,15000,16384)[index%3];bright=(0,11469)[index%2]
                    args=(target,co[:n],hist,dd,cc,pre,bright,int(steps[(64,160,240)[index%3]]),bits,qh,np.asarray(mode,np.int64),(0.,.003,.1)[index%3],1e6,beam)
                    yield f'{index:03d}-b{beam}-n{n}-w{bits}-m{mode[0]}-k{mode[3]}',args
                    index+=1

def output_hash(result):
    q,h,d,c,loss,cost,valid=result
    digest=hashlib.sha256()
    digest.update(np.asarray(q,dtype='<i8').tobytes());digest.update(np.asarray(h,dtype='<i8').tobytes())
    digest.update(struct.pack('<qqdq?',int(d),int(c),float(loss),int(cost),bool(valid)))
    return digest.hexdigest()

class ExactTrellisTests(unittest.TestCase):
    def test_frozen_original_outputs(self):
        golden=json.loads(Path(__file__).with_name('joint_trellis_golden.json').read_text())
        observed={name:output_hash(trellis(*args)) for name,args in inputs()}
        self.assertEqual(len(observed),300)
        self.assertEqual(observed,golden['output_sha256'])

if __name__=='__main__':unittest.main()

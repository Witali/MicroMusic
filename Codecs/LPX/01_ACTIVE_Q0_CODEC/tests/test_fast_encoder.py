"""Differential tests: accelerated desktop encoder MUST preserve exact files.

All fixtures here are synthetic and redistributable. This suite checks Numba
mode selection and VBR, including original quantizer outputs/PCM sidecars.
"""
from pathlib import Path
import sys,unittest,struct,json,tempfile,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'encoder_vbr'/'tools')]
from lpx4 import encode,select_chunk
from fast_lpx4 import select_chunk_fast
from l3av_parse import unpack
from encode_vbr_fixedexact import make
from fast_vbr import Prepared, make_fast

class ExactFastTests(unittest.TestCase):
 def test_mode_selector_random(self):
  rng=np.random.default_rng(68239)
  for bits in [0,2,3,4,5,6]:
   lo=-(1<<(bits-1)) if bits else 0;hi=1<<(bits-1) if bits else 1
   for length in [0,40,144,145,165,500]:
    for _ in range(5):
     hist=rng.integers(lo,hi,length).tolist()
     y=rng.integers(lo,hi,40).tolist()
     a=select_chunk(y,hist,bits,float('inf'))
     b=select_chunk_fast(y,hist,bits,float('inf'))
     self.assertEqual(a,b,(bits,length,y[:5]))

 def test_real_synthetic_exact_encoding(self):
  path=ROOT/'examples'/'SYNTHETIC_SOURCE_ONLY'/'synthetic_v1.l3av'
  doc=unpack(path.read_bytes())
  original=encode(doc)[0]
  accelerated=encode(doc,fast=True)[0]
  self.assertEqual(original,accelerated)

 def test_vbr_random_lambdas_exact(self):
  rng=np.random.default_rng(3355)
  n=640
  t=np.arange(n)/8000
  # Synthetic music-like sample: no copyrighted/sensitive speech.
  x=(.13*np.sin(2*np.pi*181*t)+.07*np.sin(2*np.pi*410*t)+.015*rng.standard_normal(n)).clip(-.95,.95)
  with tempfile.TemporaryDirectory(prefix='lpx4_fast_test_') as wd:
   td=Path(wd)
   analysis=td/'lsf.json';trace=td/'coeff.csv';legacy=td/'old.lpx3'
   frames=(n+159)//160
   co=[list(np.linspace(.07,.88,10)) for _ in range(frames)]
   analysis.write_text(json.dumps({'meta':{'pre':.85},'lsfFrame':co}))
   # A deliberately simple, varying 10-tap Q12 coefficient trace.
   rows=[]
   for j in range((n+19)//20):
    taps=[(-1)**k*(130-k*7)+(j%4)*3 for k in range(10)]
    rows.append([20*j]+taps)
   np.savetxt(trace,np.asarray(rows),fmt='%d',delimiter=',')
   legacy.write_bytes(struct.pack('<4sBBHIIHHI',b'LPX3',1,3,8000,n,24,80,0,(n+79)//80))
   ctx=Prepared(x,analysis,trace,legacy)
   a=td/'slow.l3av';b=td/'fast.l3av'
   for lam in [0.0,.0002,.0007,.00115,.0014,.003,.008]:
    r1=make(x,analysis,trace,legacy,a,lam)
    r2=make(x,analysis,trace,legacy,b,lam,fast=True,context=ctx)
    self.assertEqual(r1,r2)
    self.assertEqual(a.read_bytes(),b.read_bytes(),lam)
    r3=make_fast(x,analysis,trace,legacy,td/'fast_lambda.l3av',lam,context=ctx,block_lambdas=np.full(len(ctx.blocks),lam,dtype=np.float64))
    self.assertEqual(a.read_bytes(),(td/'fast_lambda.l3av').read_bytes(),('block lambda exact',lam))
    self.assertEqual((td/'slow.l3av.exact.pcm8').read_bytes(),(td/'fast.l3av.exact.pcm8').read_bytes())
    self.assertEqual((td/'slow.l3av.q_signed.i16').read_bytes(),(td/'fast.l3av.q_signed.i16').read_bytes())
    doc=unpack(a.read_bytes())
    self.assertEqual(encode(doc)[0],encode(doc,fast=True)[0])

if __name__=='__main__':unittest.main()

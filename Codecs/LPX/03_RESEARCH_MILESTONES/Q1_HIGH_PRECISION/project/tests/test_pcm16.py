"""Public PCM16 regression: real C++ fixed-point decoder, synthetic L4HY.

No copyrighted speech is required; the optional private reference tests are
in the separate local research report and not in this public source package.
"""
import hashlib,subprocess,sys,tempfile,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from batch_decoder import BatchSession
from tune_pcm16 import metrics, set_header, tune

class Pcm16Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.dir=Path(cls.tmp.name)
  cls.sample=(ROOT/'examples/SYNTHETIC_CELP_BUDGET/synthetic_celp_budget.l4hy')
  cls.blob=cls.sample.read_bytes();cls.n=int.from_bytes(cls.blob[8:12],'little')
  for mode,source in (('s16','decode_s16_host.cpp'),('q14','decode_q14_host.cpp'),('s8','decode_host.cpp')):
   exe=cls.dir/mode
   subprocess.run(['g++','-O3','-std=c++11','-I'+str(ROOT/'src'),
      str(ROOT/'src/Lpx4HybridCore.cpp'),str(ROOT/'tests'/source),'-o',str(exe)],check=True,capture_output=True)
  cls.batch_ctx=BatchSession('batch');cls.batch=cls.batch_ctx.__enter__()
 @classmethod
 def tearDownClass(cls):cls.batch_ctx.__exit__(None,None,None);cls.tmp.cleanup()
 def exe(self,cmd,out):
  subprocess.run([str(self.dir/cmd),str(self.sample),str(out)],check=True,capture_output=True)
  return out.read_bytes()
 def test_s16_matches_q14_exact_scaling(self):
  b16=self.exe('s16',self.dir/'hi.pcm16');q14=self.exe('q14',self.dir/'raw.pcm14')
  s16=np.frombuffer(b16,dtype='<i2');q=np.frombuffer(q14,dtype='<i2')
  self.assertEqual(len(s16),self.n)
  self.assertTrue(np.array_equal(s16,np.clip(q.astype(np.int32)*2,-32768,32767)))
  self.assertTrue(np.all((s16.astype(np.int32)%2)==0))
  self.assertTrue(np.array_equal(s16,self.batch.decode_one_s16(self.blob,self.n)))
 def test_native_pcm8_remains_consistent(self):
  b=self.exe('s8',self.dir/'legacy.pcm8')
  self.assertEqual(b,self.batch.decode_one(self.blob,self.n).tobytes())
 def test_corrupt_candidate_isolated(self):
  candidates=self.batch.decode_many_s16([self.blob,b'invalid',self.blob],self.n)
  self.assertIsNotNone(candidates[0]);self.assertIsNone(candidates[1])
  self.assertTrue(np.array_equal(candidates[0],candidates[2]))
 def test_header_tuning_never_changes_size(self):
  ref=self.batch.decode_one_s16(self.blob,self.n)
  b,out,r=tune(self.blob,ref,self.batch,trial_limit=40)
  self.assertEqual(len(b),len(self.blob))
  self.assertEqual(r['old']['pcm16_sha256'],r['new']['pcm16_sha256'])
 def test_s16_independent_of_pwm_gain(self):
  samples=[]
  for gain in (120,136):
   exe=self.dir/f'decode{gain}'
   subprocess.run(['g++','-O3','-std=c++11',f'-DLPX4_PWM_GAIN={gain}',
                   '-I'+str(ROOT/'src'),str(ROOT/'src/Lpx4HybridCore.cpp'),
                   str(ROOT/'tests/decode_s16_host.cpp'),'-o',str(exe)],check=True,capture_output=True)
   out=self.dir/f'out{gain}.pcm16';subprocess.run([str(exe),str(self.sample),str(out)],check=True,capture_output=True)
   samples.append(out.read_bytes())
  self.assertEqual(samples[0],samples[1])

if __name__=='__main__':unittest.main()

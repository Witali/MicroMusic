import sys,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from auto_search_lambda import Result,eligible,DEFAULT_LAMBDAS
class AutoTests(unittest.TestCase):
 def x(self,byt=1000,stoi=.95,snr=30,calls=1000,max160=100,maxsample=4):
  return Result('x',byt,snr,stoi,'sha',decode_cost_proxy={
   'bit_calls':calls,'max_bit_calls_160':max160,'max_bit_calls_sample':maxsample,'lsf_converts':10})
 def test_grid_contains_detected_best(self):
  self.assertIn(.00115,DEFAULT_LAMBDAS)
  self.assertIn(.0014,DEFAULT_LAMBDAS)
 def test_no_growth_size(self):
  ok,why=eligible(self.x(byt=1001),self.x(),max_bytes=1000)
  self.assertFalse(ok)
 def test_quality_gates(self):
  ok,_=eligible(self.x(stoi=.91),self.x(stoi=.95),max_stoi_drop=.001)
  self.assertFalse(ok)
  ok,_=eligible(self.x(snr=28),self.x(snr=30),max_snr_drop=.1)
  self.assertFalse(ok)
 def test_cost_gates(self):
  a=self.x(calls=1100,max160=120)
  ok,why=eligible(a,self.x(),max_cost_growth=.05)
  self.assertFalse(ok)
  self.assertIn('read-bit',why)
 def test_accept_valid(self):
  ok,_=eligible(self.x(byt=950,stoi=.951,snr=30.2,calls=1010,max160=102),
                self.x(),max_bytes=1000,max_cost_growth=.05)
  self.assertTrue(ok)
 def test_samples_manifest(self):
  c=json.loads((ROOT/'samples/catalog.json').read_text())
  self.assertEqual({v['lang'] for v in c['short_samples']},{'ru','en'})
  self.assertTrue(all(v['license'] and v['attribution'] for v in c['short_samples']))
if __name__=='__main__':unittest.main()

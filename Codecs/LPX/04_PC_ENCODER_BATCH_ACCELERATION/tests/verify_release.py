#!/usr/bin/env python3
"""Standalone exact-mode LPX4 vs LPX3 PCM parity and malformed-input tests.
Usage: python3 tests/verify_release.py [number_of_random_tests]
Dependencies: Python standard library, g++ (pystoi not needed).
"""
import sys,subprocess,tempfile,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'tools'));sys.path.insert(0,str(R/'tests'))
from l3av_parse import unpack
from lpx4 import encode,decode
from rice_v7 import encode_v7
from fuzzer import gen

def run(count=60):
 with tempfile.TemporaryDirectory() as td:
  temp=Path(td)
  def build(out,files,inc,flags=[]):
   subprocess.run(['g++','-std=c++11','-O2','-fno-strict-aliasing']+flags+['-I',str(inc)]+[str(x) for x in files]+['-o',str(out)],check=True)
  new=temp/'new';old=temp/'old';exact=temp/'exact'
  build(new,[R/'src'/'Lpx4HybridCore.cpp',R/'tests'/'decode_host.cpp'],R/'src')
  build(exact,[R/'src'/'Lpx4HybridCore.cpp',R/'tests'/'decode_host.cpp'],R/'src',['-DLPX4_ALLOW_SPARSE=0','-DLPX4_PWM_GAIN=127','-DLPX4_PWM_ROUND=0'])
  build(old,[R/'reference_v7'/'Lpx3AvrCore.cpp',R/'reference_v7'/'decode_host.cpp'],R/'reference_v7')
  cases=[('synthetic',(R/'examples'/'SYNTHETIC_SOURCE_ONLY'/'synthetic_v1.l3av').read_bytes())]
  cases += [(f'generated-{seed}',gen(20261023+seed)) for seed in range(count)]
  results=[]
  for name,raw in cases:
   doc=unpack(raw)
   l4,stats,chunk,q=encode(doc)
   l3,_=encode_v7(doc)
   frames,blocks,decodedQ=decode(l4)
   assert decodedQ==q==[v for b in doc['blocks'] for v in b['q']]
   assert [(b['bits'],b['scale']) for b in blocks]==[(b['bits'],b['scale']) for b in doc['blocks']]
   (temp/'in.l4hy').write_bytes(l4);(temp/'in.l3av').write_bytes(l3)
   for decoder,inp,out in [(old,'in.l3av','a.pcm8'),(new,'in.l4hy','b.pcm8'),(exact,'in.l4hy','c.pcm8')]:
    p=subprocess.run([str(decoder),str(temp/inp),str(temp/out)],capture_output=True)
    if p.returncode:raise RuntimeError(name+' '+decoder.name+': '+str(p.stderr))
   a=(temp/'a.pcm8').read_bytes();b=(temp/'b.pcm8').read_bytes();c=(temp/'c.pcm8').read_bytes()
   assert a==c and len(b)==len(a)==doc['sampleCount'],name # B uses new calibrated 8-bit PWM quantizer
   results.append(dict(name=name,samples=len(b),size_lpx3=len(l3),size_lpx4=len(l4),sha256=hashlib.sha256(b).hexdigest()))
  tests=0
  good=(temp/'in.l4hy').read_bytes()
  for i in range(1,10):
   (temp/'broken.l4hy').write_bytes(good[:i]);
   assert subprocess.run([str(new),str(temp/'broken.l4hy'),str(temp/'bad.pcm8')],capture_output=True).returncode
   tests+=1
  for a in (0,1,255):
   bad=bytearray(good);bad[4]=a;(temp/'broken.l4hy').write_bytes(bad)
   assert subprocess.run([str(new),str(temp/'broken.l4hy'),str(temp/'bad.pcm8')],capture_output=True).returncode
   tests+=1
  data={'valid_streams':len(results),'malformed_streams':tests,'samples_checked':sum(x['samples'] for x in results),'synthetic_case':results[0]}
  (R/'reports').mkdir(exist_ok=True)
  (R/'reports'/'public_verification.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
  print(json.dumps(data,indent=2))
if __name__=='__main__':run(int(sys.argv[1]) if len(sys.argv)>1 else 60)

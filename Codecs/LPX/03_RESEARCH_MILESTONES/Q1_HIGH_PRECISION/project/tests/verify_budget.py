#!/usr/bin/env python3
"""CPU *structural* budget tests, PCM/q parity and stream integrity.
These tests are NOT cycle measurements. Hardware 16MHz proof is separate.
"""
import json, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from lpx4 import decode, encode
from l3av_parse import unpack

def run():
 with tempfile.TemporaryDirectory() as tmp:
  tmp=Path(tmp); host=tmp/'decode';tracer=tmp/'trace'
  for path,driver,flags in [(host,'decode_host.cpp',[]),(tracer,'trace_q.cpp',['-DLPX3_Q_DIAG=1'])]:
   subprocess.run(['g++','-O2','-std=c++11','-DLPX4_ALLOW_SPARSE=1']+flags+['-I'+str(ROOT/'src'),str(ROOT/'src/Lpx4HybridCore.cpp'),str(ROOT/'tests'/driver),'-o',str(path)],check=True)
  samples=0; records=[]
  cases=list((ROOT/'examples'/'SYNTHETIC_CELP_BUDGET').glob('*.l4hy'))
  cases+=list((ROOT/'private_tests').glob('*_abs.l4hy'))
  for datafile in cases:
   data=datafile.read_bytes()
   frames,blocks,q=decode(data)
   pcmfile=tmp/'pcm';qfile=tmp/'q'
   for executable,output in [(host,pcmfile),(tracer,qfile)]:
    proc=subprocess.run([str(executable),str(datafile),str(output)],capture_output=True)
    assert proc.returncode==0,(datafile,proc.stderr)
   assert qfile.read_bytes()==bytes((z&255 for z in q)),datafile
   assert len(pcmfile.read_bytes())==len(q),datafile
   samples+=len(q)
   records.append({'file':datafile.name,'size_bytes':len(data),'samples':len(q)})
  # Version 1 is not silently treated as version 2.
  data=bytearray(cases[0].read_bytes())
  data[4]=1
  bad=tmp/'bad.l4hy';bad.write_bytes(data)
  assert subprocess.run([str(host),str(bad),str(tmp/'fail.pcm')],capture_output=True).returncode!=0
  # A series of truncated files cannot report a clean fully decoded stream.
  valid=cases[0].read_bytes()
  for n in [0,2,8,19,len(valid)//4,len(valid)//2,len(valid)-3]:
   bad.write_bytes(valid[:n])
   assert subprocess.run([str(host),str(bad),str(tmp/'fail.pcm')],capture_output=True).returncode!=0,n
  src=(ROOT/'examples/SYNTHETIC_CELP_BUDGET/synthetic_celp_v1.l3av').read_bytes()
  d=unpack(src)
  out,stats,chunks,_=encode(d,15)
  assert out==cases[0].read_bytes(), 'offline encoder must reproduce the embedded synthetic release'
  assert any(c['mode']=='sparse' for c in chunks)
  assert all(c['pulses']<=10 for c in chunks)
  report={'status':'PASS','case_count':len(cases),'samples':samples,'case_details':records,
    'max_sparse_pulses_per_40_samples':10,'LPC_taps':10,'max_rice_unary_zeroes':8,
    'ATmega328P_F_CPU':16000000,'audio_rate':8000,'cycles_per_sample_available':2000,
    'measured_avr_cycles':None,'real_time_at_16MHz_proven':False}
  (ROOT/'reports').mkdir(exist_ok=True)
  (ROOT/'reports/budget_structural_checks.json').write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps(report,indent=2))
if __name__=='__main__':run()

#!/usr/bin/env python3
"""Build and compare R3 vs chosen R4 decoder across all included Speex NB8 streams."""
from pathlib import Path
import subprocess, wave, hashlib, tempfile
R=Path(__file__).resolve().parents[1]
P=R/'src'
CC='gcc'
def build(src,exename):
 subprocess.run([CC,'-O2','-fwrapv','-std=c11','-I'+str(P),str(P/'host_decode.c'),str(src),str(P/'speex_tables.c'),str(P/'cos_table.c'),'-o',str(exename)],check=True)
with tempfile.TemporaryDirectory() as tmp:
 t=Path(tmp); ref=t/'ref'; fast=t/'fast'
 build(R/'variants/baseline.c',ref)
 build(P/'speex_nb8.c',fast)
 total=0
 for src in sorted((R/'data').glob('*.spxraw')):
  out1=t/'ref.wav';out2=t/'fast.wav'
  subprocess.run([str(ref),str(src),str(out1)],check=True,stderr=subprocess.DEVNULL)
  subprocess.run([str(fast),str(src),str(out2)],check=True,stderr=subprocess.DEVNULL)
  with wave.open(str(out1),'rb') as f:a=f.readframes(f.getnframes())
  with wave.open(str(out2),'rb') as f:b=f.readframes(f.getnframes())
  assert a==b, 'DIFFERENT PCM: '+src.name
  total+=len(a)//2
  print(f'PASS {src.name:37} {len(a)//320:3} frames PCM byte-identical')
 print(f'PASS total {total//160} frames and {total} PCM samples')

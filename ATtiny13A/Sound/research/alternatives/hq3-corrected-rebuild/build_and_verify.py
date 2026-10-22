#!/usr/bin/env python3
from pathlib import Path
import subprocess,hashlib
root=Path(__file__).resolve().parent
for name in ['chego','otvechaesh','vinni']:
 d=root/name
 def run(*args):subprocess.run(args,check=True,cwd=d)
 expected=(d/'firmware.bin').read_bytes()
 run('clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','rebuild.o')
 run('llvm-objcopy','-O','binary','rebuild.o','rebuild.bin')
 b=(d/'rebuild.bin').read_bytes()
 assert b==expected,name
 print(name,'reproducible',len(b),'Flash bytes, SHA256',hashlib.sha256(b).hexdigest())
 (d/'rebuild.bin').unlink();(d/'rebuild.o').unlink()
subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','firmware.o'],cwd=root/'reference'/'chego',check=True)
# Required by bench_mul.js: it inspects both object files to locate mul_q4.
subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','firmware.o'],cwd=root/'chego',check=True)
subprocess.run(['node','verify_samples.js'],cwd=root,check=True)
subprocess.run(['node','bench_mul.js'],cwd=root,check=True,stdout=(root/'benchmark.json').open('w'))
print('4096 exhaustive multiply input combinations checked in benchmark.json')

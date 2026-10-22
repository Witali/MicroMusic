#!/usr/bin/env python3
"""Reassemble 3 ATtiny13A MiniLPC-HQ3 firmwares and check bit-exact playback.

Dependencies: clang with AVR backend, llvm-objcopy, readelf, node.
The verified voice parameters live in <name>/speech.hq and are not re-trained here.
"""
from pathlib import Path
import subprocess, hashlib
root=Path(__file__).resolve().parent
for name in ['chego','otvechaesh','vinni']:
 d=root/name
 def run(*args): return subprocess.run(args,cwd=d,check=True,capture_output=True,text=True).stdout
 run('clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','firmware.o')
 run('llvm-objcopy','-O','binary','firmware.o','rebuild.bin')
 run('llvm-objcopy','-O','ihex','firmware.o','rebuild.hex')
 syms=run('readelf','-s','firmware.o')
 line=next(t for t in syms.splitlines() if t.strip().endswith(' code_end'))
 code=int(line.split()[1],16)
 assert code==388,(name,'code bytes',code)
 b=(d/'rebuild.bin').read_bytes();expected=(d/'firmware.bin').read_bytes()
 assert b==expected,(name,'not reproducible')
 assert len(b)<=1024,(name,'flash overflow',len(b))
 assert len(b)==code+len((d/'speech.hq').read_bytes())+1
 print(name,'code',code,'flash',len(b),'sha256',hashlib.sha256(b).hexdigest())
 for p in ('rebuild.bin','rebuild.hex','firmware.o'): (d/p).unlink()
subprocess.run(['node','verify.js'],cwd=root,check=True)
print('Reassembly, PCM playback and Timer0 cycle tests PASS.')

#!/usr/bin/env python3
"""Self-contained reconstruction using clang/LLVM AVR toolchain.
Run from project folder: python3 rebuild.py
"""
import pathlib,subprocess,hashlib,json
ROOT=pathlib.Path(__file__).parent.resolve()
expected=json.loads((ROOT/'manifest.json').read_text())
for name,entry in expected.items():
 d=ROOT/'examples'/name
 subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','recompiled.o'],cwd=d,check=True)
 subprocess.run(['llvm-objcopy','-O','binary','recompiled.o','recompiled.bin'],cwd=d,check=True)
 b=(d/'recompiled.bin').read_bytes()
 assert hashlib.sha256(b).hexdigest()==entry['bin_sha256'],f'Firmware mismatch: {name}'
 print(f'{name}: OK, {len(b)} bytes, {entry["code_bytes"]} bytes decoder')
 print('  identical SHA256 to distributed firmware.bin')
print('All six binaries built identically')

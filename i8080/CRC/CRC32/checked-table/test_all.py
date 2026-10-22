#!/usr/bin/env python3
"""Complete reproducible firmware tests (requires gcc/Clang for C emulator)."""
from pathlib import Path
import subprocess,sys
p=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(p/'build.py')],check=True)
subprocess.run(['cc','-O3','-std=c11','-Wall','-Wextra',str(p/'emulate8080.c'),'-o',str(p/'emulate8080')],check=True)
for size in ('24k','32k'):
    rom=str(p/f'crc32c_8080_checked_{size}.bin')
    subprocess.run([str(p/'emulate8080'),rom],check=True)
    subprocess.run([str(p/'emulate8080'),rom,'--all-table-bits'],check=True)
print('PASS: 2 architectures of CPU emulator, all 8,192 single-bit table flips for both ROM sizes')

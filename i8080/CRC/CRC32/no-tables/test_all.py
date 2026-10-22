#!/usr/bin/env python3
"""Build and test ROM integrity checkers with a second emulator (C source)."""
from pathlib import Path
from intel8080_tools import crc_raw
from patch_rom import patch
import subprocess, re, random, shutil, tempfile, sys
from generate import create
from experiment_cached import *   # generates cachedB files (top-level)
P=Path(__file__).resolve().parent

v=[(n, s, u, e) for s in (24576,32768) for u in (1,2,4,8) for e in ('halt','spin') for n in [f'crc32c_8080_{s//1024}k_u{u}_{e}']]
for size in (24576,32768):
    v.append((f'crc32c_8080_{size//1024}k_cachedB',size,1,'halt'))

assert shutil.which('gcc'), 'Need GCC for fast full-ROM CPU tests'
subprocess.run(['gcc','-O3','-std=c11','-Wall','-Wextra','-Werror',str(P/'emulate8080.c'),'-o',str(P/'emulate8080')],check=True)
subprocess.run([sys.executable,str(P/'golden_8080.py')],check=True)
results=[]
for name,size,u,mode in v:
    if 'cached' not in name:
        create(size,u,mode)
    rom=(P/(name+'.bin')).read_bytes()
    assert len(rom)==size and crc_raw(rom)==0
    ret=subprocess.run([str(P/'emulate8080'),str(P/(name+'.bin'))],capture_output=True,text=True)
    assert ret.returncode==0, (name,ret.stdout,ret.stderr)
    assert 'INTE=1' in ret.stdout and 'CRCregs=00000000' in ret.stdout and f'SP={size:04X}' in ret.stdout
    mc=re.search(r'cycles=(\d+)',ret.stdout)
    assert mc,ret.stdout
    cycles=int(mc.group(1))
    # Independent single-bit flips in data and in CRC field (not executable code)
    for idx in [512,1091,size//2,size-4,size-1]:
        bit=8*idx+(idx%8)
        corrupt=subprocess.run([str(P/'emulate8080'),str(P/(name+'.bin')),str(bit)],capture_output=True,text=True)
        assert corrupt.returncode==0,(name,idx,corrupt.stdout,corrupt.stderr)
        assert 'INTE=0' in corrupt.stdout,(name,idx,corrupt.stdout)
    results.append((name,cycles))
print('GOOD + 5 BAD full-ROM tests for',len(results),'variants: PASS')

# Introduce arbitrary payload changes; patch trailer and verify on 8080 instruction emulator.
R=random.Random(808032)
for size in (24576,32768):
    src=(P/f'crc32c_8080_{size//1024}k_u1_halt.bin').read_bytes()
    for i in range(5):
        v=bytearray(src)
        for j in range(512, size-4):
            v[j]=R.randrange(256)
        v=patch(v)
        assert crc_raw(v)==0
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'rom.bin';p.write_bytes(v)
            ret=subprocess.run([str(P/'emulate8080'),str(p)],capture_output=True,text=True)
            assert ret.returncode==0,(size,i,ret.stdout,ret.stderr)
print('10 full-ROM randomized contents + trailer patch + 8080 emulation: PASS')
for name,cyc in results:
    if name.endswith(('u1_halt','u2_halt','u4_halt','u8_halt','cachedB')):
        print(name,cyc, f'{cyc/3_500_000:.6f}s')

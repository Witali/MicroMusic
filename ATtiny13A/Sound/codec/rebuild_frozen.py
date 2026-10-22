#!/usr/bin/env python3
"""Rebuild the exact released MiniLPC-HQ4 HEX from frozen parameters."""
from pathlib import Path
import subprocess,hashlib,sys
import numpy as np
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R))
from refine_and_build import pack
NAMES=['chego','otvechaesh','vinni']
for n in NAMES:
    folder=R/'HQ4'/n;z=np.load(folder/'parameters.npz')
    encoded=pack(z['frames'],z['durations'])
    assert encoded==(folder/'speech.hq').read_bytes(),n
    subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','rebuild.o'],cwd=folder,check=True)
    subprocess.run(['llvm-objcopy','-O','binary','rebuild.o','rebuild.bin'],cwd=folder,check=True)
    original=(folder/'firmware.bin').read_bytes();rebuilt=(folder/'rebuild.bin').read_bytes()
    assert original==rebuilt,n
    print(n,len(rebuilt),'bytes, SHA256',hashlib.sha256(rebuilt).hexdigest())
    (folder/'rebuild.bin').unlink();(folder/'rebuild.o').unlink()
subprocess.run(['node','verify_hq4.js'],cwd=R,check=True)
print('All three exact builds verified')

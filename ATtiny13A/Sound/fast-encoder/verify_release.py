#!/usr/bin/env python3
"""Verify that produced HEX images are reproducible and under 1024-byte cap."""
import hashlib,json,subprocess
from pathlib import Path
BASE=Path(__file__).resolve().parent
for case in ('chego','otvechaesh','vinni','chego_balanced'):
    folder=BASE/'final'/case
    expected=(folder/'firmware.bin').read_bytes()
    h=hashlib.sha256(expected).hexdigest()
    info=json.loads((folder/'result.json').read_text())
    assert info['sha256']==h,(case,'SHA mismatch')
    assert len(expected)<=1024,(case,len(expected))
    subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','firmware.verify.o'],cwd=folder,check=True,capture_output=True)
    subprocess.run(['llvm-objcopy','-O','binary','firmware.verify.o','firmware.verify.bin'],cwd=folder,check=True,capture_output=True)
    got=(folder/'firmware.verify.bin').read_bytes()
    assert got==expected,(case,'AVR recompilation changed bytes')
    (folder/'firmware.verify.o').unlink();(folder/'firmware.verify.bin').unlink()
    print(case,'OK,',len(expected),'Flash bytes, SHA-256',h)
print('All four images bit-identical on rebuild.')

#!/usr/bin/env python3
import math, struct
from pathlib import Path
p=Path(__file__).resolve().parent
# Codec2 3200 pitch quantizer is linear in Wo/f0: about 50..400 Hz, 128 levels.
pitch=[]
for i in range(128):
    f=50.0 + (350.0/128.0)*i
    pitch.append(max(1,min(255,round(f/12.5))))
(p/'pitch.tbl').write_bytes(bytes(pitch))
# Nonlinear 0..15 AY volume mapping for 5-bit energy index.
energy=[]
for i in range(32):
    # Slightly expanded low end, monotonic, 0..15
    v=round(15.0*((i/31.0)**1.45)) if i else 0
    energy.append(max(0,min(15,v)))
(p/'energy.tbl').write_bytes(bytes(energy))
# Standard Spectrum 128 AY clock is commonly CPU/2 ~1.7734 MHz.
# AY square-wave tone frequency = clock/(16*period).
AY=1773400.0
raw=bytearray()
for u in range(256):
    f=max(12.5, u*12.5)
    per=round(AY/(16.0*f))
    per=max(1,min(4095,per))
    raw += struct.pack('<H',per)
(p/'ayperiod.tbl').write_bytes(raw)
print('pitch',len(pitch),'energy',len(energy),'period',len(raw))

#!/usr/bin/env python3
"""Reproduce TinyLPC AVR speech byte stream tuned to the user's actual recording.
Bitstream: 5 bytes/frame, K0..K6 4 bit; pitch 8 bit; gain 4 bit.
The coefficients are chosen offline for a Q4 (>>4) lattice, not Q3.
Run optimize_formants.py to recompute tuned parameters on user's WAV.
"""
from pathlib import Path
import numpy as np
P=Path(__file__).resolve().parent
z=np.load(P/'v3_formant_best.npz')
K,pitch,energy=z['K'],z['pitch'],z['energy']
assert K.shape[1]==7 and len(K)==len(pitch)==len(energy)
out=bytearray()
for i in range(len(pitch)):
 k=list(map(int,K[i]));amp=int(energy[i]);pi=int(pitch[i])
 assert 0<=pi<=254 and 0<=amp<=15 and all(-7<=q<=7 for q in k)
 out.extend([pi,(amp&15)|((k[0]+8)<<4),((k[2]+8)<<4)|(k[1]+8),((k[4]+8)<<4)|(k[3]+8),((k[6]+8)<<4)|(k[5]+8)])
(P/'voice_tinylpc.bin').write_bytes(out)
print('frames',len(pitch),'speech bytes',len(out),'duration sec',len(pitch)*256/7500)

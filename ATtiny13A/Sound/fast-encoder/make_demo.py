#!/usr/bin/env python3
"""Generate a copyright-free synthetic MiniLPC training recording and stream."""
from pathlib import Path
import ctypes
import numpy as np
import soundfile as sf
from fast_train import HERE,pack_stream

base=HERE/'examples'/'demo';base.mkdir(parents=True,exist_ok=True)
frames=[];d=[]
# No movie or speech samples: deliberately synthesized with HQ3 lattice.
for i in range(36):
    pitch=24+(i//5)%5*2 if i%11!=8 else 0
    gain=(5+(i//7)%5)
    mode=i%4
    k=[2+(i//8)%2,-3,3,-2,1,0,0,0]
    packed=[((k[j]+8)&15)|(((k[j+1]+8)&15)<<4) for j in (0,2,4,6)]
    frames.append([pitch,(mode<<4)|gain,*packed]);d.append(256)
f=np.array(frames,dtype=np.uint8);d=np.array(d,dtype=np.uint16)
lib=ctypes.CDLL(str(HERE/'libmicrolpc.so'))
lib.mlpc_decode.restype=ctypes.c_int
lib.mlpc_decode.argtypes=[ctypes.POINTER(ctypes.c_uint8),ctypes.POINTER(ctypes.c_uint16),ctypes.c_int,ctypes.POINTER(ctypes.c_uint8),ctypes.c_int]
pcm=np.zeros(int(d.sum()),dtype=np.uint8)
n=lib.mlpc_decode(f.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),d.ctypes.data_as(ctypes.POINTER(ctypes.c_uint16)),len(f),pcm.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),len(pcm))
assert n==len(pcm)
sf.write(base/'original.wav',(pcm.astype(np.float64)-128)/128,7500,subtype='PCM_16')
# Start with a deliberately perturbed pitch and gain.
baseline=f.copy()
for i in range(len(baseline)):
    if baseline[i,0] and i%3==0:baseline[i,0]+=2
    if i%4==0:baseline[i,1]=(baseline[i,1]&0xf0)|max(0,(baseline[i,1]&15)-2)
(base/'speech.hq').write_bytes(pack_stream(baseline,d))
(base/'firmware.S').write_bytes((HERE/'decoder_template.S').read_bytes())
print('Generated:',base/'original.wav',base/'speech.hq')

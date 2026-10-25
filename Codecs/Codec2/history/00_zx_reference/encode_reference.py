#!/usr/bin/env python3
"""Encode 8 kHz mono PCM WAV with the installed reference libcodec2 mode 3200."""
import ctypes, wave, struct, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
lib=ctypes.CDLL('/lib/x86_64-linux-gnu/libcodec2.so.1.2')
lib.codec2_create.argtypes=[ctypes.c_int]
lib.codec2_create.restype=ctypes.c_void_p
lib.codec2_destroy.argtypes=[ctypes.c_void_p]
lib.codec2_samples_per_frame.argtypes=[ctypes.c_void_p]
lib.codec2_samples_per_frame.restype=ctypes.c_int
lib.codec2_bits_per_frame.argtypes=[ctypes.c_void_p]
lib.codec2_bits_per_frame.restype=ctypes.c_int
lib.codec2_encode.argtypes=[ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte), ctypes.POINTER(ctypes.c_short)]

inp=Path(sys.argv[1]) if len(sys.argv)>1 else HERE/'speech8.wav'
out=Path(sys.argv[2]) if len(sys.argv)>2 else HERE/'speech.c2zx'

with wave.open(str(inp),'rb') as w:
    assert w.getnchannels()==1 and w.getsampwidth()==2 and w.getframerate()==8000
    raw=w.readframes(w.getnframes())
samps=list(struct.unpack('<%dh'%(len(raw)//2),raw))

c2=lib.codec2_create(0) # CODEC2_MODE_3200
if not c2: raise SystemExit('codec2_create(3200) failed')
ns=lib.codec2_samples_per_frame(c2)
bits=lib.codec2_bits_per_frame(c2)
assert ns==160 and bits==64, (ns,bits)
nb=(bits+7)//8
frames=(len(samps)+ns-1)//ns
samps += [0]*(frames*ns-len(samps))
encoded=bytearray()
inbuf=(ctypes.c_short*ns)()
outbuf=(ctypes.c_ubyte*nb)()
for fi in range(frames):
    fr=samps[fi*ns:(fi+1)*ns]
    for i,v in enumerate(fr): inbuf[i]=v
    lib.codec2_encode(c2,outbuf,inbuf)
    encoded.extend(bytes(outbuf))
lib.codec2_destroy(c2)
out.write_bytes(encoded)
print(f'reference Codec2 3200: {frames} frames, {len(encoded)} bytes, {frames*0.02:.2f}s, {bits} bits/frame')
print('first frames:', [encoded[i:i+8].hex() for i in range(0,min(40,len(encoded)),8)])

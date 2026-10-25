#!/usr/bin/env python3
"""Check delta LSP codebook formulas against official native libcodec2."""
import sys,math,ctypes,ctypes.util
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from test_codec2tiny import fields
r=Path(__file__).resolve().parents[1]
L=ctypes.CDLL(ctypes.util.find_library('codec2'))
L.decode_lspds_scalar.argtypes=[ctypes.POINTER(ctypes.c_float),ctypes.POINTER(ctypes.c_int),ctypes.c_int]
maxerr=0;points=0
for filename in ['speech.c2zx','codec2_3200_8byte_frames.bin']:
    data=(r/'tests'/filename).read_bytes()
    for off in range(0,len(data),8):
        d=fields(data[off:off+8]);pos=0
        out=(ctypes.c_float*10)()
        L.decode_lspds_scalar(out,(ctypes.c_int*10)(*d[4]),10)
        for j,idx in enumerate(d[4]):
            pos+=idx+1 if j not in (3,4,5) or idx<8 else 2*idx-6
            diff=abs(out[j]*4000/math.pi-25*pos)
            maxerr=max(maxerr,diff);points+=1
assert maxerr<0.001
print('PASS: %d LSP codebook entries, max error %.7f Hz'%(points,maxerr))

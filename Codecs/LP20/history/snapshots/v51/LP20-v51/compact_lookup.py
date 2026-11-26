#!/usr/bin/env python3
"""Exact packed data layouts, not a Z80 timing claim."""
from pathlib import Path
import numpy as np
import json
from grid51 import grid,pack_grid
from study50 import lut,W
ROOT=Path(__file__).resolve().parent
p=grid();pack_grid(p,ROOT/'pwm255.bin');a=lut(p).reshape(256,4)
b=a[:,0].astype(np.uint8);d=a-a[:,:1];assert d.min()==0 and d.max()<=3
# Low 2 bits describe frac=1, next 2 frac=2, next 2 frac=3; frac=0 -> 0.
# Use the same signed high-byte addressing as the legacy Z80 PCM.
order=np.r_[128:256,0:128];delta=(d[:,1]|d[:,2]<<2|d[:,3]<<4).astype(np.uint8)
payload=b[order].tobytes()+delta[order].tobytes();(ROOT/'pcm-to-pwm255.bin').write_bytes(payload)
for x in range(-512,512):
 hi=(x//4)&255;fr=x%4;actual=payload[hi]+(0 if fr==0 else ((payload[256+hi]>>(2*(fr-1)))&3));assert actual==a.ravel()[x+512]
# Symmetric table: negative level k = complement of positive level 254-k.
assert np.array_equal(p[::-1],320-p)
# Centre template is self-complementary sample-by-sample in this grid.
assert np.all(p[127]==160)
pack_grid(p[127:],ROOT/'pwm255-half.bin')
raw=np.frombuffer((ROOT/'pwm255-half.bin').read_bytes(),np.uint8).reshape(-1,4);ix=np.empty((128,8),np.uint8);ix[:,::2]=raw>>4;ix[:,1::2]=raw&15;w=np.array(W);q=w[ix];rec=np.concatenate([320-q[:0:-1],q]);assert np.array_equal(rec,p)
result=dict(full_pattern_bytes=1020,symmetric_pattern_bytes=512,pcm_map_bytes=len(payload),full_total_bytes=1020+len(payload),symmetric_total_bytes=512+len(payload),max_index_jump_per_quartet=int(d.max()),verified_pcm_codes=1024,verified_patterns=len(p),runtime='not tested')
(ROOT/'packing.json').write_text(json.dumps(result,indent=2));print(result)

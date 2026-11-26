import os,sys
from pathlib import Path
B=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(B/'LP20_v37'))
from reuse_macros import builder, np
import share_tails as st
from collections import Counter
import json
m=json.load(open(B/'LP20_v37/release/first/Strict8/decoder.json'))
for c in ['first','second']:
 p=B/'LP20_v37/release'/c/'Strict8';d=np.load(p/'model.npz'); meta=json.load(open(p/'decoder.json')); r=np.concatenate([d['records'],d['ext_records']]); l=np.r_[d['lengths'],d['ext_lengths']]; plan=d['plan']; pairs=set(tuple(x) for rr,n in zip(r,l) for x in rr[:n]);print(c,'pairs',len(pairs),'short',d['shortmax'],'used levels',len(set(np.load(p/'decoder.widths10.npy'))),'bytes',meta['stream_bytes']);

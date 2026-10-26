#!/usr/bin/env python3
"""Build a freely usable periodic speech-like excitation test with CELP sparse modes."""
import random,struct,json
from pathlib import Path
from rice_v3 import BitWriter
from l3av_parse import unpack
from lpx4 import encode,decode
ROOT=Path(__file__).resolve().parent.parent
out=ROOT/'examples/SYNTHETIC_CELP_BUDGET';out.mkdir(parents=True,exist_ok=True)
random.seed(20261023)
n=3200
seq=[]
for i in range(n):
    if i<160:
        v=random.choices([-4,-3,-2,-1,0,1,2,3,4],[1,2,3,4,7,4,3,2,1])[0]
    else:
        v=seq[i-40]
        if (i%40) in (7,29):v=max(-8,min(7,v+random.choice([-2,-1,1,2])))
    seq.append(v)
lsf=[100+80*i for i in range(10)]
assert max(lsf)<1024
hdr=bytearray(struct.pack('<4sBBHIHHHH',b'L3AV',1,3,8000,n,2000,1000,160,80))
buf=bytearray(hdr)
for frame in range((n+159)//160):
    if frame==0:
        buf.append(5)
        buf.extend(sum(x<<(10*i) for i,x in enumerate(lsf)).to_bytes(13,'little'))
    else:buf.append(0)
    for block in range(2):
        start=frame*160+block*80
        buf.extend((4,38))
        w=BitWriter()
        for v in seq[start:start+80]:w.put(v+8,4)
        w.aligned();buf.extend(w.get())
src=bytes(buf);doc=unpack(src)
packed,stats,chunks,qs=encode(doc,min_snr=15)
assert qs==decode(packed)[2]
assert any(c['mode']=='sparse' for c in chunks),stats
(out/'synthetic_celp_v1.l3av').write_bytes(src)
(out/'synthetic_celp_budget.l4hy').write_bytes(packed)
with (out/'voice_data.h').open('w') as f:
    f.write('#pragma once\n#include <stdint.h>\n#include <avr/pgmspace.h>\n')
    f.write('const uint8_t g_voice_l4hy[] PROGMEM = {\n')
    for i in range(0,len(packed),16):f.write('  '+', '.join(str(x) for x in packed[i:i+16])+',\n')
    f.write('};\nconst uint16_t g_voice_l4hy_size = sizeof(g_voice_l4hy);\n')
(out/'synthetic_report.json').write_text(json.dumps({'v1':len(src),'l4hy':len(packed),'modes':stats,'sparse_chunks':[{'pos':c['position'],'pulses':c['pulses']} for c in chunks if c['mode']=='sparse']},indent=2)+'\n')
print('SYNTHETIC',len(src),len(packed),'SPARSE',stats.get('sparse',0))

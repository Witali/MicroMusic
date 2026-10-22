#!/usr/bin/env python3
"""Convert actual MicroMusic PIC C-port assets to PIC program-memory data words.
A DW value is one 14-bit Flash word; indirect FSR reads its low 8 bits.
"""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
src=root/'source'/'music-assets.json'
a=json.loads(src.read_text(encoding='utf8'))
SAMPLE_RATE=12500
SCALE_NUM=15625
SCALE_DEN=SAMPLE_RATE
assert len(a['violin'])==32 and len(a['piano'])==128 and len(a['guitar'])==128

def emit(path,content):path.write_text(content,encoding='utf8')
wave='; FSR accesses low byte of each 14-bit Flash word; two signed 4-bit samples / DW.\nORG 0x0600\nwave_table:\n'
for inst in ('violin','piano','guitar'):
    x=a[inst]
    assert len(x)%16==0
    assert all(-8<=v<=7 for v in x)
    packed=[((x[i]+8)&15)|(((x[i+1]+8)&15)<<4) for i in range(0,len(x),2)]
    wave+=inst+'_wave:\n'
    for i in range(0,len(packed),12):wave+='    DW '+', '.join(f'0x{v:02X}' for v in packed[i:i+12])+'\n'
assert len(packed)==64
wave+='\n'
emit(root/'firmware'/'wave_tables.inc',wave)

# Signed 4-bit oscillator * 4-bit envelope with arithmetic /4.
# PIC has no multiplier; one Flash lookup is much faster than 4 additions.
gain='; 256-word exact signed (sample * envelope) >> 2 lookup, FSR1H=0x84.\nORG 0x0400\ngain_table:\n'
for sample in range(-8,8):
    values=[((sample*env)>>2)&255 for env in range(16)]
    gain+='    DW '+', '.join(f'0x{v:02X}' for v in values)+'\n'
emit(root/'firmware'/'gain_tables.inc',gain)
assert len(a['score'])==216 and len(a['playlist'])==15
music='; Programme-space constants: 16-bit DDS steps scaled from source 15625 Hz to target 12500 Hz.\nORG 0x0690\nnote_table:\n'
for v0 in a['noteSteps']:
    v=(v0*SCALE_NUM + SCALE_DEN//2)//SCALE_DEN
    music+=f'    DW 0x{v&255:02X},0x{v>>8:02X}\n'
music+='chord_table:\n'
for k,p in zip(a['chordsKey'],a['chordsPluck']):
    k=(k*SCALE_NUM + SCALE_DEN//2)//SCALE_DEN
    p=(p*SCALE_NUM + SCALE_DEN//2)//SCALE_DEN
    music+=f'    DW 0x{k&255:02X},0x{k>>8:02X},0x{p&255:02X},0x{p>>8:02X}\n'
music+='duration_table:\n    DW '+','.join(str(x) for x in a['durations'])+'\n'
music+='playlist_table:\n    DW '+','.join(f'0x{v:02X}' for v in a['playlist'])+'\n'
music+='\nORG 0x0700\nscore_table:\n'
for i in range(0,len(a['score']),14):music+='    DW '+', '.join(f'0x{v:02X}' for v in a['score'][i:i+14])+'\n'
emit(root/'firmware'/'music_tables.inc',music)
print('PIC wave tables:',(len(a['violin'])+len(a['piano'])+len(a['guitar']))//2,'words; scores',len(a['score']),'words.')

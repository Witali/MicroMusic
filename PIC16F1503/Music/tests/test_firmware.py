#!/usr/bin/env python3
"""Static ROM data and timing invariants, independent of the PIC interpreter."""
import json,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
a=json.loads((root/'source/music-assets.json').read_text())
report=json.loads((root/'reports/assembly.json').read_text())
assert report['occupied_words'] <= 2048
assert report['code_words'] < 0x400
assert report['sections']['wave_table']==0x600
assert report['sections']['score_table']==0x700
assert report['config1_hex']=='0x3FC4'
assert report['config2_hex']=='0x3FFF'
assert report['pwm_carrier_hz']==62500 and report['audio_rate_hz']==12500
assert len(a['violin'])==32 and len(a['piano'])==128 and len(a['guitar'])==128
for inst in ('violin','piano','guitar'):
    v=a[inst]
    for j in range(0,len(v),16):
        seg=v[j:j+16]
        assert sum(seg)==0,(inst,j,sum(seg))
        assert max(seg)<=7 and min(seg)>=-8
assert len(a['playlist'])==15 and len(a['score'])==216
assert all(0<=n<216 for n in a['playlist'])
assert len(a['noteSteps'])==13 and len(a['chordsKey'])==5
freq=[]
for k,raw in enumerate(a['noteSteps']):
    step=(raw*15625+6250)//12500
    actual=step*12500/65536
    wanted=raw*15625/65536
    assert abs(actual-wanted)<.1
    freq.append(actual)
assert len(freq)==13
# For the original 80 BPM tune, 250 grid ticks/s and inc=1398 fit 0.1875 s.
seconds_grid=65536/(1398*250)
assert abs(seconds_grid-0.1875)<0.0001,seconds_grid
hexlines=(root/'firmware/micromusic_with_config.hex').read_text().splitlines()
for line in hexlines:
    b=bytes.fromhex(line[1:]); assert len(b)==b[0]+5 and sum(b)%256==0
assert hexlines[-1]==':00000001FF'
rep={'pass':True,'waveforms':18,'waveSamples':288,'scoreBytes':216,'playlistItems':15,
     'frequencyRangeHz':[freq[0],freq[-1]],'gridSeconds':seconds_grid,
     'flashOccupiedWords':report['occupied_words'],'hexRecords':len(hexlines)}
(root/'reports/static_tests.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(rep,ensure_ascii=False,indent=2))

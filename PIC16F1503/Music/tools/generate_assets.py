#!/usr/bin/env python3
"""Port exact packed score and waveforms from Witali/MicroMusic rhythmic snapshot.
No MIDI binaries or SoundFont are distributed.
"""
import json, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'source'; OUT=ROOT/'firmware'
# Encoded byte-for-byte from ATtiny13A/Music/variants/rhythmic/score.inc (main on 2026-10-21).
SECTION_HEX={
  '000':'''e0 19 39 61 40 50 e1 11 39 5b e2 01 31 51 40 50 e3 09 31 5b e0 2d e1 1b 2a 20 e2 34 29 e3 3d e0 2b 33 e1 3b 33 ff''',
  '002':'''e0 2b 19 41 e1 71 39 39 40 38 e2 33 29 31 e3 31 41 39 31 e0 29 18 20 29 39 e1 31 29 31 41 e2 73 39 31 e3 3d e0 39 39 39 30 28 e1 39 39 39 30 28 e2 3b 42 38 ff''',
  '004':'''e0 53 4a 40 e1 3c 31 e2 2c 19 e3 34 29 e0 19 21 29 31 e1 3c 30 28 e2 44 39 e3 35 ff''',
  '006':'''e0 3b 6b e1 33 6b e2 2b 6b e3 23 6b e1 2b 6b e2 33 6b e4 43 6b e3 3b 6b e0 3c 49 e1 44 41 e2 49 41 41 39 e3 35 e0 33 3b e1 3b 43 e2 4b 41 39 e3 45''',
  '005':'''e0 39 39 39 30 28 e1 39 39 39 30 28 e2 44 39''',
  '003':'''e3 35 e0 39 39 39 30 28 e1 3b 39 40 38''',
  '001':'''e2 33 2a 30 e3 25 ff''',
  '007':'''f6 6d 6d 6d f4 6d 6d f2 6d 6d f8 6d ff''',
}
PLAYLIST=[0x00,0xC4,0x26,0xB7,0x5B,0xA8,0xA8,0x77,0xA8,0xCB,0xCB,0x77,0xA8,0xCB,0xCB]
DURATIONS=[1,2,3,4,6,8,16]
AVR_NOTES=[0x240,0x287,0x2ad,0x35f,0x3c9,0x402,0x480,0x50d,0x55a,0x602,0x6be,0x792,0x805]
AVR_CHORDS=[(0x35f,0x287),(0x2ad,0x201),(0x240,0x1b0),(0x287,0x1e4),(0x1e4,0x16b)]
# PIC sample clock 15625 Hz vs AVR 18750 Hz => increment * 6/5.
# Do rounding with integer math, no platform-dependent floating-point.
def scale_step(s): return (6*s+2)//5

def cdecl(name, values, typ='uint8_t', split=16):
    data=', '.join(str(v) for v in values)
    return f'static const {typ} {name}[{len(values)}] = {{\n    '+',\n    '.join(', '.join(str(v) for v in values[i:i+split]) for i in range(0,len(values),split))+'\n};\n'

def main():
    sections=[]; offsets={}; pos=0
    for n in SECTION_HEX:
        offsets[n]=pos
        b=bytes.fromhex(SECTION_HEX[n]); sections+=list(b);pos+=len(b)
    assert offsets=={'000':0,'002':38,'004':91,'006':119,'005':168,'003':183,'001':196,'007':203},offsets
    assert all(p in offsets.values() for p in PLAYLIST)
    assert sections[0]==0xe0 and sections[-1]==0xff
    assert len(sections)==216, len(sections)
    waves=json.loads((SRC/'waveforms.json').read_text())['waves']
    for name, w in waves.items(): assert len(w)==16 and sum(w)==0 and min(w)>=-8 and max(w)<=7,(name,w)
    # PIC has more program memory than ATtiny13A; precompute spectral crossfades.
    # This removes per-sample multiplication from the real-time audio path.
    def qdiv(n,den):
        return (n+den//2)//den if n>=0 else -((-n+den//2)//den)
    vln=[];pno=[];gtr=[]
    for reg in ('low','high'): vln.extend(waves[f'violin_{reg}'])
    for kind,dest in (('piano',pno),('guitar',gtr)):
        for reg in ('low','high'):
            sustain=waves[f'{kind}_{reg}_sustain'];attack=waves[f'{kind}_attack']
            for frame in range(4):
                wave=[qdiv((3-frame)*a+frame*b,3) for a,b in zip(attack,sustain)]
                # Keep the mean *exactly* at zero after 4-stage quantization.
                delta=sum(wave)
                # Spread rounding residual among samples nearest zero with headroom.
                for i in sorted(range(16),key=lambda j:abs(wave[j])):
                    if not delta:break
                    if delta>0 and wave[i]>-8:wave[i]-=1;delta-=1
                    elif delta<0 and wave[i]<7:wave[i]+=1;delta+=1
                assert sum(wave)==0 and min(wave)>=-8 and max(wave)<=7,(kind,reg,frame,wave)
                dest.extend(wave)
    txt='''/* AUTO-GENERATED. tools/generate_assets.py, source Witali/MicroMusic.\n * Flash tables are const in PIC XC8 program memory; no EEPROM dependency.\n * Tone table index: instrument (violin=0, piano=1, guitar=2), register (low=0,high=1), attack(0)/sustain(1), phase 0..15.\n * Each waveform has zero DC mean.\n */\n#ifndef MICROMUSIC_DATA_H\n#define MICROMUSIC_DATA_H\n#include <stdint.h>\n'''
    txt+=cdecl('mm_violin',vln,typ='int8_t')
    txt+=cdecl('mm_piano',pno,typ='int8_t')
    txt+=cdecl('mm_guitar',gtr,typ='int8_t')
    txt+=cdecl('mm_playlist',PLAYLIST)
    txt+=cdecl('mm_score',sections)
    txt+=cdecl('mm_durations',DURATIONS)
    txt+=cdecl('mm_note_steps',[scale_step(v) for v in AVR_NOTES],typ='uint16_t',split=9)
    # separate key/pluck chord banks reduce PIC index arithmetic
    txt+=cdecl('mm_chords_key',[scale_step(a) for a,b in AVR_CHORDS],typ='uint16_t')
    txt+=cdecl('mm_chords_pluck',[scale_step(b) for a,b in AVR_CHORDS],typ='uint16_t')
    txt+='''#define MM_VIOLIN_SIZE 32
#define MM_PIANO_SIZE 128
#define MM_GUITAR_SIZE 128
#define MM_SCORE_LEN 216\n#define MM_PLAYLIST_LEN 15\n#define MM_GRID_INC 1432u /* (80 BPM * 4 / 60) * 65536 / (15625/64) */\n#endif\n'''
    (OUT/'music_data.h').write_text(txt)
    meta={'sourceRepo':'https://github.com/Witali/MicroMusic','originalVariant':'rhythmic','sectionOffsets':offsets,'playlist':PLAYLIST,'scoreByteCount':len(sections),'waveforms':8,'mcuWaves':18,'mcuWaveSamples':288,'sampleRate':15625,'pwmRate':62500,'originalDDSRate':18750,'notes':len(AVR_NOTES),'chords':len(AVR_CHORDS)}
    (OUT/'port_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    # Browser's reference synthesis uses EXACTLY the same generated tables as XC8.
    asset={'violin':vln,'piano':pno,'guitar':gtr,'playlist':PLAYLIST,
           'score':sections,'durations':DURATIONS,
           'noteSteps':[scale_step(v) for v in AVR_NOTES],
           'chordsKey':[scale_step(a) for a,b in AVR_CHORDS],
           'chordsPluck':[scale_step(b) for a,b in AVR_CHORDS],
           'gridInc':1432,'source':meta['sourceRepo']}
    (ROOT/'web'/'music-assets.mjs').write_text('/* GENERATED: tools/generate_assets.py */\nexport const MUSIC_ASSETS = '+json.dumps(asset,ensure_ascii=False,separators=(',',':'))+';\n')
    (ROOT/'source'/'music-assets.json').write_text(json.dumps(asset,ensure_ascii=False,indent=2))

    print(json.dumps(meta,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

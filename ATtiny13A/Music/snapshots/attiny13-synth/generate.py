#!/usr/bin/env python3
"""Turn supplied score.json into a tiny one-byte-event music stream.

Only instruments active in this arrangement are emitted as synthesis algorithms:
  --lead violin|flute, --keys piano|organ, --pluck guitar|bass, --drums snare|hat|off.
Repeat sections are stored once; all section offsets must fit in one byte.

The ATtiny13A cannot process arbitrary General MIDI in 1 KB. For .mid inputs,
use midi_to_score.py first to quantize and select the main melody/chords.
"""
import argparse
import json
import math
import re
from pathlib import Path

BEATS = (0.25, 0.5, 0.75, 1., 1.5, 2., 4.)
NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
ROOTS = {'Bm':59, 'Gmaj7':55, 'Em':52, 'F#m':54, 'F#':54,'C#m7b5':49}
KEY_VOICE_OFFSETS = {'piano':0,'organ':0}
BASS_VOICE_OFFSETS = {'guitar':-5, 'bass':-12}

def midi(n):
    if n.upper() == 'R':
        return None
    m = re.fullmatch(r'([A-G])([#b]?)(-?\d+)', n)
    if not m: raise ValueError(f'Invalid note {n}')
    c,a,o=m.groups(); semi=NAMES.index(c) if c in NAMES else None
    semi={'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}[c] + (1 if a=='#' else -1 if a=='b' else 0)
    return (int(o)+1)*12+semi

def pname(n):
    if n is None: return 'R'
    return NAMES[n%12] + str(n//12-1)

def split_durations(beats):
    q=round(beats*4)
    if abs(q-beats*4)>1e-6: raise ValueError(f'Duration {beats} is not a multiple of a 16th note')
    chunks=[]
    while q>0:
        n=next((v for v in reversed(BEATS) if round(4*v)<=q),None)
        chunks.append(n);q-=round(4*n)
    return chunks

def pack_bar(bar,chords,note_index,chord_index):
    tokens=[]
    for piece in bar.split():
        raw,dur=piece.split(':')
        dur=float(dur.rstrip('~'))
        tokens.append((raw,dur))
    if abs(sum(d for _,d in tokens)-4)>1e-6:
        raise ValueError(f'Bar does not sum to four beats: {bar}')
    out=[]
    pos=0.
    chord_boundary=0.
    out.append(0xE0 | chord_index[chords[0]])
    for note,duration in tokens:
        remaining=duration
        while remaining>1e-8:
            if pos>=2-1e-8 and chord_boundary==0:
                out.append(0xE0 | chord_index[chords[1]])
                chord_boundary=2.
            until=min(remaining, (2 if pos<2-1e-8 else 4)-pos)
            if until<1e-8: raise AssertionError((note,pos,duration))
            for frag in split_durations(until):
                pi=note_index[note]
                out.append((pi << 3) | BEATS.index(frag))
            pos=round(pos+until,5)
            remaining=round(remaining-until,5)
    if chord_boundary==0:
        out.append(0xE0 | chord_index[chords[1]])
    return out

def to_inc(data,lead,keys,pluck,drums):
    tempo=data['tempo_bpm']
    # 9.6 MHz / 256 = 37 500 Hz PWM; music clock at 1/512 of audio clock.
    # Durations are rounded to tick count, therefore the maximum tempo error
    # for the shortest event is < one 13.653 ms timer tick.
    ticks=[round(d*60/tempo*37500/512) for d in BEATS]
    if any(not 1 <= t <= 255 for t in ticks): raise ValueError('Unrepresentable tempo')
    sections=list(data['patterns'])
    if len(sections)>16: raise ValueError('Too many unique sections')
    if any(s not in sections for s in data['playlist']):raise ValueError('Unknown section')
    pitches=sorted({n.split(':')[0] for bars in data['patterns'].values() for bar in bars for n in bar.split()},key=lambda n: 1000 if n=='R' else midi(n))
    if len(pitches)>28:raise ValueError('Too many different pitches, use note range quantization')
    note_index={n:i for i,n in enumerate(pitches)}
    # 0xE0..0xEF are chord commands; 0xFF marks end of a section.
    if len(pitches)>28:raise ValueError('No note codes remaining')
    chords=list(dict.fromkeys(c for bars in data['chord_overrides'].values() for b in bars for c in b))
    for p in data['chord_pairs']:
        for c in p:
            if c not in chords:chords.append(c)
    if len(chords)>16:raise ValueError('Too many chord types')
    chord_index={c:i for i,c in enumerate(chords)}
    song_sections={};bars_count=0
    for section,bars in data['patterns'].items():
        events=[]
        for i,bar in enumerate(bars):
            chords_b=data.get('chord_overrides',{}).get(section)
            pair=chords_b[i] if chords_b else data['chord_pairs'][i % len(data['chord_pairs'])]
            events.extend(pack_bar(bar,pair,note_index,chord_index))
            bars_count+=1
        events.append(255)
        song_sections[section]=events
    offsets={};pos=0
    for section,events in song_sections.items():
        offsets[section]=pos
        pos+=len(events)
    if pos>256:raise ValueError(f'Event section offsets need more than one byte: {pos}')
    def delta(n):
        if n is None:return 0
        freq=440.0*2**((n-69)/12)
        x=round(freq*65536/37500)
        if not 0<=x<=65535: raise ValueError(f'{n} note out of range')
        return x
    def table_row(bytes_,comment=''):
        return '  .byte ' + ', '.join(f'0x{x:02x}' for x in bytes_) + (f'   /* {comment} */' if comment else '')
    lines=['/* GENERATED by generate.py. Do not edit by hand. */',
           '.set SAMPLE_CYCLES, 256',f'.set INSTR_LEAD, {1 if lead=="violin" else 2}',
           f'.set INSTR_KEYS, {1 if keys=="piano" else 2}',
           f'.set INSTR_PLUCK, {1 if pluck=="guitar" else 2}',
           f'.set INSTR_DRUMS, {0 if drums=="off" else 1 if drums=="hat" else 2}',
           '', '.balign 2','playlist:']
    playlist=[sections.index(s) for s in data['playlist']]+[255]
    lines.append(table_row(playlist,'15 playback entries + loop marker'))
    lines.append('durations:')
    lines.append(table_row(ticks,f'ticks @ {tempo} BPM, 512 PWM periods/tick'))
    lines.append('note_steps:')
    for p in pitches:
        d=delta(midi(p));lines.append(table_row([d&255,d>>8],f'{p}, {round(d*37500/65536,1)} Hz'))
    lines.append('chord_steps:')
    for ch in chords:
        x=ROOTS[ch];a=delta(x+KEY_VOICE_OFFSETS[keys]);b=delta(x+BASS_VOICE_OFFSETS[pluck])
        lines.append(table_row([a&255,a>>8,b&255,b>>8],f'{ch}: piano {pname(x)}, guitar {pname(x+BASS_VOICE_OFFSETS[pluck])}'))
    lines.append('section_offsets:')
    lines.append(table_row([offsets[s] for s in sections],'byte offsets in melody_data'))
    lines.append('melody_data:')
    for section,events in song_sections.items():
        lines.append(f'section_{section}:')
        for i in range(0,len(events),16):
            lines.append(table_row(events[i:i+16]))
    meta={"note_count":sum(sum(1 for n in sec if n!=255 and n<0xe0) for sec in song_sections.values()),
          "event_bytes":pos,"playlist_bytes":len(playlist),"note_table_bytes":len(pitches)*2,
          "chord_table_bytes":len(chords)*4,"durations":ticks,"pitches":pitches,"chords":chords,
          "total_data_bytes":pos+len(playlist)+len(ticks)+len(pitches)*2+len(chords)*4+len(sections),
          "section_bars":{k:len(v) for k,v in data['patterns'].items()},
          "playlist":data['playlist'],"section_offsets":offsets,"source":data['title'],
          "instruments":{"lead":lead,"keys":keys,"pluck":pluck,"drums":drums}}
    return '\n'.join(lines)+'\n',meta

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('score',nargs='?',default='score.json')
    ap.add_argument('--lead',choices=['violin','flute'],default='violin')
    ap.add_argument('--keys',choices=['piano','organ'],default='piano')
    ap.add_argument('--pluck',choices=['guitar','bass'],default='guitar')
    ap.add_argument('--drums',choices=['off','hat','snare'],default='snare')
    ap.add_argument('-o','--output',default='score.inc')
    args=ap.parse_args()
    text,meta=to_inc(json.loads(Path(args.score).read_text()),args.lead,args.keys,args.pluck,args.drums)
    Path(args.output).write_text(text)
    Path(args.output).with_name("config.inc").write_text("\n".join([line for line in text.splitlines() if line.startswith(".set INSTR_")])+"\n")
    Path(args.output).with_suffix('.meta.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False))
    print(json.dumps(meta,indent=2,ensure_ascii=False))
if __name__=='__main__':main()

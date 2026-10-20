#!/usr/bin/env python3
"""Compile a score onto the firmware's shared sixteenth-note grid.

The firmware has three assigned tonal parts and optional noise percussion.
Repeat sections are stored once; all section offsets must fit in one byte.

The ATtiny13A cannot process arbitrary General MIDI in 1 KB. For .mid inputs,
use midi-reader.py first to select and arrange the main melody/chords.
"""
import argparse
import json
import math
import re
import importlib.util
from pathlib import Path

BEATS = (0.25, 0.5, 0.75, 1., 1.5, 2., 4.)
NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
ROOTS = {'Bm':59, 'Gmaj7':55, 'Em':52, 'F#m':54, 'F#':54,'C#m7b5':49}
KEY_VOICE_OFFSETS = {'piano':0,'organ':0}
BASS_VOICE_OFFSETS = {'guitar':-5, 'bass':-12}
SYNTHESIS_HZ = 18750

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

def pack_bar(bar,chords,note_index,chord_index,hold_index,previous_tie=None,note_off=None):
    tokens=[]
    for piece in bar.split():
        raw,dur=piece.split(':')
        tokens.append((raw,float(dur.rstrip('~')),dur.endswith('~')))
    if abs(sum(d for _,d,_ in tokens)-4)>1e-6:
        raise ValueError(f'Bar does not sum to four beats: {bar}')
    out=[]
    pos=0.
    chord_boundary=0.
    out.append(0xE0 | chord_index[chords[0]])
    holds=[]
    for i,(note,duration,tied) in enumerate(tokens):
        continuing=i==0 and previous_tie==note and note!='R'
        remaining=duration
        while remaining>1e-8:
            if pos>=2-1e-8 and chord_boundary==0:
                out.append((0xF0 | note_off) if note_off is not None else (0xE0 | chord_index[chords[1]]))
                chord_boundary=2.
            until=min(remaining, (2 if pos<2-1e-8 else 4)-pos)
            if until<1e-8: raise AssertionError((note,pos,duration))
            for frag in split_durations(until):
                pi=hold_index if continuing and note!='R' else note_index[note]
                out.append((pi << 3) | BEATS.index(frag))
                if pi==hold_index:holds.append(dict(pitch=note,beat=pos))
                continuing=True
            pos=round(pos+until,5)
            remaining=round(remaining-until,5)
        previous_tie=note if tied else None
    if chord_boundary==0:
        out.append((0xF0 | note_off) if note_off is not None else (0xE0 | chord_index[chords[1]]))
    return out,previous_tie,holds

def to_inc(data,validate_size=True):
    tempo=data['tempo_bpm']
    ticks=[round(d*4) for d in BEATS]
    sections=list(data['patterns'])
    if any(s not in sections for s in data['playlist']):raise ValueError('Unknown section')
    pitches=sorted({n.split(':')[0] for bars in data['patterns'].values() for bar in bars for n in bar.split()}-{'R'},key=midi)+['R']
    if len(pitches)>27:raise ValueError('Need space for both rest and hold codes below 0xE0')
    note_index={n:i for i,n in enumerate(pitches)}
    rest_index=note_index['R'];hold_index=rest_index+1
    # 0xE0..0xEF are chord commands; 0xFF marks end of a section.
    if len(pitches)>28:raise ValueError('No note codes remaining')
    chords=list(dict.fromkeys(c for bars in data.get('chord_overrides',{}).values() for b in bars for c in b))
    for p in data['chord_pairs']:
        for c in p:
            if c not in chords:chords.append(c)
    # Explicit pairs preserve independent instrument parts. Legacy root-only
    # arrangements keep their established octave/fifth mapping.
    note_pairs={}
    for c in chords:
        if c in data.get('chord_notes',{}):
            pair=data['chord_notes'][c]
            if len(pair)!=2:raise ValueError(f'{c}: chord_notes needs keys and pluck notes')
            note_pairs[c]=tuple(midi(n) if isinstance(n,str) else n for n in pair)
        else:
            root=data.get('chord_roots',{}).get(c, ROOTS.get(c))
            if root is None:raise ValueError(f'Unknown root for {c}')
            note_pairs[c]=(root+KEY_VOICE_OFFSETS['piano'],root+BASS_VOICE_OFFSETS['guitar'])
    unique_by_pair={}
    for c in chords:unique_by_pair.setdefault(note_pairs[c],c)
    chord_index={c:list(unique_by_pair).index(note_pairs[c]) for c in chords}
    chords=list(unique_by_pair.values())
    if len(chords)>16:raise ValueError('Too many chord types')
    song_sections={};bars_count=0;holds=[]
    for section,bars in data['patterns'].items():
        events=[];previous_tie=None
        for i,bar in enumerate(bars):
            chords_b=data.get('chord_overrides',{}).get(section)
            pair=chords_b[i] if chords_b else data['chord_pairs'][i % len(data['chord_pairs'])]
            # A sparse ending progressively releases the chord voices, then drums.
            # The four release masks are independent per-voice NOTE-OFF controls:
            # 0x2=piano, 0x4=guitar, 0x8=drums; first event 0x6 releases both.
            outro_release = (6, 4, 2, 8)[i] if (section=='F' and len(bars)==4 and all(b=='R:4' for b in bars)) else None
            packed,previous_tie,bar_holds=pack_bar(bar,pair,note_index,chord_index,hold_index,previous_tie,note_off=outro_release)
            events.extend(packed)
            holds.extend(dict(section=section,bar=i,**h) for h in bar_holds)
            bars_count+=1
        events.append(255)
        song_sections[section]=events
    packing_spec=importlib.util.spec_from_file_location('pack_score',Path(__file__).with_name('pack-score.py'))
    packing=importlib.util.module_from_spec(packing_spec);packing_spec.loader.exec_module(packing)
    chunks=[bytes(song_sections[s][:-1]) for s in data['playlist']]
    packed=packing.pack(b''.join(chunks),chunks,candidate_limit=data.get('packing_candidates',96))
    song_sections=packed['sections'];offsets=packed['offsets'];storage=packed['storage']
    output_playlist=packed['playlist'];pos=len(storage)
    # Only playlist ENTRY offsets are bytes. LPM Z+ advances a full 16-bit
    # pointer, so the last phrase may legitimately continue beyond byte 255.
    max_offset=max(offsets.values(),default=0)
    if validate_size and max_offset>255:raise ValueError(f'Packed phrase entry exceeds one-byte offsets: {max_offset}')
    def delta(n):
        if n is None:return 0
        freq=440.0*2**((n-69)/12)
        x=round(freq*65536/SYNTHESIS_HZ)
        if not 0<=x<=65535: raise ValueError(f'{n} note out of range')
        return x
    def table_row(bytes_,comment=''):
        return '  .byte ' + ', '.join(f'0x{x:02x}' for x in bytes_) + (f'   /* {comment} */' if comment else '')
    lines=['/* GENERATED FROM score.json BY tools/score-format.py. */', 'playlist:']
    playlist=[offsets[s] for s in output_playlist]
    lines.append(table_row(playlist,'direct section byte offsets (no sentinel)'))
    lines.append('durations:')
    lines.append(table_row(ticks,'sixteenth-note grid units'))
    lines.append('note_steps:')
    for p in pitches:
        if p=='R': continue  # rest is handled before note lookup; no step bytes
        d=delta(midi(p));lines.append(table_row([d&255,d>>8],f'{p}, {round(d*SYNTHESIS_HZ/65536,1)} Hz'))
    lines.append('chord_steps:')
    for ch in chords:
        keys_note,pluck_note=note_pairs[ch]
        a=delta(keys_note);b=delta(pluck_note)
        lines.append(table_row([a&255,a>>8,b&255,b>>8],f'{ch}: keys {pname(keys_note)}, pluck {pname(pluck_note)}'))
    lines.append('melody_data:')
    labels_by_offset={}
    for name,offset in offsets.items():labels_by_offset.setdefault(offset,[]).append('section_'+name)
    labels_by_offset.setdefault(playlist[0],[]).append('first_section')
    for i,token in enumerate(storage):
        for label in labels_by_offset.get(i,[]):lines.append(label+':')
        lines.append(table_row([token]))
    meta={"note_count":sum(sum(1 for n in sec if n!=255 and n<0xe0) for sec in song_sections.values()),
          "event_bytes":pos,"maximum_entry_offset":max_offset,"playlist_bytes":len(playlist),"note_table_bytes":sum(p!="R" for p in pitches)*2,
          "chord_table_bytes":len(chords)*4,"durations":ticks,"pitches":pitches,"chords":chords,"chord_notes":{c:note_pairs[c] for c in chords},
          "total_data_bytes":pos+len(playlist)+len(ticks)+sum(p!="R" for p in pitches)*2+len(chords)*4,
          "section_bars":{k:len(v) for k,v in data['patterns'].items()},
          "playlist":output_playlist,"source_playlist":data['playlist'],"section_offsets":offsets,"compression":packed['report'],"source":data['title'],"rest_index":rest_index,"hold_index":hold_index,"holds":holds,
          "instruments":data.get('instruments',{"lead":"violin","keys":"acoustic-grand-piano","pluck":"acoustic-guitar-nylon"})}
    return '\n'.join(lines)+'\n',meta

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('score',nargs='?',default='score.json')
    ap.add_argument('-o','--output',default='score.inc')
    args=ap.parse_args()
    text,meta=to_inc(json.loads(Path(args.score).read_text()))
    Path(args.output).write_text(text)
    Path(args.output).with_suffix('.meta.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False))
    print(json.dumps(meta,indent=2,ensure_ascii=False))
if __name__=='__main__':main()

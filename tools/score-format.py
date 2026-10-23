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

def pack_solo_bar(bar,note_index,hold_index,previous_tie=None):
    """No companion boundary may split a solo note or rest unnecessarily."""
    out=[];holds=[];position=0.
    for i,piece in enumerate(bar.split()):
        note,raw=piece.split(':');duration=float(raw.rstrip('~'))
        continuing=i==0 and previous_tie==note and note!='R'
        for fragment in split_durations(duration):
            index=hold_index if continuing and note!='R' else note_index[note]
            out.append(index<<3|BEATS.index(fragment))
            if index==hold_index:holds.append(dict(pitch=note,beat=position))
            position+=fragment;continuing=True
        previous_tie=note if raw.endswith('~') else None
    if not 0<position<=4:raise ValueError(f'Invalid solo bar length: {bar}')
    return out,previous_tie,holds

def insert_timed_controls(events,controls,chord_index,hold_index,rest_index):
    """Merge offline note-off/companion events without moving melody attacks."""
    by_unit={}
    for control in controls:
        unit=control['unit']
        if type(unit) is not int or unit<0:raise ValueError('Control position must be a nonnegative grid unit')
        if 'chord' in control:token=0xe0|chord_index[control['chord']]
        else:
            mask=control['offMask']
            if type(mask) is not int or not 1<=mask<=14:raise ValueError('Note-off mask must be 1..14')
            token=0xf0|mask
        by_unit.setdefault(unit,[]).append(token)
    out=[];unit=0
    for token in events:
        if token>=0xe0:out.append(token);continue
        remaining=round(BEATS[token&7]*4);pitch=token>>3
        while remaining:
            out.extend(by_unit.pop(unit,[]))
            future=[point for point in by_unit if unit<point<unit+remaining]
            length=min(future)-unit if future else remaining
            for fragment in split_durations(length/4):
                out.append(pitch<<3|BEATS.index(fragment))
                unit+=round(fragment*4)
                if pitch!=rest_index:pitch=hold_index
            remaining-=length
    out.extend(by_unit.pop(unit,[]))
    if by_unit:raise ValueError('Timed control lies beyond its section')
    return out

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
    for controls in data.get('timed_controls',{}).values():
        for control in controls:
            if 'chord' in control and control['chord'] not in chords:chords.append(control['chord'])
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
    def disabled(role):
        assignment=data['instruments'].get(role,'off')
        return assignment=='off' or isinstance(assignment,dict) and (assignment.get('instrument')=='off' or assignment.get('level')==0)
    no_companions='instruments' in data and all(disabled(role) for role in ('keys','pluck'))
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
            if no_companions:
                packed,previous_tie,bar_holds=pack_solo_bar(bar,note_index,hold_index,previous_tie)
            else:
                packed,previous_tie,bar_holds=pack_bar(bar,pair,note_index,chord_index,hold_index,previous_tie,note_off=outro_release)
            if outro_release is not None:
                # Rest bars may release existing voices, never start harmony
                # again. Begin the first release at the start of the outro.
                packed=[token for token in packed if not 0xe0<=token<0xf0]
                if i==0:
                    packed.remove(0xf0|outro_release)
                    packed.insert(0,0xf0|outro_release)
            events.extend(packed)
            holds.extend(dict(section=section,bar=i,**h) for h in bar_holds)
            bars_count+=1
        if section in data.get('replace_harmony_sections',[]):events=[token for token in events if not 0xe0<=token<0xf0]
        if section in data.get('timed_controls',{}):
            events=insert_timed_controls(events,data['timed_controls'][section],chord_index,hold_index,rest_index)
        events.append(255)
        song_sections[section]=events
    if no_companions:chords=[]
    packing_spec=importlib.util.spec_from_file_location('pack_score',Path(__file__).with_name('pack-score.py'))
    packing=importlib.util.module_from_spec(packing_spec);packing_spec.loader.exec_module(packing)
    chunks=[bytes(song_sections[s][:-1]) for s in data['playlist']]
    packed=packing.pack(b''.join(chunks),chunks,candidate_limit=data.get('packing_candidates',96),
                        max_entry_offset=data.get('packing_max_entry_offset'))
    song_sections=packed['sections'];offsets=packed['offsets'];storage=packed['storage']
    output_playlist=packed['playlist'];pos=len(storage)
    # Only playlist ENTRY offsets are bytes. LPM Z+ advances a full 16-bit
    # pointer, so the last phrase may legitimately continue beyond byte 255.
    max_offset=max(offsets.values(),default=0)
    if validate_size and max_offset>255:raise ValueError(f'Packed phrase entry exceeds one-byte offsets: {max_offset}')
    def delta(n,role):
        if n is None:return 0
        freq=440.0*2**((n-69)/12)
        x=round(freq*65536/SYNTHESIS_HZ)
        if not 0<=x<=65535: raise ValueError(f'{n} note out of range')
        threshold=data.get('dds_fast_decay_roles',{}).get(role)
        if threshold is not None:
            if x>=32768:raise ValueError('DDS fast-decay flag needs a frequency below Nyquist')
            if n>=threshold:x|=32768
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
        d=delta(midi(p),'lead');lines.append(table_row([d&255,d>>8],f'{p}, {round((d&32767 if "lead" in data.get("dds_fast_decay_roles",{}) else d)*SYNTHESIS_HZ/65536,1)} Hz'))
    lines.append('chord_steps:')
    for ch in chords:
        keys_note,pluck_note=note_pairs[ch]
        a=delta(keys_note,'keys');b=delta(pluck_note,'pluck')
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

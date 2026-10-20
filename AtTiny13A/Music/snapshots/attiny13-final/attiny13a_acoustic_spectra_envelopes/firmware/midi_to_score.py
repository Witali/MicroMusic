#!/usr/bin/env python3
"""Standard MIDI file -> ATtiny13A 4-voice simplified score.json.

Pure Python, no MIDI library. Reads SMF type 0/1, skips the drum channel when
selecting a melody, quantizes melody to a 1/16-note grid, derives two bass
roots per bar from other MIDI tracks, and folds identical multi-bar blocks.
This is NOT a transparent General MIDI renderer: dense polyphony is reduced
to one melodic line plus generated accompaniment/drums. Default 16 bars keeps
score data near the ATtiny13A's strict 1KB limit. Use --bars to change.
"""
from collections import defaultdict
from pathlib import Path
import argparse
import json
import struct

NOTE_NAMES=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']


def note_name(p):return NOTE_NAMES[p%12]+str(p//12-1)


def vlq(buf,i):
    value=0
    for _ in range(4):
        if i>=len(buf):raise ValueError('Truncated MIDI VLQ')
        b=buf[i];i+=1;value=(value<<7)|(b&127)
        if not b&128:return value,i
    raise ValueError('MIDI VLQ too long')


def read_midi(path):
    b=Path(path).read_bytes()
    if b[:4]!=b'MThd':raise ValueError('Not an SMF MIDI file')
    header_size=struct.unpack_from('>I',b,4)[0]
    fmt,tracks,division=struct.unpack_from('>HHH',b,8)
    if fmt not in (0,1):raise ValueError('Only MIDI format 0 and 1 are supported')
    if division&0x8000:raise ValueError('SMPTE time division is unsupported')
    i=8+header_size
    all_notes=[];tempos=[]
    for track in range(tracks):
        if b[i:i+4]!=b'MTrk':raise ValueError('MTrk chunk missing')
        length=struct.unpack_from('>I',b,i+4)[0];chunk=b[i+8:i+8+length];i+=8+length
        tick=0;j=0;running=None;active=defaultdict(list)
        while j<len(chunk):
            d,j=vlq(chunk,j);tick+=d
            if j>=len(chunk):break
            status=chunk[j]
            if status>=128:j+=1
            else:
                if running is None:raise ValueError('MIDI running status without preceding event')
                status=running
            if status==255:
                typ=chunk[j];j+=1;n,j=vlq(chunk,j);payload=chunk[j:j+n];j+=n
                if typ==0x51 and len(payload)==3:tempos.append((tick,int.from_bytes(payload,'big')))
                running=None
            elif status in (0xf0,0xf7):
                n,j=vlq(chunk,j);j+=n;running=None
            elif 0x80<=status<=0xef:
                running=status;op=status&0xf0;chan=status&15
                size=1 if op in (0xc0,0xd0) else 2
                if j+size>len(chunk):raise ValueError('Truncated MIDI channel event')
                x=chunk[j];y=chunk[j+1] if size==2 else 0;j+=size
                key=(chan,x)
                if op==0x90 and y>0:active[key].append((tick,y))
                if op==0x80 or (op==0x90 and y==0):
                    if active[key]:
                        start,velocity=active[key].pop(0)
                        if tick>start:all_notes.append((track,chan,x,start,tick,velocity))
            else:raise ValueError('Unsupported MIDI status 0x%02x'%status)
        for (chan,pitch),items in active.items():
            for start,velocity in items:
                if tick>start:all_notes.append((track,chan,pitch,start,tick,velocity))
    tempos.sort()
    bpm=round(60_000_000/(tempos[0][1] if tempos else 500000))
    return all_notes,division,bpm


def create_score(notes,ppqn,bpm,max_bars,section_bars,melody_track,bass_track):
    melodic=[n for n in notes if n[1]!=9]
    by_track=defaultdict(list)
    for n in melodic:by_track[n[0]].append(n)
    if not by_track:raise ValueError('No pitched notes found')
    if melody_track is None:
        # Prefer a high, active track; exclude sparse intros if possible.
        ranked=sorted(by_track,key=lambda t:(len(by_track[t])>=8,sum(n[2] for n in by_track[t])/len(by_track[t]),len(by_track[t])),reverse=True)
        melody_track=ranked[0]
    if melody_track not in by_track:raise ValueError('Selected melody track has no notes')
    melody=by_track[melody_track]
    other=[n for n in melodic if n[0]!=melody_track]
    if bass_track is not None:other=by_track[bass_track]
    length=max(n[4] for n in melody)
    bars=min(max_bars,max(1,(length+(ppqn*4)-1)//(ppqn*4)))
    samples=bars*16
    def active_at(events,position):return [n[2] for n in events if n[3]<=position<n[4]]
    # Grid cell = 1/4 beat, so a complete 4/4 bar contains 16 cells.
    grid=[]
    for k in range(samples):
        pitch=active_at(melody,(k+0.5)*ppqn/4)
        grid.append(note_name(max(pitch)) if pitch else 'R')
    barstrings=[]
    for bar in range(bars):
        slots=grid[16*bar:16*(bar+1)]
        parts=[];last=slots[0];length=1
        for x in slots[1:]+[None]:
            if x==last:length+=1
            else:
                parts.append(f'{last}:{length/4:g}')
                last=x;length=1
        barstrings.append(' '.join(parts))
    pairs=[];root_map={}
    for bar in range(bars):
        two=[]
        for half in range(2):
            pos=(bar*4+half*2+0.5)*ppqn
            root_pitches=active_at(other,pos)
            if not root_pitches:root_pitches=active_at(melody,pos)
            root=(min(root_pitches) if root_pitches else 48)%12+48
            name=note_name(root)
            root_map[name]=root;two.append(name)
        pairs.append(two)
    patterns={};playlist=[];overrides={};seen={};labels=['intro']+[chr(65+i) for i in range(24)]
    for j,start in enumerate(range(0,bars,section_bars)):
        part=(tuple(barstrings[start:start+section_bars]),tuple(tuple(p) for p in pairs[start:start+section_bars]))
        if part in seen:name=seen[part]
        else:
            if len(patterns)>=len(labels):raise ValueError('Too many unique sections')
            name=labels[len(patterns)]
            patterns[name]=list(part[0]);overrides[name]=list(map(list,part[1]));seen[part]=name
        playlist.append(name)
    return {
        'title':'MIDI reduction for ATtiny13A', 'tempo_bpm':bpm,'beats_per_bar':4,
        'playlist':playlist,'patterns':patterns,'chord_pairs':[pairs[0]],
        'chord_overrides':overrides,'chord_roots':root_map,
        'conversion_note':f'Melody track {melody_track}; {bars} bars; quarter-beat quantization; bass-root accompaniment, NOT full MIDI polyphony'
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('midi',help='Input .mid/.midi file')
    ap.add_argument('-o','--output',default='score.json')
    ap.add_argument('--melody-track',type=int)
    ap.add_argument('--bass-track',type=int)
    ap.add_argument('--bars',type=int,default=16)
    ap.add_argument('--section-bars',type=int,default=4)
    ap.add_argument('--tempo',type=int,help='Override MIDI tempo in beats per minute')
    args=ap.parse_args()
    if args.bars<1 or args.section_bars<1:ap.error('Bar counts must be positive')
    notes,ppqn,bpm=read_midi(args.midi)
    song=create_score(notes,ppqn,args.tempo or bpm,args.bars,args.section_bars,args.melody_track,args.bass_track)
    Path(args.output).write_text(json.dumps(song,ensure_ascii=False,indent=2)+'\n')
    print(f'Wrote {args.output}: {len(song["playlist"])} blocks, {len(song["patterns"])} unique; tempo {song["tempo_bpm"]} BPM')
    print(song['conversion_note'])
    print('Run: python build.py (in the folder containing the new score.json).')


if __name__=='__main__':main()

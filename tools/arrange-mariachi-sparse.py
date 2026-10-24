"""Keep every lead note and replace the busy backing with sparse source voicings.

This is an explicitly new arrangement, not lossless source-note compression.
The original two-guitar score/player remains available separately.
"""
from pathlib import Path
from copy import deepcopy
import argparse
import importlib.util
import json

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('mariachi_polyphonic',ROOT/'tools/build-mariachi-lossless.py')
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)


def arrange():
    original=engine.compile_score()['parts']
    parts=deepcopy(original)
    source=original[1]['groups']
    lead=original[0]['groups']
    groups=[]
    # Each two-quarter cell has one attack and one quarter of breathing room.
    # Alternate a source bass note with a small source chord. Before Gtr.2's
    # first entry, stay silent rather than inventing accompaniment notes.
    for quarter in range(0,63,2):
        tick=quarter*480
        current=next((g for g in source if g['on']<=tick<g['off']),None)
        if current is None:
            current=next((g for g in reversed(source) if g['on']<=tick),None)
        if current is None:
            continue
        pitches=sorted(set(current['pitches']))
        if quarter%4==0:
            chosen=[pitches[0]]
        else:
            # One representative of each pitch class, in the existing voicing.
            chosen=[];classes=set()
            for pitch in reversed(pitches):
                if pitch%12 not in classes:
                    chosen.append(pitch);classes.add(pitch%12)
                if len(chosen)==3:break
        groups.append(dict(on=tick,off=min(tick+480,63*480),velocity=80,pitches=chosen))
    parts[1]['groups']=groups
    assert parts[0]==original[0]
    assert all(g['on']%960==0 and g['off']-g['on']==480 for g in groups)
    assert all(len(g['pitches'])<=(1 if (g['on']//480)%4==0 else 3) for g in groups)
    description=dict(policy='sparse-source-voicings-v1',title='Canción del Mariachi · редкие аккорды',
        sourceFile='../../reference/cancion-del-mariachi/source-events.json',
        sourceSha256=engine.hashlib.sha256(engine.SOURCE.read_bytes()).hexdigest(),
        firstBeat=58,lastBeat=121,leadSourceNotes=117,leadNotesPreserved=True,
        backingSourceNotes=910,backingNotes=sum(len(g['pitches']) for g in groups),
        backingAttacks=len(groups),originalBackingAttacks=len(source),
        attackSpacingQuarterBeats=2,gateQuarterBeats=1,
        method='Keep all Gtr.1 notes and gates. Every two quarters alternate the lowest Gtr.2 source pitch and up to three distinct source chord pitch classes; hold one quarter, rest one quarter. No melody is borrowed from rhythm-guitar top notes.',
        references=[dict(url='https://www.gitaartabs.nl/tab/los-lobos-and-antonio-banderas/cancion-del-mariachi',
            use='Sparse sustained support at the start of the Guitar Solo section; arrangement principle only. Notes come from the retained event JSON.'),
            dict(url='https://christianshowtoplays.de/download/PDF/Los_Lobos_Cancin_Del_Mariachi_antonio_banderas_version.pdf',
            use='Compared lead rests and Verse/Interlude sections on pages 1–2; no external note transcription copied.')])
    return parts,description


def build(folder):
    parts,description=arrange()
    codec=engine.compile_parts(parts)
    report=engine.build(folder,codec=codec,arrangement=description)
    (folder/'arrangement.json').write_text(json.dumps(dict(**description,parts=parts),indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({key:description[key] for key in ('leadSourceNotes','backingNotes','backingAttacks')}))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'build/mariachi-sparse')
    args=parser.parse_args();build(args.output)

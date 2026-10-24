"""Find a losslessly packed opening excerpt that fits the 1 KB device."""
from pathlib import Path
import hashlib
import importlib.util
import json
import argparse

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'ATtiny13A/Music/reference/turkish-march/source-events.json'
OUT=ROOT/'ATtiny13A/Music/variants/turkish-march'
BASE=ROOT/'ATtiny13A/Music/variants/rhythmic'

def module(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

reader=module('midi_reader',ROOT/'tools/midi-reader.py')
builder=module('builder',ROOT/'tools/build-rhythmic.py')


def left_hand_part(notes,ppqn,blocks):
    """Reduce each two-quarter window to one real, bounded source note.

    Select the same lowest note active half a quarter into the window as the
    original reduction. Selection never moves its attack to the window start.
    Repeated windows containing one source identity form one sustained note.
    """
    pairs=[];segments=[];chord_notes={'left_None':[None,None]}
    source=[(index,n) for index,n in enumerate(notes) if n[0]==2]
    for block in range(blocks):
        pair=[]
        for half in range(2):
            begin=(block*4+half*2)*ppqn;end=begin+2*ppqn
            active=[(index,n) for index,n in source if n[3]<=begin+ppqn/2<n[4]]
            selected=min(active,key=lambda item:(item[1][2],-item[1][3],item[0])) if active else None
            pitch=selected[1][2] if selected else None
            name='left_'+str(pitch);chord_notes[name]=[pitch,None];pair.append(name)
            if selected is None:continue
            identity,note=selected
            # Ceil note-on and floor note-off: neither an early attack nor a
            # late held note is introduced. A sub-grid note lasts one unit.
            on=(max(begin,note[3])*4+ppqn-1)//ppqn
            off=max(on+1,min(end,note[4])*4//ppqn)
            if segments and segments[-1]['sourceIndex']==identity and segments[-1]['offUnit']==on:
                segments[-1]['offUnit']=off
            else:
                segments.append(dict(sourceIndex=identity,pitch=pitch,onUnit=on,offUnit=off,
                                     sourceOnTicks=note[3],sourceOffTicks=note[4]))
        pairs.append(pair)
    controls=[dict(unit=0,offMask=2)]
    for segment in segments:
        controls.extend([dict(unit=segment['onUnit'],chord='left_'+str(segment['pitch'])),
                         dict(unit=segment['offUnit'],offMask=2)])
    controls.sort(key=lambda event:(event['unit'],'chord' in event))
    return pairs,chord_notes,controls,segments


def arrange(notes,ppqn,bpm,blocks,candidates):
    # One raw section preserves ties across bars. The compiler finds phrases.
    score=reader.create_score(notes,ppqn,bpm,blocks,blocks,1,2)
    score['patterns']['ending']=['D#5:1 R:3']
    score['playlist'].append('ending')
    score['engine']='instrument-bank'
    score['release_tail_slots']=2
    score['instruments']={'lead':'acoustic-grand-piano','keys':{'instrument':'acoustic-grand-piano','level':10},'pluck':'off','percussion':'off'}
    pairs,chord_notes,controls,segments=left_hand_part(notes,ppqn,blocks)
    score['left_hand_sampling_pairs']=pairs
    # Empty windows use NOTE_OFF, never a zero-frequency chord. Keep the
    # compiler's legacy chord registration nonzero so the specialized player
    # can omit a zero-DDS guard that can no longer execute in this reduction.
    first=next((name for pair in pairs for name in pair if name!='left_None'),'left_None')
    registered=[[name if name!='left_None' else first for name in pair] for pair in pairs]
    score['chord_overrides']['intro']=registered
    score['chord_pairs']=[registered[0]]
    score['chord_overrides']['ending']=[['cadence','cadence']]
    chord_notes['cadence']=[51,None]
    score['chord_notes']=chord_notes
    score['replace_harmony_sections']=['intro','ending']
    score['timed_controls']={'intro':controls,'ending':[
        dict(unit=0,chord='cadence'),dict(unit=4,offMask=14)]}
    score['left_hand_note_events']=segments
    score['packing_candidates']=candidates
    score['packing_max_entry_offset']=255
    return score


def enrich_chords(score,notes):
    segments=score['left_hand_note_events']
    chord_notes={'left_None':[None,None]}
    controls=[dict(unit=0,offMask=6)]
    for segment in segments:
        pitch=segment['pitch']
        candidates=[(i,n) for i,n in enumerate(notes) if n[0]==2 and n[3]==segment['sourceOnTicks'] and n[4]==segment['sourceOffTicks'] and n[2]>pitch]
        second=min(candidates,key=lambda item:item[1][2]) if candidates else None
        segment['secondPitch']=second[1][2] if second else None
        segment['secondSourceIndex']=second[0] if second else None
        name='left_'+str(pitch)+'_'+str(segment['secondPitch'])
        chord_notes[name]=[pitch,segment['secondPitch']]
        controls.extend([dict(unit=segment['onUnit'],chord=name),dict(unit=segment['offUnit'],offMask=6)])
    first=next(name for name in chord_notes if name!='left_None')
    score['chord_overrides']['intro']=[[first,first] for _ in score['patterns']['intro']]
    score['chord_pairs']=[[first,first]]
    chord_notes['cadence']=[51,None]
    score['chord_notes']=chord_notes
    score['timed_controls']['intro']=sorted(controls,key=lambda event:(event['unit'],'chord' in event))
    score['timed_controls']['ending']=[dict(unit=0,chord='cadence'),dict(unit=4,offMask=14)]
    score['instruments']['pluck']={'instrument':'acoustic-grand-piano','level':9}
    score['engine']='turkish-three'
    score['release_tail_slots']=0
    score['player_description']='Правая рука фортепиано, исходный бас и восстановленные тоны аккордов левой руки.'
    return score


def main():
    ap=argparse.ArgumentParser(description='Extend the authentic opening and restore left-hand chord tones')
    ap.add_argument('--source-bars',type=int,default=74)
    ap.add_argument('--candidates',type=int,default=4096)
    ap.add_argument('--output',type=Path,default=OUT)
    args=ap.parse_args()
    if args.source_bars<70 or args.source_bars%2:ap.error('--source-bars must be an even number of at least70')
    notes,ppqn,bpm=reader.read_midi(SOURCE)
    score=enrich_chords(arrange(notes,ppqn,bpm,args.source_bars//2,args.candidates),notes)
    score['title']='Моцарт — Турецкий марш (расширенный фрагмент)'
    score['composer']='Wolfgang Amadeus Mozart'
    score['source_midi']=dict(file='../../reference/turkish-march/source-events.json',sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        originalMidiSha256=json.loads(SOURCE.read_text(encoding='utf-8'))['source']['sha256'],ppqn=ppqn,
        credit='MIDI: Bernd Krüger / piano-midi.de; source edition2013-07-15',timeSignature='2/4',sourcePitchedNotes=len(notes))
    score['arrangement']=dict(sourceQuarterBeats=args.source_bars*2,sourceBars2_4=args.source_bars,cadenceQuarterBeats=4,
        lead='Highest active source right-hand note, sixteenth grid; every selected repeated attack preserved.',
        accompaniment='Lowest original source left-hand note selected half a quarter into each two-quarter window, plus the lowest higher chord tone sharing its exact source onset and NoteOff. Selected source identities retain bounded attacks/releases; absent chord tones are silent.',
        leftHandQuantization='Ceil NoteOn, floor NoteOff, minimum one sixteenth; no selected note extends beyond its two-quarter window.',
        scope='Extended opening excerpt with added closing D# cadence. Full source polyphony and later source sections remain omitted.',
        tempo='Steady151 BPM replaces the expressive source tempo map.',
        restoredSecondChordNotes=sum(n['secondPitch'] is not None for n in score['left_hand_note_events']))
    engine=module('turkish_three',ROOT/'tools/build-turkish-three.py')
    result=engine.build(args.output,score)
    (args.output/'packing-search.json').write_text(json.dumps(dict(
        selection='Selected extended source prefix with genuine inner chord notes. The dictionary is heuristic; no global maximum is claimed.',
        candidates=args.candidates,flashBytes=result['flashBytes'],codeBytes=result['codeBytes'],tableBytes=result['tableBytes'],
        sourceBars2_4=args.source_bars,flashLimitBytes=1024,maximumPhraseEntryOffset=255,streamPointerBits=16),indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(sourceBars=args.source_bars,seconds=(args.source_bars*2+4)*60/bpm,flashBytes=result['flashBytes'],restoredSecondChordNotes=score['arrangement']['restoredSecondChordNotes'])))


if __name__=='__main__':main()

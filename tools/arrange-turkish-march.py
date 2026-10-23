"""Find a losslessly packed opening excerpt that fits the 1 KB device."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import argparse
import math

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


def main():
    notes,ppqn,bpm=reader.read_midi(SOURCE)
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-bars',type=int,help='Even number of source 2/4 bars; default searches every prefix')
    ap.add_argument('--candidates',type=int,nargs='+',default=[96,192,384,4096],
                    help='Deterministic dictionary search limits (default: 96 192 384 4096)')
    args=ap.parse_args()
    if any(n<1 for n in args.candidates):ap.error('--candidates must be positive integers')
    maximum=math.ceil(max(n[4] for n in notes if n[0]==1)/(ppqn*4))
    trials=[];best=None
    # Measure specialized machine code, rather than assuming the old four-voice
    # engine's size. Score contents only change tables after the playlist label.
    fixture=ROOT/'build/turkish-engine-budget';fixture.mkdir(parents=True,exist_ok=True)
    # The register-dependent piano envelope can require extra code when the
    # full pitch range reaches MIDI75. Budget against the whole source range.
    fixture_score=arrange(notes,ppqn,bpm,maximum,96)
    source,metadata=builder.engine.specialize(fixture_score,builder.bank.describe_assignments(fixture_score['instruments']))
    fixture_score.update(metadata)
    source=builder.release_engine.specialize(fixture_score,source)
    (fixture/'synth.S').write_text(source,encoding='utf-8',newline='\n')
    for name in ['config.inc','score.inc']:shutil.copyfile(BASE/name,fixture/name)
    _,labels=builder.release_engine.assemble_relaxed(fixture/'synth.S');code_bytes=labels['playlist']
    def assess(blocks,candidates):
        nonlocal best
        score=arrange(notes,ppqn,bpm,blocks,candidates)
        _,meta=builder.compiler.to_inc(score,validate_size=False)
        size=(code_bytes+meta['total_data_bytes']+1)//2*2
        fits=size<=1024 and meta['maximum_entry_offset']<=255 and meta['playlist_bytes']<=255
        trials.append(dict(sourceBars2_4=blocks*2,candidates=candidates,flashBytes=size,
                           dataBytes=meta['total_data_bytes'],maximumEntryOffset=meta['maximum_entry_offset'],
                           playlistBytes=meta['playlist_bytes'],fits=fits))
        if fits and (best is None or (blocks,-size)>(best[0],-best[1])):best=(blocks,size,score)
        return size
    if args.source_bars is not None:
        if args.source_bars<2 or args.source_bars%2:ap.error('--source-bars must be a positive even number')
        if args.source_bars>maximum*2:ap.error('--source-bars exceeds the MIDI length')
        for candidates in sorted(set(args.candidates)):assess(args.source_bars//2,candidates)
    else:
        print('Searching all',maximum,'source prefixes and refining dictionaries near the Flash budget...',flush=True)
        sizes={blocks:assess(blocks,96) for blocks in range(1,maximum+1)}
        for blocks,size in sizes.items():
            if size<=1088:
                for candidates in sorted(set(args.candidates)-{96}):
                    # The strongest dictionary can be expensive. Only use it
                    # to extend or improve the best prefix already found.
                    if candidates>384 and best is not None and blocks<best[0]:continue
                    assess(blocks,candidates)
    if best is None:raise ValueError('No searched arrangement fits the device')
    blocks,size,score=best
    print('Selected',blocks*2,'source bars + cadence;',size,'Flash bytes',flush=True)
    score['title']='Моцарт — Турецкий марш (начальный фрагмент)'
    score['composer']='Wolfgang Amadeus Mozart'
    score['source_midi']={'file':'../../reference/turkish-march/source-events.json',
        'sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'originalMidiSha256':json.loads(SOURCE.read_text(encoding='utf-8'))['source']['sha256'],'ppqn':ppqn,
        'credit':'MIDI: Bernd Krüger / piano-midi.de; source edition 2013-07-15',
        'timeSignature':'2/4','sourcePitchedNotes':len(notes),'sourceTempoChanges':'Expressive tempo map replaced by steady 151 BPM'}
    score['arrangement']={'sourceQuarterBeats':blocks*4,'sourceBars2_4':blocks*2,'cadenceQuarterBeats':4,
        'lead':'Highest active note of right-hand track 1, sixteenth grid, distinct repeated Note On events',
        'accompaniment':'Lowest source note active half a quarter into each two-quarter window; exact selected source identity retains its real NoteOn/NoteOff within the window; continuous identities merge; pickup silence retained; full piano polyphony omitted',
        'leftHandQuantization':'Sixteenth grid: ceil NoteOn and floor NoteOff, minimum one grid unit; no source selected for an empty window',
        'scope':'Opening excerpt with a closing D# cadence, not the complete MIDI'}
    OUT.mkdir(parents=True,exist_ok=True)
    for name in ['avr_core.js','FluidR3-MIT.txt']:
        shutil.copyfile(BASE/name,OUT/name)
    (OUT/'packing-search.json').write_text(json.dumps(dict(selection='Longest fitting searched prefix; then smallest image. Dictionary optimization is heuristic.',
        engineCodeBytes=code_bytes,flashLimitBytes=1024,maximumPhraseEntryOffset=255,streamPointerBits=16,trials=trials),indent=2)+'\n',encoding='utf-8',newline='\n')
    (OUT/'score.json').write_text(json.dumps(score,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    builder.build(OUT)

if __name__=='__main__':main()

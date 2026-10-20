"""Find a losslessly packed opening excerpt that fits the 1 KB device."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import argparse
import math

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'ATtiny13A/Music/reference/turkish-march/source.mid'
OUT=ROOT/'ATtiny13A/Music/variants/turkish-march'
BASE=ROOT/'ATtiny13A/Music/variants/rhythmic'

def module(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

reader=module('midi_reader',ROOT/'tools/midi-reader.py')
builder=module('builder',ROOT/'tools/build-rhythmic.py')

def main():
    notes,ppqn,bpm=reader.read_midi(SOURCE)
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-bars',type=int,help='Even number of source 2/4 bars; default searches every prefix')
    args=ap.parse_args()
    maximum=math.ceil(max(n[4] for n in notes if n[0]==1)/(ppqn*4))
    trials=[];best=None
    def arrange(blocks,candidates):
        # One raw section preserves ties across bars. The compiler finds phrases.
        score=reader.create_score(notes,ppqn,bpm,blocks,blocks,1,2)
        score['patterns']['ending']=['D#5:1 R:3']
        score['playlist'].append('ending')
        score['chord_overrides']['ending']=[['D#3','D#3']]
        score['chord_roots']['D#3']=51
        score['engine']='instrument-bank'
        score['instruments']={'lead':'acoustic-grand-piano','keys':{'instrument':'acoustic-grand-piano','level':10},'pluck':'off','percussion':'off'}
        # Keep actual left-hand bass pitches, with silence in the pickup.
        # Two samples per four-quarter block are an explicit polyphony reduction.
        pairs=[];chord_notes={}
        for block in range(blocks):
            pair=[]
            for half in range(2):
                pos=(block*4+half*2+.5)*ppqn
                active=[n[2] for n in notes if n[0]==2 and n[3]<=pos<n[4]]
                pitch=min(active) if active else None
                name='left_'+str(pitch)
                chord_notes[name]=[pitch,None];pair.append(name)
            pairs.append(pair)
        score['chord_overrides']['intro']=pairs
        score['chord_pairs']=[pairs[0]]
        score['chord_overrides']['ending']=[['cadence','cadence']]
        chord_notes['cadence']=[51,None]
        score['chord_notes']=chord_notes
        score['packing_candidates']=candidates
        return score
    # Measure specialized machine code, rather than assuming the old four-voice
    # engine's size. Score contents only change tables after the playlist label.
    fixture=ROOT/'build/turkish-engine-budget';fixture.mkdir(parents=True,exist_ok=True)
    source,_=builder.engine.specialize(arrange(1,96),builder.bank.describe_assignments(arrange(1,96)['instruments']))
    (fixture/'synth.S').write_text(source,encoding='utf-8',newline='\n')
    for name in ['config.inc','score.inc']:shutil.copyfile(BASE/name,fixture/name)
    _,labels=builder.assembler.assemble(fixture/'synth.S');code_bytes=labels['playlist']
    def assess(blocks,candidates):
        nonlocal best
        score=arrange(blocks,candidates)
        _,meta=builder.compiler.to_inc(score,validate_size=False)
        size=(code_bytes+meta['total_data_bytes']+1)//2*2
        fits=size<=1024 and meta['maximum_entry_offset']<=255 and meta['playlist_bytes']<=255
        trials.append(dict(sourceBars2_4=blocks*2,candidates=candidates,flashBytes=size,fits=fits))
        if fits and (best is None or (blocks,-size)>(best[0],-best[1])):best=(blocks,size,score)
        return size
    if args.source_bars is not None:
        if args.source_bars<2 or args.source_bars%2:ap.error('--source-bars must be a positive even number')
        for candidates in [96,192,384]:assess(args.source_bars//2,candidates)
    else:
        print('Searching all',maximum,'source prefixes and refining dictionaries near the Flash budget...',flush=True)
        sizes={blocks:assess(blocks,96) for blocks in range(1,maximum+1)}
        for blocks,size in sizes.items():
            if size<=1088:
                for candidates in [192,384]:assess(blocks,candidates)
    if best is None:raise ValueError('No searched arrangement fits the device')
    blocks,size,score=best
    print('Selected',blocks*2,'source bars + cadence;',size,'Flash bytes',flush=True)
    score['title']='Моцарт — Турецкий марш (начальный фрагмент)'
    score['composer']='Wolfgang Amadeus Mozart'
    score['source_midi']={'file':'../../reference/turkish-march/source.mid',
        'sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'ppqn':ppqn,
        'credit':'MIDI: Bernd Krüger / piano-midi.de; source edition 2013-07-15',
        'timeSignature':'2/4','sourcePitchedNotes':len(notes),'sourceTempoChanges':'Expressive tempo map replaced by steady 151 BPM'}
    score['arrangement']={'sourceQuarterBeats':blocks*4,'sourceBars2_4':blocks*2,'cadenceQuarterBeats':4,
        'lead':'Highest active note of right-hand track 1, sixteenth grid, distinct repeated Note On events',
        'accompaniment':'Actual low pitches sampled from left-hand piano track 2 every two quarters; pickup silence retained; full piano polyphony omitted',
        'scope':'Opening excerpt with a closing D# cadence, not the complete MIDI'}
    OUT.mkdir(parents=True,exist_ok=True)
    for name in ['avr_core.js','FluidR3-MIT.txt']:
        shutil.copyfile(BASE/name,OUT/name)
    (OUT/'packing-search.json').write_text(json.dumps(dict(selection='Longest fitting searched prefix; then smallest image. Dictionary optimization is heuristic.',
        engineCodeBytes=code_bytes,flashLimitBytes=1024,maximumPhraseEntryOffset=255,streamPointerBits=16,trials=trials),indent=2)+'\n',encoding='utf-8',newline='\n')
    (OUT/'score.json').write_text(json.dumps(score,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    builder.build(OUT)

if __name__=='__main__':main()

#!/usr/bin/env python3
"""Convert an SMF MIDI into a reproducible, bank-assigned ATtiny13A image.

Standard library only. This is a documented monophonic reduction, followed by
lossless phrase packing, not a General MIDI synthesizer. Never trims an intro
or silently shortens a song to make it fit. See tools/MIDI_TO_FIRMWARE_RU.txt.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


reader = module('conversion_midi', 'midi-reader.py')
builder = module('conversion_builder', 'build-rhythmic.py')
event_json = module('conversion_events', 'midi-events.py')


def midi_metadata(path):
    document=event_json.load(path)
    programs={};tempos=[]
    for track in document['tracks']:
        for event in track['events']:
            if event['type']=='programChange':programs.setdefault((track['index'],event['channel']),[]).append(dict(tick=event['tick'],program=event['program']))
            elif event['type']=='tempo':tempos.append(dict(tick=event['tick'],microseconds=event['microsecondsPerQuarter']))
    return programs,tempos


def select_instrument(track, notes, programs, override=None):
    bank = builder.bank.load_bank()
    if override is not None:
        if override not in bank['instruments']:raise ValueError(f'Unknown bank instrument: {override}')
        return override
    channels = {n[1] for n in notes if n[0] == track and n[1] != 9}
    selected = set()
    for channel in channels:
        # ProgramChange is channel-wide even when stored in another SMF track.
        timeline = sorted((event for (other_track,c),values in programs.items() if c==channel for event in values), key=lambda e:e['tick'])
        for note in notes:
            if note[0]!=track or note[1]!=channel:continue
            active=[e for e in timeline if e['tick']<=note[3]]
            selected.add(active[-1]['program'] if active else 0)
    if len(selected) != 1:
        raise ValueError(f'Track {track} changes instruments; select one explicitly in the build configuration')
    gm = selected.pop()
    matching = [key for key,value in bank['instruments'].items() if value.get('gmProgram') == gm and key != 'off']
    if not matching:raise ValueError(f'GM program {gm} is absent from the bank; add a measured profile or explicitly choose an approximation')
    return matching[0]


def make_score(notes, ppqn, bpm, settings, programs):
    pitched = [n for n in notes if n[1] != 9]
    tracks = sorted({n[0] for n in pitched})
    if not tracks:raise ValueError('MIDI has no pitched notes')
    lead = settings.get('lead_track')
    if lead is None:lead = max(tracks,key=lambda t:(sum(n[0]==t for n in pitched)>=8,sum(n[2] for n in pitched if n[0]==t)/sum(n[0]==t for n in pitched)))
    if lead not in tracks:raise ValueError('Selected lead track is empty')
    bass = settings.get('bass_track')
    if bass is not None and (bass not in tracks or bass == lead):raise ValueError('Bass must be a different pitched track')
    extent = max(n[4] for n in pitched if n[0] in (lead,bass))
    available = math.ceil(extent/(ppqn*4))
    bars = settings.get('bars',available)
    if not 1 <= bars <= available:raise ValueError(f'--bars must be in 1..{available}')
    tempo = settings.get('tempo',bpm)
    if not 20 <= tempo <= 400:raise ValueError('Tempo must be in 20..400 quarter BPM')
    score = reader.create_score(notes,ppqn,tempo,bars,bars,lead,bass,extent_ticks=extent)
    score['title'] = settings.get('name') or 'MIDI adaptation'
    score['engine'] = 'instrument-bank'
    score['packing_candidates'] = settings.get('candidates',96)
    if score['packing_candidates'] < 1:raise ValueError('Candidate limit must be positive')
    score['packing_max_entry_offset'] = 255
    score['instruments'] = dict(lead=select_instrument(lead,notes,programs,settings.get('lead_instrument')),keys='off',pluck='off',percussion='off')
    score['chord_notes'] = {};score['chord_pairs'] = [['silent','silent']]
    score['chord_notes']['silent'] = [None,None]
    score['chord_overrides'] = {};score['replace_harmony_sections'] = ['intro','silence']
    controls = [];previous = None
    if bass is not None:
        score['instruments']['keys'] = select_instrument(bass,notes,programs,settings.get('bass_instrument'))
        events = [(n[2],math.ceil(n[3]*4/ppqn),math.floor(n[4]*4/ppqn),identity)
                  for identity,n in enumerate(notes) if n[0]==bass and n[1]!=9]
        for unit in range(bars*16):
            active = [n for n in events if n[1]<=unit<n[2]]
            selected = min(active,key=lambda n:(n[0],-n[1],n[3])) if active else None
            if selected != previous:
                if selected is None:controls.append(dict(unit=unit,offMask=2))
                else:
                    name = 'bass_'+str(selected[0]);score['chord_notes'][name] = [selected[0],None]
                    controls.append(dict(unit=unit,chord=name))
            previous = selected
    # The final rest releases the lead; F6 releases both companions. One
    # complete storage bar guarantees >205ms to finish all release envelopes.
    score['patterns']['silence'] = ['R:4'];score['playlist'].append('silence')
    score['timed_controls'] = dict(intro=controls,silence=[dict(unit=0,offMask=6)])
    if controls:
        first=next((c['chord'] for c in controls if 'chord' in c),None)
        if first:score['chord_pairs']=[[first,first]]
    elif bass is not None:
        # No source bass survives the conservative grid quantizer. Do not
        # leave an unreachable zero-frequency accompaniment enabled.
        score['instruments']['keys']='off'
    if score['instruments']['lead'] in ('acoustic-grand-piano','acoustic-grand-piano-soft') and score['instruments']['keys'] in ('off','acoustic-grand-piano','acoustic-grand-piano-soft','fretless-bass'):
        score['release_tail_slots']=2
    score['conversion'] = dict(leadTrack=lead,bassTrack=bass,sourceBars=bars,availableLeadBars=available,
        startsAtSourceBeat=0,leadQuantization='Nearest sixteenth, ties to even; highest active note; separate NoteOn identities',
        bassQuantization='Ceil NoteOn, floor NoteOff; lowest active source note; distinct repeated attacks',
        omittedDrumNotes=sum(n[1]==9 for n in notes),
        ending='One silent 4-quarter storage block; all parts release before the loop restarts',
        tempo='Constant quarter BPM; source tempo map retained as metadata; use a dedicated arranger for expressive tempo maps',
        reduction='One lead plus optional monophonic bass. Full polyphony and sustain-pedal controller are not emulated.')
    return score


def convert(settings):
    source = Path(settings['input']).resolve();output = Path(settings['output']).resolve()
    if output.exists():raise ValueError(f'Output already exists: {output}; choose a new directory')
    notes,ppqn,bpm = reader.read_midi(source)
    programs,tempos = midi_metadata(source)
    score = make_score(notes,ppqn,bpm,settings,programs)
    retained=event_json.describe_parts(event_json.load(source))
    retained_text=json.dumps(retained,ensure_ascii=False,indent=2)+'\n'
    score['source_midi'] = dict(file='source-events.json',sha256=hashlib.sha256(retained_text.encode('utf-8')).hexdigest(),
        originalMidiSha256=retained['source']['sha256'],ppqn=ppqn,tempoMap=tempos,
        programs=[dict(track=t,channel=c,programs=p) for (t,c),p in sorted(programs.items())])
    # Build and size-check before creating the destination, so a failure never
    # leaves a mixture of old HEX, new EEPROM and partially generated sources.
    staging = ROOT/'build/midi-conversion';staging.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=staging,prefix='trial-') as temporary:
        trial = Path(temporary)
        for filename in ('avr_core.js','FluidR3-MIT.txt'):shutil.copyfile(ROOT/'ATtiny13A/Music/variants/rhythmic'/filename,trial/filename)
        builder.save_text(trial/'source-events.json',retained_text)
        builder.save_text(trial/'score.json',json.dumps(score,ensure_ascii=False,indent=2)+'\n')
        builder.build(trial)
        builder.save_text(trial/'conversion.json',json.dumps(settings,ensure_ascii=False,indent=2)+'\n')
        output.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(trial,output)
    return output


def main():
    # Windows may select cp1252 for a redirected console. Source names and
    # destination paths can be Cyrillic even when the host locale is not.
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',nargs='?',help='External SMF MIDI or retained musical-event JSON')
    parser.add_argument('--config',type=Path,help='JSON settings; command-line values override them')
    for name in ('output','name','lead-instrument','bass-instrument'):parser.add_argument('--'+name)
    for name in ('lead-track','bass-track','bars','tempo','candidates'):parser.add_argument('--'+name,type=int)
    args = vars(parser.parse_args());config = args.pop('config')
    try:
        settings = json.loads(config.read_text(encoding='utf-8-sig')) if config else {}
        if not isinstance(settings,dict):raise ValueError('Configuration must be a JSON object')
        settings.update({key:value for key,value in args.items() if value is not None})
        if not settings.get('input') or not settings.get('output'):parser.error('input and --output are required (or supply --config)')
        result = convert(settings)
    except (ValueError,AssertionError,IndexError,KeyError,OSError) as error:
        parser.exit(1,f'Conversion failed: {error}\nUse fewer explicitly selected --bars or increase --candidates; the introduction is never removed automatically.\n')
    print('Built',result)


if __name__ == '__main__':main()

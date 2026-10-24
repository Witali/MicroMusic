"""Build native-time Alicia with four primary voices and two release slots.

The original 3/4, 4/4 and triplets use twelve units per quarter; tempo changes
remain commands. Harmony/arpeggios reuse the Z80 arrangement's actual chord
voicings. Repeated eighth-note piano motion alternates two retained chord
tones; a register counter replaces hundreds of literal accompaniment events.
By default write feasibility artifacts to build/alicia-multi. --production
publishes the checked native codec to variants/alicia; --output selects a folder.
"""
from pathlib import Path
from fractions import Fraction
import argparse
import hashlib
import importlib.util
import json
import math
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/alicia-multi'
SOURCE = ROOT / 'ATtiny13A/Music/reference/alicia/source-score.json'
BASE = ROOT / 'ATtiny13A/Music/variants/greensleeves'
DURATIONS = (3, 4, 6, 12, 18, 24, 30, 36)
TEMPOS = (78, 58, 87)
CHORDS = {
    'Cm': (36, [55, 60, 63]), 'Fm': (41, [56, 60, 65]),
    'Bb': (46, [58, 62, 65]), 'Eb': (39, [55, 58, 63]),
    'C7b9': (36, [58, 61, 64]), 'Gsus4': (43, [55, 60, 62]),
    'G7': (43, [55, 59, 62]), 'Abmaj7': (44, [56, 60, 63]),
    'Ab': (44, [56, 60, 63]), 'Am7b5': (45, [57, 60, 63]),
    'Bb7': (46, [56, 62, 65]), 'G7/B': (47, [55, 59, 62]),
    'Bb/D': (38, [58, 62, 65]), 'Cm/Eb': (39, [55, 60, 63]),
    'Dm7b5': (38, [53, 56, 60]), 'G7b9': (43, [53, 56, 59]),
    'Ddim7': (38, [53, 56, 59]), 'Cm/G': (43, [55, 60, 63]),
    'Fm7': (41, [56, 60, 63]), 'Fm/Ab': (44, [56, 60, 65]),
    'F5': (41, [53, 60, 65]), 'Cmadd9': (36, [55, 62, 63]),
}


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


compiler = module('alicia_multi_score', ROOT / 'tools/score-format.py')
release = module('alicia_multi_release', ROOT / 'tools/build-release-engine.py')
bank = module('alicia_multi_bank', ROOT / 'tools/instrument-bank.py')


def duration_parts(length):
    best = [()] + [None] * length
    for n in range(1, length + 1):
        choices = [(d,) + best[n-d] for d in DURATIONS if d <= n and best[n-d] is not None]
        if choices:
            best[n] = min(choices, key=lambda parts:(len(parts), tuple(-d for d in parts)))
    if best[length] is None:
        raise ValueError(f'Unrepresentable native duration {length}')
    return best[length]


def musical_stream(data, arpeggio=True):
    # Thirteen used piano notes fit nibbles; no unused chromatic DDS entries.
    pitched = set()
    descriptors = []
    def descriptor_key(chord, duration):
        root, tones = CHORDS[chord]
        return root, tuple(tones[:2]), duration
    def descriptor_index(chord, duration):
        key = descriptor_key(chord, duration)
        return next((i for i,(old,old_duration) in enumerate(descriptors)
                     if descriptor_key(old,old_duration)==key), None)
    for pattern in data['patterns'].values():
        for bar in pattern['bars']:
            transpose = bar.get('lead_transpose', pattern.get('lead_transpose', 0))
            for token in bar['melody'].split():
                note = compiler.midi(token.split(':')[0])
                if note is not None:
                    pitched.add(note + transpose)
            for chord, duration in bar['chords']:
                entry = (chord, int(Fraction(str(duration)) * 12))
                if descriptor_index(*entry) is None:
                    descriptors.append(entry)
    piano_pitches = sorted({note for _, tones in CHORDS.values() for note in tones})
    pitches = piano_pitches + sorted(pitched - set(piano_pitches))
    rest, hold = len(pitches), len(pitches) + 1
    assert hold < 24, (pitches, hold)
    bass = sorted({CHORDS[chord][0] for chord, _ in descriptors})
    bass_base = len(pitches)
    pitches += bass
    assert len(descriptors) <= 56
    incoming = {name:set() for name in data['patterns']}
    previous = (None, None)
    for name in data['playlist']:
        incoming[name].add(previous)
        pattern = data['patterns'][name]
        previous = (pattern['tempo_bpm'], pattern['bars'][-1].get('lead_instrument', pattern.get('lead_instrument', 1)))
    chunks, metadata = {}, {}
    for name, pattern in data['patterns'].items():
        needs_tempo = any(tempo != pattern['tempo_bpm'] for tempo,_ in incoming[name])
        controls = {0:[248 + TEMPOS.index(pattern['tempo_bpm'])]} if needs_tempo else {}
        prior_instruments = {instrument for _,instrument in incoming[name]}
        previous_instrument = next(iter(prior_instruments)) if len(prior_instruments)==1 else None
        melody, position = [], 0
        for bar_index, bar in enumerate(pattern['bars']):
            inst = bar.get('lead_instrument', pattern.get('lead_instrument', 1))
            if inst != previous_instrument:
                controls.setdefault(position, []).append(251 + inst)
                previous_instrument = inst
            cursor = position
            for chord, beats in bar['chords']:
                duration = int(Fraction(str(beats)) * 12)
                controls.setdefault(cursor, []).append(192 + descriptor_index(chord, duration))
                cursor += duration
            for token in bar['melody'].split():
                note, text = token.split(':')
                duration = int(Fraction(text) * 12)
                pitch = compiler.midi(note)
                if pitch is not None:
                    pitch += bar.get('lead_transpose', pattern.get('lead_transpose', 0))
                melody.append(dict(start=position, end=position+duration, pitch=pitch,
                                   sourceInstrument=inst, sourceBar=bar_index))
                position += duration
        stream = bytearray()
        for event in melody:
            at, end = event['start'], event['end']
            note_index = rest if event['pitch'] is None else pitches.index(event['pitch'])
            while at < end:
                stream.extend(controls.pop(at, []))
                stop = min([p for p in controls if at < p < end] + [end])
                for duration in duration_parts(stop-at):
                    stream.append(note_index * 8 + DURATIONS.index(duration))
                    at += duration
                    if note_index != rest:
                        note_index = hold
        assert not controls
        chunks[name] = bytes(stream)
        metadata[name] = dict(quarterBeats=position/12, sourceEvents=melody,
                              meter=f'{pattern["beats_per_bar"]}/4', tempoBpm=pattern['tempo_bpm'])
    full = b''.join(chunks[name] for name in data['playlist'])
    return full, chunks, dict(pitches=pitches, restIndex=rest, holdIndex=hold,
                             bassBase=bass_base, bassPitches=bass, descriptors=descriptors,
                             patterns=metadata, sourcePlaylist=data['playlist'])


def native_packer():
    # Apply clock/token predicates to a private module only. The production
    # packer remains unchanged and its repeated-phrase losslessness proof runs.
    path = ROOT / 'tools/pack-score.py'
    source = path.read_text(encoding='utf-8')
    source = source.replace('if token<224:', 'if token<192:')
    source = source.replace("        if atom[-1]&7==7:raise ValueError('Reserved duration code 7')\n", '')
    source = source.replace('(1,2,3,4,6,8,16)[atom[-1]&7]', 'DURATIONS[atom[-1]&7]')
    source = source.replace('if units%16==0:', 'if units%12==0:')
    namespace = dict(__name__='alicia_multi_packing', DURATIONS=DURATIONS)
    exec(compile(source, str(path), 'exec'), namespace)
    return namespace['pack']


def native_source(meta, arpeggio):
    """Use the reviewed native kernel independently of all published variants."""
    return (ROOT/'tools/alicia-native-template.S').read_text(encoding='utf-8')


def assemble(packed, meta, arpeggio):
    playlist = [packed['offsets'][name] for name in packed['playlist']]
    labels_at = {}
    for name, offset in packed['offsets'].items():
        labels_at.setdefault(offset, []).append('section_' + name)
    labels_at.setdefault(playlist[0], []).append('first_section')
    rows = ['playlist:', '  .byte ' + ','.join(map(str, playlist)),
            'durations:', '  .byte ' + ','.join(map(str, DURATIONS)),
            'tempo_steps:']
    steps = [round(bpm * 12 / 60 / (18750/256) * 65536) for bpm in TEMPOS]
    for step in steps:
        rows.append(f'  .byte {step&255},{step>>8}')
    rows.append('note_steps:')
    for pitch in meta['pitches']:
        step = round(440 * 2**((pitch-69)/12) * 65536 / 18750)
        rows.append(f'  .byte {step&255},{step>>8}')
    rows.append('chord_descriptors:')
    for chord, duration in meta['descriptors']:
        root, tones = CHORDS[chord]
        a, b, c = (meta['pitches'].index(pitch) for pitch in tones)
        assert all(0 <= value <= 15 for value in (a,b,c))
        rows.append(f'  .byte {a|(b<<4)},{meta["bassPitches"].index(root)|((duration//6)<<4)}')
    rows.append('melody_data:')
    for i, token in enumerate(packed['storage']):
        rows.extend(name+':' for name in labels_at.get(i, []))
        rows.append(f'  .byte {token}')
    constants = dict(REST_INDEX=meta['restIndex'], HOLD_INDEX=meta['holdIndex'],
                     PLAYLIST_LEN=len(playlist), FIRST_PLAYLIST_INDEX=int(len(playlist)>1),
                     GRID_STEP_LOW=steps[0]&255, GRID_STEP_HIGH=steps[0]>>8,
                     GRID_INITIAL_HIGH=math.ceil((65536-steps[0])/256),
                     BASS_BASE_NEGATIVE=256-meta['bassBase'])
    (OUT/'config.inc').write_text(''.join(f'.set {k}, {v}\n' for k,v in constants.items()), encoding='utf-8', newline='\n')
    (OUT/'score.inc').write_text('\n'.join(rows)+'\n', encoding='utf-8', newline='\n')
    (OUT/'synth.S').write_text(native_source(meta, arpeggio), encoding='utf-8', newline='\n')
    rom, labels = release.assemble_relaxed(OUT/'synth.S')
    # LPM tables contained in one page cannot carry from ADD into ZH. Prove
    # this against assembled addresses before removing the redundant ADCs.
    limits = dict(playlist=len(playlist), durations=8, tempo_steps=6, note_steps=len(meta['pitches'])*2)
    source = (OUT/'synth.S').read_text(encoding='utf-8')
    removed = []
    for name, length in limits.items():
        if labels[name] % 256 + length <= 256:
            for register in ('r4','r16','r17'):
                old = f'  ldi r30, lo8({name})\n  ldi r31, hi8({name})\n  add r30, {register}\n  adc r31, r29\n'
                if old in source:
                    source = source.replace(old, old.rsplit('  adc',1)[0])
                    removed.append(name)
    (OUT/'synth.S').write_text(source, encoding='utf-8', newline='\n')
    rom, labels = release.assemble_relaxed(OUT/'synth.S')
    for name in removed:
        assert labels[name] % 256 + limits[name] <= 256
    (OUT/'synth.bin').write_bytes(rom)
    assignments = dict(lead='acoustic-grand-piano-soft', keys='violin', pluck='cello', percussion='off')
    (OUT/'eeprom.bin').write_bytes(bank.build_eeprom(assignments))
    return rom, labels


def build(folder=None, candidates=4096, arpeggio=True, production=False):
    """Build the native codec; production dispatch preserves the saved source."""
    global OUT
    OUT = Path(folder) if folder is not None else ROOT/'build/alicia-multi'
    if not OUT.is_absolute():
        OUT = ROOT/OUT
    target=OUT
    saved = OUT/'score.json'
    previous = json.loads(saved.read_text(encoding='utf-8')) if production and saved.exists() else {}
    supported_banks=dict(lead='acoustic-grand-piano-soft',keys='violin',pluck='cello',percussion='off')
    if previous.get('engine')=='alicia-native' and previous.get('instruments')!=supported_banks:
        raise ValueError('alicia-native uses fixed piano/violin/cello wave banks; this assignment requires a new native codec profile')
    data = previous.get('native_score', json.loads(SOURCE.read_text(encoding='utf-8')))
    if candidates < 1:
        raise ValueError('Candidate count must be positive')
    if production:
        # A failed budget search must leave the saved firmware intact.
        OUT=ROOT/'build/alicia-native-trial'
    stream, chunks, meta = musical_stream(data, arpeggio)
    packed = native_packer()(stream, [chunks[name] for name in data['playlist']],
                             candidate_limit=candidates, max_entry_offset=255)
    OUT.mkdir(parents=True, exist_ok=True)
    if not production:
        (OUT/'source-stream.bin').write_bytes(stream)
        (OUT/'packed-stream.bin').write_bytes(packed['storage'])
    rom, labels = assemble(packed, meta, arpeggio)
    report = dict(experimental=not production, primaryVoices=4, releaseVoices=2,
                  sourceSha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                  sourceCommandBytes=len(stream), actualCodeBytes=labels['playlist'],
                  actualDataBytes=len(rom)-labels['playlist'], actualFlashBytes=len(rom),
                  fitsFlash=len(rom)<=1024, nativeUnitsPerQuarter=12,
                  pianoArpeggio=arpeggio,
                  temposBpm=TEMPOS, durations=DURATIONS,
                  maximumEntryOffset=max(packed['offsets'].values()), packing=packed['report'],
                  metadata=meta, labels=labels,
                  reduction='All 169 source melody attacks, 55 written bars, source octave/program changes and native rational note lengths retained. Repeated eighth-note piano motion is restored using the first two source chord tones; the third chord tone remains omitted. Bass root and bowed inner second chord tone remain. Companion gates close one native unit before the chord boundary.',
                  voices=[dict(state=97,role='source-melody',instruments=['acoustic-grand-piano-soft','violin'],programs=[0,40],sourcePrograms=[0,1],pianoLevel=14,bowedLevel=12,gain=1),
                          dict(state=102,role='piano-arpeggio',instrument='acoustic-grand-piano-soft',level=5,gain=1),
                          dict(state=107,role='cello-bass',instrument='cello',level=12,gain=.5),
                          dict(state=112,role='violin-inner-voice',instrument='violin',level=12,gain=.5)],
                  layout=dict(stateAddresses=[97,102,107,112,117,122], stateBytes=30,
                              ringStart=128, ringBytes=16, stackAvailableBytes=16))
    if not production:
        (OUT/'feasibility.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    if production:
        if not report['fitsFlash'] or report['maximumEntryOffset']>255:
            raise ValueError(f'Native Alicia exceeds the MCU budget: {len(rom)} Flash bytes')
        target.mkdir(parents=True,exist_ok=True)
        for name in ('synth.S','synth.bin','eeprom.bin','config.inc','score.inc'):
            shutil.copyfile(OUT/name,target/name)
        OUT=target
        publish(data, packed, meta, report, rom, labels, candidates)
    print(json.dumps({k:v for k,v in report.items() if k not in ('metadata','labels')}, indent=2))
    return report


def ihex(raw):
    rows=[]
    for i in range(0,len(raw),16):
        record=bytes([len(raw[i:i+16]),i>>8,i&255,0])+raw[i:i+16]
        rows.append(':'+(record+bytes([-sum(record)&255])).hex().upper())
    return '\n'.join(rows+[':00000001FF',''])


def publish(data, packed, meta, feasibility, rom, labels, candidates):
    """Produce the same self-contained artifacts as the ordinary builder."""
    def text(name, value):
        (OUT/name).write_text(value, encoding='utf-8', newline='\n')
    def json_text(name, value):
        text(name,json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    def sha(raw):
        return hashlib.sha256(raw).hexdigest()
    assignments=dict(lead='acoustic-grand-piano-soft',keys='violin',pluck='cello',percussion='off')
    profiles=bank.load_bank()['instruments']
    ep=bank.build_eeprom(assignments)
    assert ep==(OUT/'eeprom.bin').read_bytes()
    source_hash=sha(SOURCE.read_bytes())
    source_bars=sum(len(data['patterns'][name]['bars']) for name in data['playlist'])
    source_events=sum(len(meta['patterns'][name]['sourceEvents']) for name in data['playlist'])
    source_notes=sum(event['pitch'] is not None for name in data['playlist'] for event in meta['patterns'][name]['sourceEvents'])
    chord_count=sum(len(bar['chords']) for name in data['playlist'] for bar in data['patterns'][name]['bars'])
    piano_notes=sum(int(Fraction(str(beats))*2) for name in data['playlist']
                    for bar in data['patterns'][name]['bars'] for chord,beats in bar['chords'])
    companion_notes=2*chord_count+piano_notes
    source_seconds=sum(meta['patterns'][name]['quarterBeats']*60/data['patterns'][name]['tempo_bpm'] for name in data['playlist'])
    envelope_override=dict(bowed=dict(attackLevels=[0,4,8,12],retrigger='zero',releaseStep=1),
        piano=dict(leadLevel=14,companionLevel=5,decayMasks=[3,7,15],releaseStep=2),
        outputGain=dict(lead=1,pianoCompanion=1,cello=.5,innerViolin=.5,releaseSlots=.5),
        note='Measured bank waves and piano attack are unchanged. The native1KiB envelope explicitly replaces the bank default half-current bowed retrigger with a zero-level soft attack.')
    decoder_ranges=[(labels['read_event'],labels['render_tone']),
                    (labels['indexed_note'],labels['playlist'])]
    decoder_instructions=0
    for start,end in decoder_ranges:
        at=start
        while at<end:
            word=rom[at]|rom[at+1]<<8
            at+=4 if word&0xfe0f in (0x9000,0x9200) else 2
            decoder_instructions+=1
        assert at==end
    score=dict(engine='alicia-native',title='02 · Алисия · Экспедиция 33',
               composers=data['composers'],native_score=data,
               source_score=dict(file='../../reference/alicia/source-score.json',sha256=source_hash,
                                 rights=data['rights'],melodyTranscription=data['melody_transcription']),
               tempo_bpm=TEMPOS[0],native_units_per_quarter=12,
               instruments=assignments,instrument_slots_are='EEPROM wave banks, not the four physical voice states',
               primary_voice_assignments=feasibility['voices'],active_primary_voices=4,native_envelope_override=envelope_override,
               release_tail_slots=2,percussion_enabled=False,packing_candidates=candidates,
               arrangement=dict(sourceBars=source_bars,sourceEvents=source_events,sourceNoteOns=source_notes,
                                originalMeters=['3/4','4/4'],originalTemposBpm=list(TEMPOS),
                                durationSeconds=source_seconds,
                                rhythm='Native 12-units/quarter retains every rational source duration, including triplets; runtime switches tempo rather than flattening bars.',
                                reduction=feasibility['reduction'],
                                companionNoteOns=companion_notes,pianoNoteOns=piano_notes,
                                accompaniment=dict(chords=chord_count,pianoTonesPerChord=2,pianoStepQuarterBeats=.5,
                                    pianoMotion='Alternating first and second source chord tones; third tone omitted',
                                    retainedOriginalDuration=True),
                                loopSilence='The original final four-quarter rest; all six envelopes finish before restart.'))
    # Resolve the bank provenance separately from the actual four state roles.
    report=dict(engine='alicia-native',activePrimaryVoices=4,
                flashBytes=len(rom),codeBytes=labels['playlist'],tableBytes=len(rom)-labels['playlist'],
                eepromBytes=64,flashSha256=sha(rom),eepromSha256=sha(ep),labels=labels,
                instrumentBankSha256=sha(bank.BANK_PATH.read_bytes()),
                standaloneCoreSourceSha256=sha((ROOT/'web-player/lib/avr-reference.js').read_bytes()),
                standaloneHexParserSourceSha256=sha((ROOT/'web-player/lib/hex.js').read_bytes()),
                instrumentAssignments=bank.describe_assignments(assignments),
                primaryVoiceAssignments=feasibility['voices'],
                pianoArpeggio=score['arrangement']['accompaniment'],
                nativeEnvelopeOverride=envelope_override,
                scoreDecoder=dict(format='Native compact score, not raw MIDI/SMF',
                    mainBytes=decoder_ranges[0][1]-decoder_ranges[0][0],
                    helperBytes=decoder_ranges[1][1]-decoder_ranges[1][0],
                    totalBytes=sum(end-start for start,end in decoder_ranges),
                    staticInstructionCount=decoder_instructions,
                    scope='read_event through playlist decoding; indexed DDS lookup and companion-gate helper. Shared voice initialization, reserve allocation, DSP and PWM are excluded.'),
                sourceScoreSha256=source_hash,
                score=dict(note_count=sum(token<192 for token in b''.join(bytes(packed['sections'][name][:-1]) for name in packed['playlist'])),
                           event_bytes=len(packed['storage']),maximum_entry_offset=max(packed['offsets'].values()),
                           playlist_bytes=len(packed['playlist']),note_table_bytes=len(meta['pitches'])*2,
                           chord_table_bytes=len(meta['descriptors'])*2,durations=list(DURATIONS),
                           native_units_per_quarter=12,source=data['title'],
                           pitches=[compiler.pname(n) for n in meta['pitches'][:meta['restIndex']]]+['R','HOLD'],
                           dds_pitches=[compiler.pname(n) for n in meta['pitches']],
                           rest_index=meta['restIndex'],hold_index=meta['holdIndex'],
                           total_data_bytes=len(rom)-labels['playlist'],playlist=packed['playlist'],
                           source_playlist=data['playlist'],section_offsets=packed['offsets'],
                           compression=packed['report'],chord_descriptors=meta['descriptors'],
                           source_bars=source_bars,source_events=source_events,source_note_ons=source_notes),
                timing=dict(phaseBits=16,envelopeTickCycles=131072,nativeUnitsPerQuarter=12,
                            sourceDurationSeconds=score['arrangement']['durationSeconds'],
                            tempoBpm=TEMPOS[0],tempos=[dict(tempoBpm=bpm,phaseStep=round(bpm*12/60/(18750/256)*65536),
                                actualTempoBpm=round(bpm*12/60/(18750/256)*65536)/65536*(18750/256)*60/12) for bpm in TEMPOS],
                            sharedGrid='Native source quarter grid; tempo changes retained; meters remain 3/4 and 4/4'),
                articulation=dict(attack='piano/bowed',retrigger='Piano full; bowed from zero',phaseContinuous=True,
                                  bowedAttackStep=4,bowedMaximumLevel=12,pianoReleaseStep=2,bowedReleaseStep=1),
                releaseChannels=dict(primaryVoices=4,tailSlots=2,voiceAddresses=[97,102,107,112,117,122],
                    voiceStateBytes=30,pwmRingBytes=16,tailGain=.5,stealing='Quietest of two release levels',
                    phaseContinuous=True,isrCycles=15,requiredFuses=dict(low='0x7A',high='0xFF')))
    json_text('score.json',score)
    json_text('build-report.json',report)
    json_text('waveforms.json',dict(source='Shared measured FluidR3 build-time bank',
        bankSha256=report['instrumentBankSha256'],slots={name:dict(instrument=instrument,waves=profiles[instrument]['waves'])
            for name,instrument in assignments.items() if name!='percussion'},
        pianoTransient=profiles['acoustic-grand-piano-soft']['transient']))
    core=(ROOT/'web-player/lib/avr-reference.js').read_text(encoding='utf-8').replace('export class AVRCore','class AVRCore')
    parser=(ROOT/'web-player/lib/hex.js').read_text(encoding='utf-8').replace('export function parseHex','function parseHex')
    core += '\n'+parser+'\nAVRCore.fromHex=(flash,eeprom)=>new AVRCore(parseHex(flash),eeprom?parseHex(eeprom,64):null);\n'
    core += "if(typeof module!=='undefined'&&module.exports)module.exports={AVRCore};\n"
    text('avr_core.js',core)
    if not (OUT/'FluidR3-MIT.txt').exists():
        shutil.copyfile(BASE/'FluidR3-MIT.txt',OUT/'FluidR3-MIT.txt')
    text('synth.hex',ihex(rom))
    text('eeprom.hex',ihex(ep))
    html=(ROOT/'tools/player-template.html').read_text(encoding='utf-8')
    for key,value in [('AVR_CORE',(OUT/'avr_core.js').read_text(encoding='utf-8')),('FIRMWARE_HEX',ihex(rom)),('EEPROM_HEX',ihex(ep))]:
        html=html.replace('/*'+key+'*/',value)
    html=html.replace('ATtiny13A — проигрыватель AVR-прошивки','ATtiny13A — '+score['title'])
    html=html.replace('мелодия, пианино, гитара и ударные.',
                      'мелодия рояля/скрипки, арпеджио рояля, виолончель и внутренняя скрипка.')
    text('player.html',html)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates',type=int,default=4096)
    parser.add_argument('--arpeggio',action='store_true',default=True,help='Retained compatibility flag; repeated two-tone piano motion is always enabled')
    parser.add_argument('--output',type=Path,help='Output folder; defaults to build/alicia-multi')
    parser.add_argument('--production',action='store_true',help='Write self-contained native firmware; defaults to variants/alicia')
    args=parser.parse_args()
    output=args.output or (ROOT/'ATtiny13A/Music/variants/alicia' if args.production else None)
    build(output,args.candidates,args.arpeggio,args.production)


if __name__ == '__main__':
    main()

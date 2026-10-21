"""Compile the native four-primary/two-release Children arrangement.

By default writes an isolated build/children-four experiment. --production
publishes the same verified image and self-contained player to the variant.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import math
import shutil
import re
import itertools

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/children-four'
SOURCE = ROOT / 'ATtiny13A/Music/reference/children/source-events.json'
BASE = ROOT / 'ATtiny13A/Music/variants/children'
DURATIONS = (1, 2, 3, 4, 6, 8, 16)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


reader = module('children_four_midi', ROOT / 'tools/midi-reader.py')
compiler = module('children_four_score', ROOT / 'tools/score-format.py')
packing = module('children_four_packing', ROOT / 'tools/pack-score.py')
ORIGINAL_ATOMS = packing.atoms


def selected_segments(notes, ppqn, tracks, stop, selection, quantization='nearest'):
    """A documented one-voice reduction, retaining selected source identities."""
    quantized = []
    for identity, note in enumerate(notes):
        if note[0] not in tracks or note[3] * 4 >= stop * ppqn:
            continue
        # Humanization by one MIDI tick must not become an artificial whole
        # sixteenth delay. Nearest/even matches the existing main piano grid.
        if quantization == 'nearest':
            start = round(note[3] * 4 / ppqn)
            end = min(stop, max(start + 1, round(note[4] * 4 / ppqn)))
        elif quantization == 'inside':
            start = math.ceil(note[3] * 4 / ppqn)
            end = min(stop, math.floor(note[4] * 4 / ppqn))
        else:
            raise ValueError('Unknown source quantization')
        if start < end:
            quantized.append(dict(identity=identity, track=note[0], pitch=note[2],
                                  start=start, end=end, sourceOn=note[3], sourceOff=note[4]))
    grid = []
    for unit in range(stop):
        active = [n for n in quantized if n['start'] <= unit < n['end']]
        if selection == 'latest':
            chosen = max(active, key=lambda n:(n['start'], -n['track'], n['pitch'])) if active else None
        else:
            chosen = max(active, key=lambda n:(n['pitch'], n['start'])) if active else None
        grid.append(chosen)
    segments = []
    for unit, note in enumerate(grid):
        if note is None:
            continue
        if segments and segments[-1]['identity'] == note['identity'] and segments[-1]['end'] == unit:
            segments[-1]['end'] += 1
        else:
            segments.append(dict(note, start=unit, end=unit + 1))
    return segments, len(quantized)


def musical_stream(notes, ppqn, bpm):
    bars = 107
    score = reader.create_score(notes, ppqn, bpm, bars, bars, 1, 4)
    score['patterns']['ending'] = ['F4:1 R:3']
    lead_pitches = sorted({token.split(':')[0] for rows in score['patterns'].values()
                          for bar in rows for token in bar.split()} - {'R'}, key=compiler.midi)
    pitches = [compiler.midi(name) for name in lead_pitches]
    echo, echo_source = selected_segments(notes, ppqn, (2, 3), bars * 16, 'latest')
    bass, bass_source = selected_segments(notes, ppqn, (4,), bars * 16, 'latest')
    strings, strings_source = selected_segments(notes, ppqn, (5,), bars * 16, 'highest')
    for note in [37,34,29] + sorted({n['pitch'] for n in echo + bass + strings}):
        if note not in pitches:
            pitches.append(note)
    pitch_index = {pitch:index for index, pitch in enumerate(pitches)}
    # All sixteen echo notes are already the main table's first sixteen notes.
    assert set(n['pitch'] for n in echo) <= set(pitches[:16])
    bass_pitches = [37, 34, 29]
    rest, hold = len(lead_pitches), len(lead_pitches) + 1
    note_index = {name:index for index, name in enumerate(lead_pitches + ['R'])}
    lead = []
    for name in ('intro', 'ending'):
        tie = None
        for bar in score['patterns'][name]:
            tokens, tie, _ = compiler.pack_solo_bar(bar, note_index, hold, tie)
            lead.extend(tokens)
    by_unit = {}
    def add(unit, value):
        by_unit.setdefault(unit, []).append(value)
    for voice, segments in enumerate((echo, bass, strings), 1):
        incoming = {note['start'] for note in segments}
        for note in segments:
            if voice == 1:
                encoded = bytes([224 | pitch_index[note['pitch']]])
            elif voice == 2:
                encoded = bytes([241 + bass_pitches.index(note['pitch']) * 2])
            else:
                encoded = bytes([247, pitch_index[note['pitch']]])
            add(note['start'], (False, voice, encoded))
            if note['end'] not in incoming and note['end'] < bars * 16:
                add(note['end'], (True, voice, bytes([240 | 1 << voice])))
    stop = bars * 16
    add(stop, (True, 0, b'\xfe'))
    add(stop, (False, 1, bytes([224 | pitch_index[53]])))
    add(stop, (False, 2, b'\xf5'))
    add(stop, (False, 3, bytes([247, pitch_index[65]])))
    add(stop + 4, (True, 0, b'\xfe'))
    controls = {unit:b''.join(item[2] for item in sorted(events, key=lambda v:(not v[0], v[1])))
                for unit, events in by_unit.items()}
    output = bytearray()
    unit = 0
    for token in lead:
        remaining = DURATIONS[token & 7]
        pitch = token >> 3
        while remaining:
            output.extend(controls.pop(unit, b''))
            future = [point for point in controls if unit < point < unit + remaining]
            length = min(future) - unit if future else remaining
            fragment_left = length
            while fragment_left:
                duration = max(value for value in DURATIONS if value <= fragment_left)
                output.append(pitch << 3 | DURATIONS.index(duration))
                unit += duration
                fragment_left -= duration
                if pitch != rest:
                    pitch = hold
            remaining -= length
    assert not controls
    return bytes(output), dict(pitches=pitches, bassPitches=bass_pitches,
        restIndex=rest, holdIndex=hold, totalUnits=unit,
        sourceLeadNotes=len([n for n in notes if n[0] == 1]),
        sourceEchoNotes=echo_source, selectedEchoSegments=len(echo),
        sourceBassNotes=bass_source, selectedBassSegments=len(bass),
        sourceStringsNotes=strings_source, selectedStringsSegments=len(strings),
        echo=echo, bass=bass, strings=strings,
        sourceSha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        originalMidiSha256='065ea095a29a7086f736d9b61895ae3b35aa8950d980c045110145f8b2832321')


def bar_macro_stream(notes, ppqn, bpm):
    """Preserve the lead and bass; reduce echo to a source pitch per bar.

    A chord byte carries echo pitch (four bits) and one of the seven exact
    bass bar shapes (three bits). GM50 supplies a quiet harmonic pad from bar8.
    Every generated echo has an eighth-note gate; the pad changes per bar.
    """
    score = reader.create_score(notes, ppqn, bpm, 107, 107, 1, 4)
    score['patterns']['ending'] = ['F4:1 R:3']
    echo, source_echo = selected_segments(notes, ppqn, (2,3), 1712, 'latest')
    bass, source_bass = selected_segments(notes, ppqn, (4,), 1712, 'latest')
    echo_at_bar = [next((n['pitch'] for n in echo if n['start'] <= bar*16 < n['end']), None)
                   for bar in range(107)]
    # The first three entries are also the source-inspired pad voicings for
    # Db/Bb/F bass roots: F4/Eb4/C4. The echo uses only entries below15.
    pitches = [65,63,60]
    for pitch in sorted(set(echo_at_bar)-{None}):
        if pitch not in pitches:pitches.append(pitch)
    source_lead_pitches = sorted({compiler.midi(token.split(':')[0])
        for rows in score['patterns'].values() for bar in rows for token in bar.split()
        if not token.startswith('R:')})
    for pitch in source_lead_pitches:
        if pitch not in pitches:pitches.append(pitch)
    assert len(pitches)==17
    assert all(pitches.index(p)<15 for p in echo_at_bar if p is not None)
    pitches += [37,34,29]
    bass_pitches = [37,34,29]
    bass_glyphs = []
    for bar in range(107):
        begin,end = bar*16,(bar+1)*16
        attacks = [n for n in bass if begin<=n['start']<end]
        if not attacks:
            assert any(n['start']<begin and n['end']>=end for n in bass)
            glyph=3
        elif len(attacks)==1 and attacks[0]['start']==begin and attacks[0]['end']>=end:
            glyph=bass_pitches.index(attacks[0]['pitch'])
        else:
            assert [n['start']-begin for n in attacks]==[0,4,8,12]
            assert len({n['pitch'] for n in attacks})==1
            assert all(n['end']-n['start']==4 for n in attacks)
            glyph=4+bass_pitches.index(attacks[0]['pitch'])
        bass_glyphs.append(glyph)
    assert sum(4 if g&4 else int(g!=3) for g in bass_glyphs)==source_bass==345
    controls,records,bar_indices = {},[],[]
    def chord(pitch,glyph):
        value=(15 if pitch is None else pitches.index(pitch))|(glyph<<4)
        if value not in records:records.append(value)
        assert 9<=value<=111,value
        return 142+value
    for bar,(pitch,glyph) in enumerate(zip(echo_at_bar,bass_glyphs)):
        control=chord(pitch,glyph)
        # The quarter driver repeats the active macro independently. Repeating
        # its unchanged selector wastes Flash and changes no note or gate.
        if not bar_indices or records[bar_indices[-1]]!=control-142:
            controls[bar*16]=bytes([control])
        bar_indices.append(records.index(control-142))
    controls[1712]=bytes([chord(65,2)])
    controls[1716]=b'\xfe'
    assert len(records)<=30,(len(records),records)
    note_index={compiler.pname(pitch):index for index,pitch in enumerate(pitches[:17])}
    note_index['R']=17
    lead=[]
    for name in ('intro','ending'):
        tie=None
        for bar in score['patterns'][name]:
            tokens,tie,_=compiler.pack_solo_bar(bar,note_index,18,tie)
            lead.extend(tokens)
    output=bytearray();unit=0
    for token in lead:
        remaining=DURATIONS[token&7];pitch=token>>3
        while remaining:
            output.extend(controls.pop(unit,b''))
            future=[point for point in controls if unit<point<unit+remaining]
            length=min(future)-unit if future else remaining
            left=length
            while left:
                duration=max(value for value in DURATIONS if value<=left)
                output.append(pitch<<3|DURATIONS.index(duration))
                unit+=duration;left-=duration
                if pitch!=17:pitch=18
            remaining-=length
    assert not controls
    assert sum(token<151 and token>>3 not in (17,18) for token in output)==257
    return bytes(output),dict(pitches=pitches,bassPitches=bass_pitches,
        restIndex=17,holdIndex=18,totalUnits=unit,sourceLeadNotes=256,
        sourceEchoNotes=source_echo,sourceBassNotes=source_bass,
        chordRecords=records,barIndices=bar_indices,bassGlyphs=bass_glyphs,
        echoAtBar=echo_at_bar,mode='bar-macros',descriptorInline=True,timedTokenLimit=151,
        sourceSha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        originalMidiSha256='065ea095a29a7086f736d9b61895ae3b35aa8950d980c045110145f8b2832321',
        limitation='Echo principal pitch sampled from the source once per bar, then quarter pulses with eighth gates. Synth Strings 1 is a new source-inspired F4/Eb4/C4 harmonic pad, not an exact copy of track5. Lead and345 bass attacks retain the nearest-sixteenth source grid.')


def atoms(stream):
    """Keep F7+pitch together before the following timed main-note token."""
    result, pending = [], bytearray()
    cursor = 0
    while cursor < len(stream):
        token = stream[cursor]
        cursor += 1
        pending.append(token)
        if token == 247:
            pending.append(stream[cursor])
            cursor += 1
        elif token < 224:
            result.append(bytes(pending))
            pending.clear()
    if pending:
        raise ValueError('Trailing untimed controls')
    return result


def macro_atoms(stream):
    """Private atom boundary for offset142 descriptors; timed bytes <=150."""
    result=[];pending=bytearray()
    for token in stream:
        if token==255:raise ValueError('Source stream contains a section marker')
        pending.append(token)
        if token<151:result.append(bytes(pending));pending.clear()
    if pending:raise ValueError('Trailing untimed descriptor')
    return result


def six_state_source():
    """Adapt a snapshot of the current release kernel in this experiment only."""
    text = (ROOT / 'tools/children-native-template.S').read_text(encoding='utf-8')
    def region(start, end, function):
        nonlocal text
        a, b = text.index(start), text.index(end, text.index(start) + len(start))
        text = text[:a] + function(text[a:b]) + text[b:]
    region('envelope_loop:', '.L0a8:', lambda s:s.replace('  cpi r26, 121\n', '  cpi r26, 126\n'))
    region('voice_loop:', 'write_pwm:', lambda s:s.replace('  cpi r26, 121\n', '  cpi r26, 126\n')
        .replace('  sbrc r26, 4\n  asr r17\n', '  cpi r26, 117\n  brcs primary_gain\n  asr r17\n'))
    region('note_off:', 'chord_event:', lambda s:s.replace('  cpi r26, 111\n', '  cpi r26, 116\n'))
    region('capture_ram_tail:', '.include "score.inc"', lambda s:s
        .replace('  lds r17, 116\n', '  lds r17, 121\n')
        .replace('  lds r16, 111\n', '  lds r16, 116\n')
        .replace('  ldi r30, 116\n', '  ldi r30, 121\n')
        .replace('  ldi r30, 111\n', '  ldi r30, 116\n'))
    text = text.replace('  cpi r26, 101\n  brne piano_attack_done\n',
                        '  cpi r26, 107\n  brcc piano_attack_done\n')
    text = text.replace('state_plucked:\n', '''  sbrs r16, 5
  rjmp state_plucked
  sbrc r24, 0
  rjmp envelope_store
  cpi r17, 4
  breq envelope_store
  inc r16
  rjmp envelope_store
state_plucked:
''', 1)
    text=text.replace('state_release:\n','''state_release:
  sbrs r16, 5
  rjmp ordinary_release
  mov r25, r24
  andi r25, 7
  brne envelope_store
ordinary_release:
''',1)
    old = '  cpi r16, 240\n  brcs chord_event\n'
    assert old in text
    text = text.replace(old, '''  cpi r16, 240
  brcs echo_event
  sbrs r16, 0
  rjmp note_off
  cpi r16, 247
  breq strings_event
  rjmp bass_event
''', 1)
    region('chord_event:', 'melodic_event:', lambda s:'''chord_event:
echo_event:
  andi r16, 15
  ldi r26, 101
  ldi r25, 197
  rjmp companion_note
bass_event:
  andi r16, 7
  lsr r16
  subi r16, 239
  ldi r26, 106
  ldi r25, 147
  rjmp companion_note
strings_event:
  lpm r16, Z+
  ldi r26, 111
  ldi r25, 160
companion_note:
  movw r12, r30
  lsl r16
  ldi r30, lo8(note_steps)
  ldi r31, hi8(note_steps)
  add r30, r16
  adc r31, r29
  rcall initialize_voice
  movw r30, r12
  rjmp read_event
''')
    return text


def macro_source():
    """One main stream selects native companion bar macros at zero time."""
    text=six_state_source()
    def region(start,end,replacement):
        nonlocal text
        a=text.index(start);b=text.index(end,a+len(start))
        text=text[:a]+replacement+text[b:]
    text=text.replace('  clr r24\n','''  clr r24
  ldi r16, 255
  mov r8, r16
  mov r9, r16
  ldi r16, 128
  mov r14, r16
''',1)
    region('.L0c8:\n','melodic_event:', '''.L0c8:
  cpi r16, 151
  brcs melodic_event
  cpi r16, 254
  breq all_parts_off
chord_event:
  sbrs r14, 7
  rjmp macro_already_running
  ldi r17, 255
  mov r9, r17
macro_already_running:
  subi r16, 142
  mov r14, r16
  rjmp read_event
all_parts_off:
  ldi r26, 96
all_parts_off_loop:
  ld r16, X+
  andi r16, 127
  subi r26, 1
  st X+, r16
  subi r26, 252
  cpi r26, 116
  brne all_parts_off_loop
  ldi r16, 128
  mov r14, r16
  rjmp read_event
''')
    text=text.replace('grid_step:\n','grid_step:\n  inc r8\n',1)
    text=text.replace('.L0ba:\n  dec r1\n  breq read_event\n  ret\n',
        '.L0ba:\n  dec r1\n  breq read_event\n  rjmp companion_grid\n',1)
    text=text.replace('hold_sample:\n  ret\n','hold_sample:\n  rjmp companion_grid\n',1)
    text=text.replace('  sts 96, r17\n  ret\n','  sts 96, r17\n  rjmp companion_grid\n',1)
    text=text.replace('render_tone:\n','''companion_grid:
  sbrc r14, 7
  ret
  movw r12, r30
  mov r16, r8
  andi r16, 3
  breq companion_quarter
  cpi r16, 2
  brne companion_done
  lds r16, 101
  andi r16, 127
  sts 101, r16
  rjmp companion_done
companion_quarter:
  mov r16, r14
  andi r16, 15
  cpi r16, 15
  breq companion_bass
  ldi r26, 101
  ldi r25, 199
  rcall macro_note
companion_bass:
  sbrc r14, 6
  rjmp companion_bass_on
  mov r16, r8
  andi r16, 15
  brne companion_done
companion_bass_on:
  mov r16, r14
  swap r16
  andi r16, 3
  cpi r16, 3
  breq companion_strings
  subi r16, 239
  ldi r26, 106
  ldi r25, 147
  rcall macro_note
companion_strings:
  mov r16, r8
  andi r16, 15
  brne companion_done
  inc r9
  mov r16, r9
  cpi r16, 8
  brcs companion_done
  mov r16, r14
  swap r16
  andi r16, 3
  cpi r16, 3
  brne companion_pad_pitch
  ldi r16, 2
companion_pad_pitch:
  ldi r26, 111
  ldi r25, 160
  rcall macro_note
companion_done:
  movw r30, r12
  ret
macro_note:
  lsl r16
  ldi r30, lo8(note_steps)
  ldi r31, hi8(note_steps)
  add r30, r16
  adc r31, r29
  rjmp initialize_voice
render_tone:
''',1)
    # Binary peak masks preserve full lead15/echo7/bass3 attacks; the zero-cap
    # pad keeps half its old level alongside the half-gain release copy.
    text=text.replace('  mov r16, r25\n  subi r26, 1\n',
        '  andi r16, 15\n  lsr r16\n  or r16, r25\n  subi r26, 1\n',1)
    return optimize_macro_source(text)


def optimize_macro_source(text):
    """Fixed-cost DSP and cursor peepholes, checked against known source."""
    def replace(old,new):
        nonlocal text
        assert text.count(old)==1,old
        text=text.replace(old,new)
    replace('  lsl r16\n  ldi r30, lo8(note_steps)\n  ldi r31, hi8(note_steps)\n  add r30, r16\n  adc r31, r29\n  ldi r26, 96\n  ldi r25, 207\n  rcall initialize_voice\n',
            '  ldi r26, 96\n  ldi r25, 207\n  rcall macro_note\n')
    replace('  mov r16, r3\n  ldi r17, GRID_STEP_LOW\n  add r2, r17\n  ldi r17, GRID_STEP_HIGH\n  adc r16, r17\n  mov r3, r16\n',
            '  ldi r17, GRID_STEP_LOW\n  add r2, r17\n  ldi r17, GRID_STEP_HIGH\n  adc r3, r17\n')
    replace('  mov r0, r17\n  clr r17\n  sbrc r25, 0\n  add r17, r0\n  lsl r0\n  sbrc r25, 1\n  add r17, r0\n  lsl r0\n  sbrc r25, 2\n  add r17, r0\n  lsl r0\n  sbrc r25, 3\n  add r17, r0\n',
            '  mov r0, r17\n  sbrs r25, 3\n  clr r17\n  lsl r17\n  sbrc r25, 2\n  add r17, r0\n  lsl r17\n  sbrc r25, 1\n  add r17, r0\n  lsl r17\n  sbrc r25, 0\n  add r17, r0\n')
    replace('  mov r8, r16\n  mov r9, r16\n','  mov r8, r16\n')
    # R12:R13 remains the authoritative Flash cursor after each timed byte.
    replace('  lpm r1, Z\n  movw r30, r12\n','  lpm r1, Z\n')
    replace('  movw r12, r30\n  ldi r26, 96\n','  ldi r26, 96\n')
    replace('lead_commit:\n  movw r30, r12\n','lead_commit:\n')
    replace('companion_grid:\n  sbrc r14, 7\n  ret\n  movw r12, r30\n',
            'companion_grid:\n  movw r30, r12\n  sbrc r14, 7\n  ret\n')
    replace('  cpi r26, 117\n  brcs primary_gain\n  asr r17\n',
            '  sbrc r26, 4\n  asr r17\n')
    replace('  asr r17\n  rjmp envelope_return\n',
            '  asr r17\n  asr r17\n  ret\n')
    # The two piano records have bit4 clear at their end pointers. Bass,
    # strings and both release slots have bit4 set, giving fixed half gain.
    def shift(m):
        address=int(m[2])
        return m[1]+str(address+1) if 96<=address<=126 else m[0]
    text=re.sub(r'(?m)(  (?:ldi r26, |ldi r30, |cpi r26, |lds r\d+, |sts ))(\d+)',shift,text)
    text=text.replace('  ldi r25, 147\n','  ldi r25, 151\n')
    replace('  cpi r17, 4\n  breq envelope_store\n',
            '  cpi r17, 7\n  breq envelope_store\n')
    return text


def assemble(packed, metadata):
    release = module('children_four_release', ROOT / 'tools/build-release-engine.py')
    builder = module('children_four_builder', ROOT / 'tools/build-rhythmic.py')
    names = {value:[] for value in packed['offsets'].values()}
    for name, offset in packed['offsets'].items():
        names[offset].append('section_' + name)
    names.setdefault(packed['offsets'][packed['playlist'][0]], []).append('first_section')
    playlist = [packed['offsets'][name] for name in packed['playlist']]
    rows = ['playlist:', '  .byte ' + ','.join(map(str, playlist)),
            'durations:', '  .byte ' + ','.join(map(str, DURATIONS)), 'note_steps:']
    # Bass control F1/F3/F5 indexes the three-note table in this fixed order.
    assert metadata['pitches'][17:20] == metadata['bassPitches']
    for pitch in metadata['pitches']:
        step = round(440 * 2 ** ((pitch - 69) / 12) * 65536 / 18750)
        # Bit7 of the high byte is the piano's measured fast-decay register
        # flag, masked out of DDS by the renderer before phase addition.
        rows.append(f'  .byte {step & 255},{(step >> 8) | (128 if pitch >= 75 else 0)}')
    if 'chordRecords' in metadata and not metadata.get('descriptorInline'):
        rows.extend(['chord_controls:','  .byte '+','.join(map(str,metadata['chordRecords']))])
    rows.append('melody_data:')
    for index, token in enumerate(packed['storage']):
        rows.extend(name + ':' for name in names.get(index, []))
        rows.append(f'  .byte {token}')
    score='code_end:\n'+'\n'.join(rows)+'\n'
    (OUT / 'score.inc').write_text(score, encoding='utf-8', newline='\n')
    step = round(140 * 4 / 60 / (37500 / 512) * 65536)
    constants = dict(REST_INDEX=metadata['restIndex'], HOLD_INDEX=metadata['holdIndex'],
        PLAYLIST_LEN=len(playlist), FIRST_PLAYLIST_INDEX=int(len(playlist) > 1),
        GRID_STEP_LOW=step & 255, GRID_STEP_HIGH=step >> 8,
        GRID_INITIAL_HIGH=math.ceil((65536 - step) / 256))
    (OUT / 'config.inc').write_text(''.join(f'.set {k}, {v}\n' for k,v in constants.items()), encoding='utf-8', newline='\n')
    source=macro_source() if metadata.get('mode')=='bar-macros' else six_state_source()
    if metadata.get('mode')=='bar-macros':
        source,score,proof=page_local_tables(source,score,playlist,release)
        metadata['pageLocalProof']=proof
    (OUT / 'synth.S').write_text(source, encoding='utf-8', newline='\n')
    (OUT / 'score.inc').write_text(score, encoding='utf-8', newline='\n')
    rom, labels = release.assemble_relaxed(OUT / 'synth.S')
    for check in metadata.get('pageLocalProof',{}).get('removedCarries',[]):
        assert labels[check['table']]%256+check['length']<=256,check
    (OUT / 'synth.bin').write_bytes(rom)
    (OUT / 'synth.hex').write_text(builder.ihex(rom), encoding='utf-8', newline='\n')
    return len(rom), labels


def page_local_tables(source,score,playlist,release):
    """Remove address carries only after proving the final access ranges."""
    prefix=score[:score.index('playlist:')]
    blocks={}
    for name,nextname in [('playlist','durations'),('durations','note_steps'),('note_steps','melody_data')]:
        blocks[name]=score[score.index(name+':'):score.index(nextname+':')]
    body=score[score.index('melody_data:'):]
    limits={'playlist':len(playlist),'durations':len(DURATIONS),
            'note_steps':len(re.findall(r'  \.byte',blocks['note_steps'])),
            'melody_data':max(playlist)+1}
    # note_steps consists of two bytes per row.
    limits['note_steps']*=2
    best=None
    for order in itertools.permutations(blocks):
        arranged=prefix+''.join(blocks[name] for name in order)+body
        (OUT/'score.inc').write_text(arranged,encoding='utf-8',newline='\n')
        candidate=source;removed=[]
        for iteration in range(4):
            (OUT/'synth.S').write_text(candidate,encoding='utf-8',newline='\n')
            rom,labels=release.assemble_relaxed(OUT/'synth.S')
            candidate=(OUT/'synth.S').read_text(encoding='utf-8')
            changed=False
            for name,length in limits.items():
                if labels[name]%256+length>256:continue
                for register in ('r4','r16','r17'):
                    old=f'  ldi r30, lo8({name})\n  ldi r31, hi8({name})\n  add r30, {register}\n  adc r31, r29\n'
                    if old in candidate:
                        candidate=candidate.replace(old,old.rsplit('  adc',1)[0])
                        removed.append(dict(table=name,length=length));changed=True
            if not changed:break
        (OUT/'synth.S').write_text(candidate,encoding='utf-8',newline='\n')
        rom,labels=release.assemble_relaxed(OUT/'synth.S')
        candidate=(OUT/'synth.S').read_text(encoding='utf-8')
        if any(labels[item['table']]%256+item['length']>256 for item in removed):continue
        result=(len(rom),candidate,arranged,dict(tableOrder=order,removedCarries=removed))
        if best is None or result[0]<best[0]:best=result
    assert best,'No safe page-local table layout'
    return best[1:]


def write_eeprom():
    bank=module('children_four_instruments',ROOT/'tools/instrument-bank.py')
    builder=module('children_four_hex',ROOT/'tools/build-rhythmic.py')
    data=bank.load_bank()
    profile=json.loads((ROOT/'ATtiny13A/Music/instruments/children-synth-strings-profile.json').read_text(encoding='utf-8'))['profile']
    if 'synth-strings-1' in data['instruments']:
        assert data['instruments']['synth-strings-1']['waves']==profile['waves']
    else:
        # Feasibility builds may precede promotion of this measured sidecar.
        data['instruments']['synth-strings-1']=profile
    eeprom=bank.build_eeprom(dict(lead='acoustic-grand-piano',keys='fretless-bass',
                                pluck='synth-strings-1',percussion='off'),data)
    (OUT/'eeprom.bin').write_bytes(eeprom)
    (OUT/'eeprom.hex').write_text(builder.ihex(eeprom),encoding='utf-8',newline='\n')
    return hashlib.sha256(eeprom).hexdigest()


def write_kernel_fixture(metadata):
    """A small, physically fitting stress score for the same six-state code."""
    release=module('children_four_fixture_assembler',ROOT/'tools/build-release-engine.py')
    fixture=OUT/'fixture';fixture.mkdir(parents=True,exist_ok=True)
    source=(OUT/'synth.S').read_text(encoding='utf-8')
    (fixture/'synth.S').write_text(source,encoding='utf-8',newline='\n')
    config=(OUT/'config.inc').read_text(encoding='utf-8')
    import re
    config=re.sub(r'(?m)^\.set PLAYLIST_LEN, \d+$','.set PLAYLIST_LEN, 1',config)
    config=re.sub(r'(?m)^\.set FIRST_PLAYLIST_INDEX, \d+$','.set FIRST_PLAYLIST_INDEX, 0',config)
    (fixture/'config.inc').write_text(config,encoding='utf-8',newline='\n')
    score=(OUT/'score.inc').read_text(encoding='utf-8').split('melody_data:')[0]
    # Keep the full playlist padding so proved table addresses stay identical.
    score=re.sub(r'(playlist:\n  \.byte )\d+',r'\g<1>0',score)
    chord=142+(metadata['pitches'].index(79)|(6<<4))
    note=metadata['pitches'].index(77)<<3
    score+='melody_data:\nfirst_section:\n  .byte '+','.join(map(str,[chord,note,note,note,note,255]))+'\n'
    (fixture/'score.inc').write_text(score,encoding='utf-8',newline='\n')
    rom,labels=release.assemble_relaxed(fixture/'synth.S')
    assert len(rom)<=1024,len(rom)
    (fixture/'synth.bin').write_bytes(rom)
    shutil.copyfile(OUT/'eeprom.bin',fixture/'eeprom.bin')
    (fixture/'labels.json').write_text(json.dumps(labels,indent=2)+'\n',encoding='utf-8',newline='\n')
    (OUT/'check-kernel.mjs').write_text(KERNEL_CHECK,encoding='utf-8',newline='\n')
    return len(rom)


KERNEL_CHECK='''import fs from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore} from '../../web-player/lib/avr-core.js';
const read=name=>fs.readFileSync(new URL('./fixture/'+name,import.meta.url));
const labels=JSON.parse(read('labels.json'));
const c=new AVRCore(read('synth.bin'),read('eeprom.bin'));
const step=c.step.bind(c),signed=n=>n&128?n-256:n;
let render=null,maxRender=0,maxActive=0,underruns=0,minQueued=16,sixActive=0,mixes=0,maxStack=0;
let sum=0,mixMin=127,mixMax=-128;
const voiceAddresses=[97,102,107,112,117,122];
c.step=()=>{
 if(!c.inIRQ){
  if(c.pc===labels.render_sample/2){render={cycle:c.cyc,irqs:c.irqCount};sum=0;mixes++;
   if(voiceAddresses.every(a=>(c.data[a]&15)!==0))sixActive++;
  }
  if(c.pc===labels.primary_gain/2)sum+=signed(c.r[17]);
  if(c.pc===labels.write_pwm/2){assert.equal(signed(c.r[21]),sum);assert.ok(sum>=-128&&sum<=127);mixMin=Math.min(mixMin,sum);mixMax=Math.max(mixMax,sum);}
 }
 if(c.inIRQ&&c.pc===labels.ring_read/2){const queued=(c.r[22]-c.r[28]+16)%16;minQueued=Math.min(minQueued,queued);if(!queued)underruns++;}
 step();
 if(!c.inIRQ&&c.pc===labels.idle/2&&render){const elapsed=c.cyc-render.cycle;maxRender=Math.max(maxRender,elapsed);maxActive=Math.max(maxActive,elapsed-c.maxIRQ*(c.irqCount-render.irqs));render=null;}
 maxStack=Math.max(maxStack,159-c.minSP);
};
while(c.cyc<20*9600000)c.nextDuty();
const report={fixtureFlashBytes:read('synth.bin').length,coreBytes:labels.code_end,emulatedSeconds:c.cyc/9600000,mixes,sixActiveRenderedPoints:sixActive,maxRenderElapsedCycles:maxRender,maxRenderActiveCycles:maxActive,isrCycles:c.maxIRQ,underruns,minQueued,lost:c.lost,workLost:c.workLost,maxStackBytes:maxStack,mixRange:[mixMin,mixMax],scope:'Physical <=1KB synthetic quarter-note fixture for six-state DSP and PWM deadlines; not full Children arrangement verification.'};
fs.writeFileSync(new URL('./kernel-validation.json',import.meta.url),JSON.stringify(report,null,2)+'\\n');
console.log(JSON.stringify(report,null,2));
assert.ok(sixActive>0);assert.equal(underruns,0);assert.equal(c.lost+c.workLost,0);assert.ok(maxRender<512);assert.ok(c.minSP>=144);
'''


def build(folder=None,candidates=4096,production=False,mode='bar-macros'):
    global OUT
    OUT=Path(folder) if folder and not production else ROOT/'build/children-four'
    notes, ppqn, bpm = reader.read_midi(SOURCE)
    stream, metadata = (bar_macro_stream if mode=='bar-macros' else musical_stream)(notes, ppqn, bpm)
    packing.atoms = macro_atoms if mode=='bar-macros' else atoms
    packed = packing.pack(stream, [stream], candidate_limit=candidates, max_entry_offset=255)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'source-stream.bin').write_bytes(stream)
    (OUT / 'packed-stream.bin').write_bytes(packed['storage'])
    table_bytes = 7 + len(metadata['pitches']) * 2
    if not metadata.get('descriptorInline'):table_bytes+=len(metadata.get('chordRecords',[]))
    flash_bytes, labels = assemble(packed, metadata)
    eeprom_sha256=write_eeprom()
    fixture_bytes=write_kernel_fixture(metadata) if mode=='bar-macros' else None
    report = dict(experimental=True, primaryVoices=4, releaseVoices=2,
        sourceQuarterBeats=428, cadenceQuarterBeats=4, tempoBpm=bpm,
        sourceCommandBytes=len(stream), packedDataBytes=len(packed['storage']) + len(packed['playlist']) + table_bytes,
        fixedTableBytes=table_bytes, sourceSha256=metadata['sourceSha256'],
        actualCodeBytes=labels['code_end'], actualFlashBytes=flash_bytes,
        eepromSha256=eeprom_sha256,kernelFixtureFlashBytes=fixture_bytes,
        fitsFlash=flash_bytes <= 1024, packing=packed['report'], labels=labels,
        maximumEntryOffset=max(packed['offsets'].values()),
        layout=dict(stateBytes=30, stateAddresses=[97,102,107,112,117,122],
                    pwmRingStart=128, pwmRingBytes=16, stackBudgetBytes=8, totalBytes=54),
        voices=[dict(role='main-piano', tracks=[1], program=0, level=15, eeprom=0),
                dict(role='piano-echo', tracks=[2,3], program=0, level=7, eeprom=0),
                dict(role='bass', tracks=[4], program=35, level=7, gain=0.5, eeprom=16),
                dict(role='strings', tracks=[5], program=50, level=7, gain=0.5, eeprom=32)],
        metadata=metadata)
    (OUT / 'feasibility.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    if production:
        assert mode=='bar-macros' and report['fitsFlash']
        target=Path(folder or BASE);target.mkdir(parents=True,exist_ok=True)
        for name in ('synth.S','synth.bin','synth.hex','eeprom.bin','eeprom.hex','config.inc','score.inc'):
            shutil.copyfile(OUT/name,target/name)
        publish(target,notes,ppqn,bpm,stream,packed,report)
    print(json.dumps({key:value for key,value in report.items() if key not in ('metadata','labels')}, indent=2))
    return report


def publish(folder,notes,ppqn,bpm,stream,packed,native):
    """Keep ordinary build artifacts and provenance for the native codec."""
    bank=module('children_native_bank',ROOT/'tools/instrument-bank.py')
    legacy=module('children_metadata_helper',ROOT/'tools/arrange-children.py')
    profiles=bank.load_bank()['instruments'];metadata=native['metadata'];labels=native['labels']
    def text(name,value):(folder/name).write_text(value,encoding='utf-8',newline='\n')
    def json_text(name,value):text(name,json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    sha=lambda value:hashlib.sha256(value).hexdigest()
    instruments=dict(lead='acoustic-grand-piano',keys=dict(instrument='fretless-bass',level=7),
                     pluck=dict(instrument='synth-strings-1',level=7),percussion='off')
    source=legacy.source_metadata(notes,ppqn)
    score=reader.create_score(notes,ppqn,bpm,107,107,1,4)
    score['patterns']['ending']=['F4:1 R:3'];score['playlist'].append('ending')
    score.update(engine='children-native',title='04 · Robert Miles — Children',
        instruments=instruments,instrument_slots_are='EEPROM wave banks, not the four physical main voices',
        active_primary_voices=4,primary_voice_assignments=native['voices'],release_tail_slots=2,
        packing_candidates=native['packing']['candidateLimit'],percussion_enabled=False,
        lead_envelope_model='piano',lead_retrigger='full',lead_max_level=15,lead_release_step=2,
        keys_envelope_model='pluck',keys_retrigger='full',keys_max_level=7,keys_gain=.5,
        pluck_envelope_model='sustain',pluck_retrigger='half',pluck_max_level=7,pluck_gain=.5,
        pluck_attack_step=1,pluck_attack_mask=1,pluck_release_step=1,pluck_release_mask=7,
        source_midi=source,bass_source_note_ons=345,
        arrangement=dict(firstSourceQuarterBeat=0,sourceQuarterBeats=428,sourceLeadNotes=256,
            sourceBassNotes=345,totalQuarterBeats=432,durationSeconds=432*60/bpm,
            rhythm='Nearest-sixteenth source grid; all256 main piano and345 bass attack identities/gates preserved; constant140BPM.',
            reduction=metadata['limitation'],loopSilence='One-beat cadence followed by three beats rest; all six voice levels zero before every restart.'))
    assignments=bank.describe_assignments(instruments)
    rom=(folder/'synth.bin').read_bytes();ep=(folder/'eeprom.bin').read_bytes()
    assert ep==bank.build_eeprom(instruments)
    report=dict(engine='children-native',activePrimaryVoices=4,flashBytes=len(rom),codeBytes=labels['code_end'],
        tableBytes=len(rom)-labels['code_end'],eepromBytes=64,flashSha256=sha(rom),eepromSha256=sha(ep),labels=labels,
        instrumentBankSha256=sha(bank.BANK_PATH.read_bytes()),instrumentAssignments=assignments,
        primaryVoiceAssignments=native['voices'],sourceScoreSha256=source['sha256'],
        score=dict(note_count=257,event_bytes=len(packed['storage']),playlist_bytes=len(packed['playlist']),
            note_table_bytes=40,chord_table_bytes=0,durations=list(DURATIONS),
            pitches=[compiler.pname(n) for n in metadata['pitches'][:17]]+['R','HOLD'],
            dds_pitches=[compiler.pname(n) for n in metadata['pitches']],rest_index=17,hold_index=18,
            source_playlist=['intro','ending'],playlist=packed['playlist'],section_offsets=packed['offsets'],
            maximum_entry_offset=max(packed['offsets'].values()),total_data_bytes=len(rom)-labels['code_end'],
            compression=packed['report'],source_note_ons=256,source_bass_note_ons=345),
        timing=dict(phaseStep=labels['GRID_STEP_LOW']|(labels['GRID_STEP_HIGH']<<8),phaseBits=16,
            envelopeTickCycles=131072,tempoBpm=bpm,actualTempoBpm=(labels['GRID_STEP_LOW']|(labels['GRID_STEP_HIGH']<<8))/65536*(37500/512)*60/4,
            sharedGrid='One sixteenth counter drives all four main voices and finite gates'),
        articulation=dict(attack='piano/piano/pluck/sustain',retrigger='Piano and bass peak; pad half-current attack',phaseContinuous=True),
        releaseChannels=dict(primaryVoices=4,tailSlots=2,voiceAddresses=[97,102,107,112,117,122],
            voiceStateBytes=30,pwmRingBytes=16,tailGain=.5,stealing='Quietest of two release levels',
            phaseContinuous=True,isrCycles=15,requiredFuses=dict(low='0x7A',high='0xFF')),
        native=dict(native,sourceStream=list(stream)))
    json_text('score.json',score);json_text('build-report.json',report)
    json_text('waveforms.json',dict(source='Shared measured FluidR3 build-time bank',bankSha256=report['instrumentBankSha256'],
        slots={role:dict(instrument=assignments[role]['instrument'],waves=profiles[assignments[role]['instrument']]['waves'])
               for role in ('lead','keys','pluck')},
        pianoTransient=profiles['acoustic-grand-piano']['transient']))
    html=(ROOT/'tools/player-template.html').read_text(encoding='utf-8')
    for key,value in [('AVR_CORE',(folder/'avr_core.js').read_text(encoding='utf-8')),
                      ('FIRMWARE_HEX',(folder/'synth.hex').read_text(encoding='utf-8')),
                      ('EEPROM_HEX',(folder/'eeprom.hex').read_text(encoding='utf-8'))]:
        html=html.replace('/*'+key+'*/',value)
    text('player.html',html.replace('ATtiny13A — проигрыватель AVR-прошивки','ATtiny13A — '+score['title']))
    json_text('../../reference/children/metadata.json',source)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates',type=int,default=4096)
    parser.add_argument('--mode',choices=('dense','bar-macros'),default='bar-macros')
    parser.add_argument('--production',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    build(args.output,args.candidates,args.production,args.mode)


if __name__ == '__main__':
    main()

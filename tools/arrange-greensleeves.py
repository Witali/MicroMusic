"""Reproduce the complete Z80 example's Greensleeves for the ATtiny13A.

The Public Domain LilyPond soprano is checked against the unchanged source MIDI.
Keep the 6/8 meter and eighth-note pickup; no music is removed to make it fit.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import re

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'ATtiny13A/Music/reference/greensleeves'
OUT = ROOT / 'ATtiny13A/Music/variants/greensleeves'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def voice(source, name, next_name):
    text = source.split(name + ' =', 1)[1].split(next_name, 1)[0]
    text = text.split(r'\key g \major', 1)[1].split(r'\bar', 1)[0]
    events = []
    length = 8
    position = 0
    for match in re.finditer(r"(?<![a-z])([a-g](?:is|es)?|[rs])([',]*)(\d+)?(\.)?", text):
        note, octave, duration, dot = match.groups()
        length = int(duration) if duration else length
        units = 16 // length
        if dot:
            assert units % 2 == 0
            units = units * 3 // 2
        pitch = None if note in ('r', 's') else (
            48 + {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7, 'a': 9, 'b': 11}[note[0]]
            + note.count('is') - note.count('es')
            + 12 * (octave.count("'") - octave.count(',')))
        events.append(dict(pitch=pitch, start=position, units=units, spacer=note == 's'))
        position += units
    return events


def pack_bar_6_8(compiler, bar, chords, note_index, chord_index, hold_index,
                previous_tie=None, note_off=None):
    """The shared bytecode needs no decoder change for three-beat bars."""
    tokens = []
    for piece in bar.split():
        note, duration = piece.split(':')
        tokens.append((note, round(float(duration.rstrip('~')) * 4), duration.endswith('~')))
    bar_units = sum(n for _, n, _ in tokens)
    assert bar_units in (2, 10, 12), (bar_units, bar)
    out, holds = [0xe0 | chord_index[chords[0]]], []
    position, chord_sent = 0, False
    for i, (note, duration, tied) in enumerate(tokens):
        continuing = i == 0 and previous_tie == note and note != 'R'
        remaining = duration
        while remaining:
            if position == 6 and not chord_sent:
                out.append(0xe0 | chord_index[chords[1]])
                chord_sent = True
            boundary = 6 if position < 6 and bar_units > 6 else bar_units
            until = min(remaining, boundary - position)
            assert until > 0
            for fragment in compiler.split_durations(until / 4):
                index = hold_index if continuing and note != 'R' else note_index[note]
                out.append(index << 3 | compiler.BEATS.index(fragment))
                if index == hold_index:
                    holds.append(dict(pitch=note, beat=position / 4))
                continuing = True
            position += until
            remaining -= until
        previous_tie = note if tied else None
    return out, previous_tie, holds


def main():
    midi = module('greensleeves_midi', ROOT / 'tools/midi-reader.py')
    builder = module('greensleeves_build', ROOT / 'tools/build-rhythmic.py')
    bank = module('greensleeves_bank', ROOT / 'tools/instrument-bank.py')
    compiler = builder.compiler
    source = (REFERENCE / 'greensleeves.ly').read_text(encoding='utf-8')
    melody = voice(source, 'Soprano', 'Alto =')
    alto = voice(source, 'Alto', 'Tenor =')
    bass = voice(source, 'Bass', r'\score')
    # A final s8 is a LilyPond layout spacer, not a played note. The closing
    # incomplete bar and opening pickup together make one full 6/8 measure.
    assert melody[-1]['spacer'] and melody[-1]['units'] == 2
    melody = melody[:-1]
    notes, ppqn, tempo = midi.read_midi(REFERENCE / 'greensleeves.mid')
    source_notes = {(n[2], round(n[3] * 4 / ppqn), round((n[4] - n[3]) * 4 / ppqn)) for n in notes}
    legato_overlaps = []
    for note in melody:
        if note['pitch'] is not None:
            signature = (note['pitch'], note['start'], note['units'])
            if signature not in source_notes:
                # LilyPond's parenthesized D4/E4 legato extends D4 under E4 in
                # the MIDI. Keep the written monophonic durations on one DDS.
                assert signature == (62, 164, 3) and (62, 164, 4) in source_notes, note
                legato_overlaps.append(dict(pitch='D4', start_unit=164,
                                           midi_units=4, written_units=3))
    end = melody[-1]['start'] + melody[-1]['units']
    assert end == 192 and tempo == 60
    boundaries = [(0, 2)] + [(start, min(start + 12, end)) for start in range(2, end, 12)]
    patterns, pairs, chord_notes = {}, {}, {}
    for bar_index, (start, stop) in enumerate(boundaries):
        name = 'pickup' if bar_index == 0 else f'bar_{bar_index:02d}'
        pieces = []
        for note in melody:
            left, right = max(start, note['start']), min(stop, note['start'] + note['units'])
            if left >= right:
                continue
            pitch = compiler.pname(note['pitch'])
            tie = '~' if right < note['start'] + note['units'] and pitch != 'R' else ''
            pieces.append(f'{pitch}:{(right - left) / 4:g}{tie}')
        patterns[name] = [' '.join(pieces)]
        harmony = []
        for point in (start, min(start + 6, stop - 1)):
            violin = next(n for n in alto if n['start'] <= point < n['start'] + n['units'])['pitch']
            cello = next(n for n in bass if n['start'] <= point < n['start'] + n['units'])['pitch']
            assert violin is not None and cello is not None
            chord = compiler.pname(violin) + '/' + compiler.pname(cello)
            harmony.append(chord)
            chord_notes[chord] = [violin, cello]
        pairs[name] = [harmony]
    levels = dict(lead=15, keys=12, pluck=10)
    assignments = {role: dict(instrument=instrument, level=levels[role])
                   for role, instrument in dict(lead='flute', keys='violin', pluck='cello').items()}
    (OUT / 'waveforms.json').write_text(json.dumps(bank.describe_assignments(assignments), indent=2,
                                                  ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    data = dict(title='04 · Greensleeves', composers=['Traditional'], tempo_bpm=tempo,
                engine='instrument-bank',
                beats_per_bar=3, meter='6/8', pickup_beats=0.5, closing_bar_beats=2.5,
                percussion_grid_units=6, percussion_first_unit=2,
                percussion_meter_units=12, percussion_initial_counter=9,
                percussion_enabled=False,
                instruments=dict(**assignments, percussion='off'),
                playlist=list(patterns), patterns=patterns,
                chord_pairs=[pairs['pickup'][0]], chord_overrides=pairs,
                chord_notes=chord_notes, packing_candidates=4096,
                provenance=dict(source='Z80 player MIDI example',
                    source_repository='C:/Work/z80-tester',
                    midi='ATtiny13A/Music/reference/greensleeves/greensleeves.mid',
                    z80_example='ATtiny13A/Music/reference/greensleeves/greensleeves-4voices.mid',
                    z80_programs_zero_based=dict(soprano_flute=73, alto_violin=40,
                                                tenor_clarinet=71, bass_cello=42),
                    original_midi_program_changes=0,
                    lilypond='ATtiny13A/Music/reference/greensleeves/greensleeves.ly',
                    license='Public Domain', edition='Mutopia-2014/03/30-1247',
                    credit='Traditional; typeset by Steve Dunlop',
                    sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(REFERENCE.glob('greensleeves*'))}),
                adaptation=dict(complete_melody=True, source_melody_events=len(melody),
                    source_melody_pitched_notes=sum(n['pitch'] is not None for n in melody),
                    source_midi_legato_overlaps_reduced_to_written_duration=legato_overlaps,
                    final_layout_spacer_omitted_beats=0.5,
                    total_quarter_beats=end / 4, source_midi_tempo_bpm=tempo,
                    description='Complete played soprano, written pitches/onsets/durations and eighth-note pickup. '
                    'Flute73 matches the actual Z80 player example; violin40 and cello42 follow '
                    'the written Alto/Bass pitches sampled at dotted-quarter boundaries. Clarinet71 '
                    'Tenor is omitted to fit three tonal oscillators. No invented guitar or percussion. '
                    'The original two-staff MIDI has no ProgramChange; the actual Z80 four-channel '
                    'example explicitly sets flute/violin/clarinet/cello. Final LilyPond s8 '
                    'layout spacer is omitted so the 2.5-beat closing bar and 0.5-beat pickup loop in 6/8.'),
                note_format='Quarter-note beats on a sixteenth grid. Three beats = one 6/8 bar; '
                            'pickup = 0.5 beat. ~ continues a note across a bar boundary.')
    (OUT / 'score.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    builder.build(OUT)
    report_path = OUT / 'build-report.json'
    report = json.loads(report_path.read_text())
    report['timing']['sharedGrid'] = 'One sixteenth grid; 6/8 bars and dotted-quarter accompaniment after an eighth-note pickup'
    report['timing']['percussionEnabled'] = False
    report['timing']['meter'] = '6/8'
    report['instruments'] = data['instruments']
    report['score']['instruments'] = data['instruments']
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()

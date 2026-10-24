"""Reproduce the complete Z80 example's Greensleeves for the ATtiny13A.

The Public Domain LilyPond soprano is checked against the complete retained MIDI-event JSON.
Keep the 6/8 meter and eighth-note pickup; no music is removed to make it fit.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import argparse

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
    # The closing written ten units gain a one-unit, outside-meter loop gap.
    assert bar_units in (2, 10, 11, 12), (bar_units, bar)
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
    parser = argparse.ArgumentParser(description='Retain all four complete Greensleeves source parts')
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    reader = module('greensleeves_four_reader', ROOT / 'tools/midi-reader.py')
    engine = module('greensleeves_four_engine', ROOT / 'tools/build-compact-four.py')
    path = REFERENCE / 'greensleeves-4voices-events.json'
    notes, ppqn, tempo = reader.read_midi(path)
    assignments = [('soprano', 'flute', 15), ('alto', 'violin', 12),
                   ('tenor', 'clarinet', 11), ('bass', 'cello', 10)]
    parts = []
    for track, (name, instrument, level) in enumerate(assignments):
        selected = []
        for source_index, note in enumerate(notes):
            index, channel, pitch, on, off, velocity = note
            if index != track:
                continue
            assert on * 4 % ppqn == off * 4 % ppqn == 0
            selected.append(dict(pitch=pitch, on=on*4//ppqn, off=off*4//ppqn,
                                 velocity=velocity, sourceIndex=source_index))
        parts.append(dict(name=name, instrument=instrument, level=level,
                          sourceTrack=track, channel=track, notes=selected))
    assert [len(part['notes']) for part in parts] == [70, 52, 58, 55]
    score = dict(engine='compact-four', title='05 · Greensleeves', composers=['Traditional'],
                 tempo_bpm=tempo, endUnit=192, meter='6/8', pickup_beats=.5,
                 closing_bar_beats=2.5, loop_silence_beats=.25,
                 description='Полные партии флейты, скрипки, кларнета и виолончели: все 235 исходных нот.',
                 parts=parts, percussion_enabled=False,
                 provenance=dict(file='../../reference/greensleeves/greensleeves-4voices-events.json',
                     sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                     originalMidiSha256=json.loads(path.read_text(encoding='utf-8'))['source']['sha256'],
                     ppqn=ppqn, license='Public Domain', edition='Mutopia-2014/03/30-1247',
                     credit='Traditional; typeset by Steve Dunlop; Z80 four-voice example'),
                 adaptation=dict(complete_source=True, source_notes=235, played_notes=235,
                     note_timing='Every source NoteOn and NoteOff retained exactly on the sixteenth grid.',
                     source_velocity='All source notes use velocity90; each instrument has a fixed musical mix level.',
                     description='All four original independent voices retained, including the previously omitted clarinet tenor and unsampled Alto/Bass notes. The soprano follows the retained four-voice example, whose tied D4 is one continuous note. No added percussion.'))
    engine.build_normalized(args.output, score)


if __name__ == '__main__':
    main()

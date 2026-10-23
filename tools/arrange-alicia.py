"""Preserve Alicia's complete melody and source timing in a small piano firmware.

The source mixes 3/4 and 4/4 at 78/58/87 BPM. Exact rational event times are
quantized onto a 43.103-ms grid (the unchanged decoder's 348-BPM sixteenths).
Four-quarter storage blocks are an encoding detail, not rewritten musical bars.
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
REFERENCE = ROOT / 'ATtiny13A/Music/reference/alicia'
SOURCE = REFERENCE / 'source-score.json'
OUT = ROOT / 'ATtiny13A/Music/variants/alicia'
BASE = ROOT / 'ATtiny13A/Music/variants/rhythmic'
GRID_BPM = 348
GRID_HZ = Fraction(GRID_BPM, 15)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


builder = module('alicia_builder', ROOT / 'tools/build-rhythmic.py')


def read_timeline(data):
    events, bars, sections = [], [], []
    cursor = Fraction()
    for playlist_index, name in enumerate(data['playlist']):
        pattern = data['patterns'][name]
        tempo = Fraction(str(pattern['tempo_bpm']))
        section_start = cursor
        for bar_index, bar in enumerate(pattern['bars']):
            beats = Fraction(str(bar.get('beats', pattern['beats_per_bar'])))
            transpose = bar.get('lead_transpose', pattern.get('lead_transpose', 0))
            source_instrument = bar.get('lead_instrument', pattern.get('lead_instrument', 1))
            position = Fraction()
            for token in bar['melody'].split():
                pitch, duration_text = token.split(':')
                duration = Fraction(duration_text)
                if duration <= 0:
                    raise ValueError('A source event must have positive duration')
                note = builder.compiler.midi(pitch)
                if note is not None:
                    note += transpose
                start = cursor + position * 60 / tempo
                end = start + duration * 60 / tempo
                events.append(dict(identity=len(events), playlistIndex=playlist_index, pattern=name,
                                   bar=bar_index, sourcePitch=pitch, sourceDuration=str(duration),
                                   sourceInstrument=source_instrument, transpose=transpose,
                                   midi=note, pitch=builder.compiler.pname(note),
                                   startSeconds=str(start), endSeconds=str(end)))
                position += duration
            if position != beats:
                raise ValueError(f'{name}/{bar_index}: {position} beats, expected {beats}')
            bars.append(dict(playlistIndex=playlist_index, pattern=name, bar=bar_index,
                             meter=f'{pattern["beats_per_bar"]}/4', actualQuarterBeats=str(beats),
                             tempoBpm=float(tempo), startSeconds=str(cursor),
                             endSeconds=str(cursor + beats * 60 / tempo)))
            cursor += beats * 60 / tempo
        sections.append(dict(playlistIndex=playlist_index, pattern=name, tempoBpm=float(tempo),
                             sourceMeter=f'{pattern["beats_per_bar"]}/4',
                             startSeconds=str(section_start), endSeconds=str(cursor)))
    return dict(events=events, bars=bars, sections=sections, durationSeconds=str(cursor))


def make_score(timeline, candidates, grid_bpm=GRID_BPM):
    events = timeline['events']
    grid_hz = Fraction(grid_bpm, 15)
    cells = []
    maximum_error = Fraction()
    for event in events:
        start = Fraction(event['startSeconds'])
        end = Fraction(event['endSeconds'])
        a, b = round(start * grid_hz), round(end * grid_hz)
        if a != len(cells) or b <= a:
            raise ValueError('Grid quantization must retain every event and contiguous timing')
        cells.extend([event['identity']] * (b - a))
        event['gridStart'] = a
        event['gridEnd'] = b
        maximum_error = max(maximum_error, abs(Fraction(a, 1) / grid_hz - start), abs(Fraction(b, 1) / grid_hz - end))
    source_units = len(cells)
    storage_units = math.ceil(source_units / 16) * 16
    cells.extend([None] * (storage_units - source_units))
    bars = []
    for start in range(0, len(cells), 16):
        end = start + 16
        position, pieces = start, []
        while position < end:
            identity = cells[position]
            stop = position + 1
            while stop < end and cells[stop] == identity:
                stop += 1
            pitch = events[identity]['pitch'] if identity is not None else 'R'
            tied = pitch != 'R' and stop < len(cells) and cells[stop] == identity
            pieces.append(f'{pitch}:{(stop-position)/4:g}' + ('~' if tied else ''))
            position = stop
        bars.append(' '.join(pieces))
    score = dict(title='Алисия · Экспедиция 33 — фортепианная мелодия',
                 composers=['Lorien Testard', 'Alice Duport-Percier'],
                 tempo_bpm=grid_bpm, beats_per_bar=4, playlist=['complete_melody'],
                 patterns=dict(complete_melody=bars), chord_pairs=[['silence', 'silence']],
                 chord_notes=dict(silence=[None, None]), packing_candidates=candidates,
                 packing_max_entry_offset=255,
                 engine='instrument-bank',
                 instruments=dict(lead='acoustic-grand-piano-soft', keys='off', pluck='off', percussion='off'))
    score['arrangement'] = dict(sourceDurationSeconds=float(Fraction(timeline['durationSeconds'])),
                               sourceEvents=len(events), sourceNoteOns=sum(e['midi'] is not None for e in events),
                               originalMeters=['3/4', '4/4'], originalTemposBpm=[78, 58, 87],
                               encodingGridBpm=grid_bpm, gridStepSeconds=float(1 / grid_hz),
                               maximumQuantizationErrorMs=float(maximum_error * 1000),
                               sourceGridUnits=source_units, storageGridUnits=storage_units,
                               addedFinalSilenceSeconds=float(Fraction(storage_units-source_units, 1) / grid_hz),
                               firstSourceSecond=0,
                               sourceInstrumentMapping={'0:piano': 'acoustic-grand-piano', '1:violin/vocal-line': 'acoustic-grand-piano'},
                               reduction='All source melody/rest events retained, including piano opening and source octave transpositions; one static piano tone replaces source instrument changes. Accompaniment omitted.',
                               timing='Source bars and tempo changes converted to exact rational seconds before one global grid quantization; 4-beat blocks are storage only, with explicit cross-block ties.')
    return score


def measure_code(score):
    folder = ROOT / 'build/alicia-engine-budget'
    folder.mkdir(parents=True, exist_ok=True)
    source, metadata = builder.engine.specialize(score, builder.bank.describe_assignments(score['instruments']))
    score.update(metadata)
    source = builder.release_engine.specialize(score, source)
    (folder / 'synth.S').write_text(source, encoding='utf-8', newline='\n')
    for name in ('config.inc', 'score.inc'):
        shutil.copyfile(BASE / name, folder / name)
    _, labels = builder.release_engine.assemble_relaxed(folder / 'synth.S')
    return labels['playlist']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates', type=int, default=4096)
    parser.add_argument('--grid-bpm', type=int, choices=(174, 261, 348), default=GRID_BPM,
                        help='Storage grid; 348 retains source event times within 20 ms')
    args = parser.parse_args()
    if args.candidates < 1:
        parser.error('--candidates must be positive')
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    timeline = read_timeline(source)
    score = make_score(timeline, args.candidates, args.grid_bpm)
    score['release_tail_slots'] = 2
    score['source_score'] = dict(file='../../reference/alicia/source-score.json',
                                sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                                localOriginal='C:/Work/z80-tester/audio/assets/scores/expedition-33/alicia-score.json',
                                melodyTranscription=source['melody_transcription'],
                                rights=source['rights'])
    code_bytes = measure_code(score)
    _, metadata = builder.compiler.to_inc(score, validate_size=False)
    flash_bytes = (code_bytes + metadata['total_data_bytes'] + 1) // 2 * 2
    print(f'Complete Alicia: {code_bytes} code + {metadata["total_data_bytes"]} data = {flash_bytes} Flash; max phrase entry {metadata["maximum_entry_offset"]}', flush=True)
    if flash_bytes > 1024 or metadata['maximum_entry_offset'] > 255 or metadata['playlist_bytes'] > 255:
        raise ValueError('Complete arrangement does not fit; increase --candidates before reducing music')
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ('avr_core.js', 'FluidR3-MIT.txt'):
        shutil.copyfile(BASE / name, OUT / name)
    bank = builder.bank.load_bank()
    builder.bank.verify_sources(bank)
    profile = bank['instruments']['acoustic-grand-piano-soft']
    waves = dict(piano_low=profile['waves']['low'], piano_high=profile['waves']['high'],
                 note='Shared FluidR3 program0 bank; all unused roles silent.')
    (OUT / 'waveforms.json').write_text(json.dumps(waves, indent=2) + '\n', encoding='utf-8', newline='\n')
    (OUT / 'score.json').write_text(json.dumps(score, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    (REFERENCE / 'timeline.json').write_text(json.dumps(timeline, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    builder.build(OUT)
    print(f'Alicia: {len(timeline["bars"])} source bars, {score["arrangement"]["sourceNoteOns"]} note attacks, '
          f'{score["arrangement"]["sourceDurationSeconds"]:.6f}s; maximum grid error {score["arrangement"]["maximumQuantizationErrorMs"]:.3f}ms')


if __name__ == '__main__':
    main()

"""Arrange the supplied Children MIDI for the shared-grid ATtiny13A engine.

The musical reduction is separate from lossless byte-phrase packing. Piano
track 1 and bass track 4 are selected explicitly; the recognizable opening
starts at the source's beat zero and is never skipped.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import math
import shutil
import struct

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'ATtiny13A/Music/reference/children/source.mid'
OUT = ROOT / 'ATtiny13A/Music/variants/children'
BASE = ROOT / 'ATtiny13A/Music/variants/rhythmic'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


reader = module('children_midi_reader', ROOT / 'tools/midi-reader.py')
builder = module('children_builder', ROOT / 'tools/build-rhythmic.py')


def source_metadata(notes, ppqn):
    raw = SOURCE.read_bytes()
    fmt, count, division = struct.unpack_from('>HHH', raw, 8)
    position = 8 + int.from_bytes(raw[4:8], 'big')
    tracks, tempos, signatures = [], [], []
    for track in range(count):
        assert raw[position:position + 4] == b'MTrk'
        length = int.from_bytes(raw[position + 4:position + 8], 'big')
        chunk = raw[position + 8:position + 8 + length]
        position += 8 + length
        tick = cursor = 0
        running = None
        texts, programs = [], []
        while cursor < len(chunk):
            delta, cursor = reader.vlq(chunk, cursor)
            tick += delta
            status = chunk[cursor]
            if status >= 128:
                cursor += 1
            else:
                if running is None:
                    raise ValueError('Missing running status')
                status = running
            if status == 255:
                kind = chunk[cursor]
                cursor += 1
                size, cursor = reader.vlq(chunk, cursor)
                payload = chunk[cursor:cursor + size]
                cursor += size
                running = None
                if kind in (1, 2, 3, 4, 6):
                    texts.append(dict(tick=tick, type=kind, text=payload.decode('cp1252')))
                elif kind == 81:
                    micros = int.from_bytes(payload, 'big')
                    tempos.append(dict(tick=tick, quarterBeat=tick / ppqn,
                                       microsecondsPerQuarter=micros, bpm=60000000 / micros))
                elif kind == 88:
                    signatures.append(dict(tick=tick, numerator=payload[0], denominator=2 ** payload[1]))
            elif status in (240, 247):
                size, cursor = reader.vlq(chunk, cursor)
                cursor += size
                running = None
            else:
                running = status
                op = status & 240
                size = 1 if op in (192, 208) else 2
                if op == 192:
                    programs.append(dict(tick=tick, channel=status & 15, zeroBasedProgram=chunk[cursor]))
                cursor += size
        selected = [n for n in notes if n[0] == track]
        tracks.append(dict(index=track, text=texts, programs=programs,
                           notes=len(selected), channels=sorted(set(n[1] for n in selected)),
                           pitchRange=[min(n[2] for n in selected), max(n[2] for n in selected)] if selected else None))
    return dict(file='source.mid', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                format=fmt, tracks=count, ppqn=division, sourceNotes=len(notes),
                lastQuarterBeat=max(n[4] for n in notes) / ppqn,
                tempoMap=tempos, timeSignatures=signatures, trackMetadata=tracks,
                license='No permission or license is inferred from embedded MIDI metadata.')


def arrangement(notes, ppqn, bpm, bars, candidates):
    score = reader.create_score(notes, ppqn, bpm, bars, bars, 1, 4)
    score['patterns']['ending'] = ['F4:1 R:3']
    score['playlist'].append('ending')
    score['chord_overrides']['ending'] = [['F3', 'F3']]
    score['chord_roots']['F3'] = 53
    score['packing_candidates'] = candidates
    return score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bars', type=int, default=107, help='Source 4/4 bars, beginning at beat zero')
    parser.add_argument('--candidates', type=int, default=4096, help='Phrase candidates for lossless packing')
    args = parser.parse_args()
    notes, ppqn, bpm = reader.read_midi(SOURCE)
    maximum = math.ceil(max(n[4] for n in notes if n[0] == 1) / (4 * ppqn))
    if not 1 <= args.bars <= maximum:
        parser.error(f'--bars must be between 1 and {maximum}')
    if args.candidates < 1:
        parser.error('--candidates must be positive')
    score = arrangement(notes, ppqn, bpm, args.bars, args.candidates)
    _, meta = builder.compiler.to_inc(score, validate_size=False)
    code = json.loads((BASE / 'build-report.json').read_text(encoding='utf-8'))['codeBytes']
    size = (code + meta['total_data_bytes'] + 1) // 2 * 2
    if size > 1024 or meta['event_bytes'] > 256 or meta['playlist_bytes'] > 255:
        raise ValueError(f'Arrangement does not fit: Flash {size}/1024, events {meta["event_bytes"]}/256')
    score['title'] = 'Robert Miles — Children'
    score['composer'] = 'Robert Miles'
    score['source_midi'] = dict(file='../../reference/children/source.mid',
        sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(), ppqn=ppqn,
        credit='MIDI metadata: Copyright © 1996 by Marcel Gonzalez; bka "DREAMS"',
        timeSignature='4/4', sourcePitchedNotes=len([n for n in notes if n[1] != 9]))
    score['arrangement'] = dict(sourceQuarterBeats=args.bars * 4, sourceBars4_4=args.bars,
        cadenceQuarterBeats=4, firstSourceQuarterBeat=0,
        lead='Main piano melody, MIDI track 1; one highest active note on a sixteenth grid',
        accompaniment='Roots from MIDI bass track 4, reduced to device piano/guitar plus generated percussion',
        tempo='Steady 140 BPM; original MIDI changes from approximately 140 to 137 BPM at beat 160',
        scope='The complete main piano track followed by an F cadence; later MIDI-only layers and multichannel polyphony are omitted'
            if args.bars == maximum else 'Opening excerpt of the main piano track followed by an F cadence',
        compression='Lossless automatic repeated byte phrases after the documented musical reduction; heuristic dictionary search')
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ['synth.S', 'avr_core.js', 'eeprom.bin', 'waveforms.json', 'FluidR3-MIT.txt']:
        shutil.copyfile(BASE / name, OUT / name)
    (OUT / 'score.json').write_text(json.dumps(score, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    metadata = source_metadata(notes, ppqn)
    (SOURCE.parent / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    builder.build(OUT)
    print(f'Children: {args.bars} source bars + cadence, {size} Flash bytes, {(args.bars + 1) * 4 * 60 / bpm:.6f} seconds')


if __name__ == '__main__':
    main()

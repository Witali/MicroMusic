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
import wave

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'ATtiny13A/Music/reference/children/source-events.json'
OUT = ROOT / 'ATtiny13A/Music/variants/children'
BASE = ROOT / 'ATtiny13A/Music/variants/rhythmic'


def fit_bass(capture_folder):
    """Measure external FluidR3 program 35 captures and keep a small audit trail."""
    import numpy as np
    capture = json.loads((capture_folder / 'capture.json').read_text(encoding='utf-8'))
    assert capture['program'] == 35 and capture['preset'] == 'Fretless Bass'
    measured = []
    for note in capture['notes']:
        raw = (capture_folder / note['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == note['sha256']
        with wave.open(str(capture_folder / note['file'])) as stream:
            sr = stream.getframerate()
            signal = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2').reshape(-1, 2).mean(axis=1) / 32768.
        time = np.arange(round(.25 * sr)) / sr
        window = np.hanning(len(time))
        segment = signal[round(.3 * sr):round(.3 * sr) + len(time)]
        segment = (segment - segment.mean()) * window
        nominal = 440 * 2 ** ((note['midi'] - 69) / 12)
        candidates = nominal * np.linspace(.98, 1.02, 81)
        peak = np.exp(-2j * np.pi * candidates[:, None] * time) @ segment
        f0 = candidates[np.argmax(abs(peak))]
        partials = np.exp(-2j * np.pi * np.arange(1, 8)[:, None] * f0 * time) @ segment
        amplitude = abs(partials)
        amplitude /= np.linalg.norm(amplitude)
        phases = np.angle(partials) - np.arange(1, 8) * np.angle(partials[0])
        measured.append(dict(midi=note['midi'], sourcePcmSha256=note['sha256'], f0Hz=float(f0),
                             harmonics=amplitude.round(8).tolist(), phases=phases.round(8).tolist()))
    # Retain the measured first harmonics, soften upper partials, then quantize
    # to the device's signed four-bit 16-point format. The bass is deliberately
    # quieter than the lead: four table units times a six-level amplitude.
    target = np.mean([n['harmonics'] for n in measured], axis=0)
    target /= np.sqrt(1 + (np.arange(1, 8) / 3.2) ** 4)
    phase = np.array(measured[0]['phases'])
    angle = np.arange(16) * 2 * np.pi / 16
    waveform = np.sum(target[:, None] * np.cos(np.arange(1, 8)[:, None] * angle + phase[:, None]), axis=0)
    waveform -= waveform.mean()
    waveform = np.rint(waveform / max(abs(waveform)) * 4).astype(int)
    rotation = min(range(16), key=lambda i: (abs(waveform[i]), abs(waveform[(i - 1) % 16] - waveform[i])))
    waveform = np.roll(waveform, -rotation).tolist()
    report = dict(soundfont=capture['soundfont'], renderer=capture['renderer'], program=35,
                  preset='Fretless Bass', measuredAtSeconds=.3, windowSeconds=.25,
                  method='Seven measured partials, harmonic low-pass H3.2, 16-point signed four-bit quantization, quiet amplitude ±4',
                  notes=measured, waveform=waveform)
    (SOURCE.parent / 'fretless-measurements.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')


def clean_tables(assignments, bank):
    roles = instrument_bank.describe_assignments(assignments, bank)
    piano = bank['instruments'][roles['lead']['instrument']]['waves']
    bass = bank['instruments'][roles['keys']['instrument']]['waves']
    output = dict(piano_low=piano['low'], piano_high=piano['high'], fretless_bass=bass['low'],
                  assignments=assignments, instrumentBank='../../instruments/bank.json',
                  note='Tables resolved by tools/instrument-bank.py from score.instruments. Unused EEPROM banks are silent.')
    return instrument_bank.build_eeprom(assignments, bank), output


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


reader = module('children_midi_reader', ROOT / 'tools/midi-reader.py')
builder = module('children_builder', ROOT / 'tools/build-rhythmic.py')
instrument_bank = module('children_instrument_bank', ROOT / 'tools/instrument-bank.py')


def source_metadata(notes, ppqn):
    raw = SOURCE.read_bytes()
    document = json.loads(raw)
    tracks, tempos, signatures = [], [], []
    for track in document['tracks']:
        texts, programs = [], []
        for event in track['events']:
            tick, kind = event['tick'], event['type']
            if kind == 'text':
                texts.append(dict(tick=tick, type=event['metaType'], text=event['text']))
            elif kind == 'programChange':
                programs.append(dict(tick=tick, channel=event['channel'], zeroBasedProgram=event['program']))
            elif kind == 'tempo':
                micros = event['microsecondsPerQuarter']
                tempos.append(dict(tick=tick, quarterBeat=tick / ppqn, microsecondsPerQuarter=micros, bpm=60000000 / micros))
            elif kind == 'timeSignature':
                signatures.append(dict(tick=tick, numerator=event['numerator'], denominator=event['denominator']))
        selected = [n for n in notes if n[0] == track['index']]
        tracks.append(dict(index=track['index'], text=texts, programs=programs,
                           notes=len(selected), channels=sorted(set(n[1] for n in selected)),
                           pitchRange=[min(n[2] for n in selected), max(n[2] for n in selected)] if selected else None))
    return dict(file=SOURCE.name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                originalMidiSha256=document['source']['sha256'],
                format=document['format'], tracks=len(tracks), ppqn=document['ppqn'], sourceNotes=len(notes),
                lastQuarterBeat=max(n[4] for n in notes) / ppqn,
                tempoMap=tempos, timeSignatures=signatures, trackMetadata=tracks,
                license='No permission or license is inferred from embedded MIDI metadata.')


def main():
    # Retain source_metadata/fit_bass for existing authoring tools; the native
    # generator is the single production arrangement and build entry point.
    native=module('children_native_arranger',ROOT/'tools/arrange-children-four.py')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates',type=int,default=4096)
    parser.add_argument('--bars',type=int,choices=[107],default=107)
    parser.add_argument('--bass-capture',type=Path)
    args=parser.parse_args()
    if args.bass_capture:fit_bass(args.bass_capture)
    native.build(OUT,candidates=args.candidates,production=True)


if __name__ == '__main__':
    main()

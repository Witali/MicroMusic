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
SOURCE = ROOT / 'ATtiny13A/Music/reference/children/source.mid'
OUT = ROOT / 'ATtiny13A/Music/variants/children'
BASE = ROOT / 'ATtiny13A/Music/variants/rhythmic'


def replace_once(source, before, after):
    assert source.count(before) == 1, before[:100]
    return source.replace(before, after)


def clean_engine(roles):
    """Specialize the shared engine for the MIDI's piano and fretless bass."""
    assert roles['lead']['envelope']['model'] == 'piano'
    assert roles['keys']['envelope']['model'] == 'sustain'
    assert roles['pluck']['instrument'] == roles['percussion']['instrument'] == 'off'
    decay_mask = roles['lead']['envelope']['decayMask']
    lead_peak = 128 | roles['lead']['level']
    bass_level = roles['keys']['level']
    source = (ROOT / 'tools/avr-synth-template.S').read_text(encoding='utf-8')
    source = '\n'.join(line for line in source.splitlines() if '/* BEGIN ' not in line and '/* END ' not in line)+'\n'
    start = source.index('  sbrs r1, 7', source.index('music_tick:'))
    end = source.index('.L08e:', start)
    source = source[:start] + f'''  /* Program 0 piano: immediate attack, measured three-rate decay. */
  mov r16, r1
  ldi r17, {decay_mask}
  rcall update_envelope
  mov r1, r16
''' + source[end:]
    start = source.index('  /* Piano and guitar use', source.index('.L08e:'))
    end = source.index('.L0a8:', start)
    source = source[:start] + '''  /* Quiet fretless-bass bed is held between harmony changes.
   * No substitute guitar and no generated percussion are mixed. */
''' + source[end:]
    start = source.index('  inc r29', source.index('grid_step:'))
    end = source.index('.L0ba:', start)
    source = source[:start] + source[end:]
    source = replace_once(source, '  clr r7\n  clr r11\n  ldi r16, 143\n  mov r19, r16\n  mov r20, r16',
                         f'  /* Keep the bass phase continuous; quiet level from the shared bank. */\n  ldi r19, {bass_level}\n  clr r20')
    source = replace_once(source, '  mov r16, r1\n  andi r16, 15\n  lsr r16\n  ori r16, 128\nlead_commit:',
                         f'  ldi r16, {lead_peak}\nlead_commit:')
    start = source.index('  add r10, r12', source.index('render_sample:'))
    end = source.index('write_pwm:', start)
    source = source[:start] + '''  /* The MIDI's main roles are piano and fretless bass.
   * Omit unrelated synthetic guitar, snare and hi-hat. */
''' + source[end:]
    source = source.replace('Piano/guitar use soft sustain spectra with their measured envelopes.',
                            'Program 0 piano lead and quiet program 35 fretless-bass approximation.')
    source = source.replace('Odd ticks produce new four-voice points;', 'Odd ticks produce new piano/bass points;')
    source = source.replace('bit0 violin, bit1 piano, bit2 guitar, bit3 percussion',
                            'bit0 lead piano, bit1 bass; bits2/3 are inactive')
    source = source.replace('Accumulate three pitch oscillators with independent phases and envelopes.',
                            'Accumulate piano and exact source-octave bass with continuous phases.')
    return source


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
    # The generic reader folds roots into octave three. Restore the exact
    # source bass register, rather than sounding an unrelated fifth below it.
    root_names = {'C#3': 'C#2', 'A#3': 'A#1', 'F3': 'F1'}
    score['chord_pairs'] = [[root_names[n] for n in pair] for pair in score['chord_pairs']]
    score['chord_overrides'] = {name: [[root_names[n] for n in pair] for pair in pairs]
                                for name, pairs in score['chord_overrides'].items()}
    score['chord_roots'] = {'C#2': 37, 'A#1': 34, 'F1': 29}
    score['patterns']['ending'] = ['F4:1 R:3']
    score['playlist'].append('ending')
    score['chord_overrides']['ending'] = [['F1', 'F1']]
    score['packing_candidates'] = candidates
    score['instruments'] = dict(lead='acoustic-grand-piano', keys='fretless-bass', pluck='off', percussion='off')
    roles = instrument_bank.describe_assignments(score['instruments'])
    score['lead_envelope_model'] = roles['lead']['envelope']['model']
    score['lead_retrigger'] = 'full' if roles['lead']['envelope']['retrigger'] == 'peak' else 'half'
    score['percussion_enabled'] = roles['percussion']['instrument'] != 'off'
    score['accompaniment_envelope_model'] = 'constant'  # Minimal held-root specialization of the bank sustain model.
    return score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bars', type=int, default=107, help='Source 4/4 bars, beginning at beat zero')
    parser.add_argument('--candidates', type=int, default=4096, help='Phrase candidates for lossless packing')
    parser.add_argument('--bass-capture', type=Path, help='Regenerate the bass table from FluidR3 program35 capture.json and WAV files')
    args = parser.parse_args()
    notes, ppqn, bpm = reader.read_midi(SOURCE)
    maximum = math.ceil(max(n[4] for n in notes if n[0] == 1) / (4 * ppqn))
    if not 1 <= args.bars <= maximum:
        parser.error(f'--bars must be between 1 and {maximum}')
    if args.candidates < 1:
        parser.error('--candidates must be positive')
    if args.bass_capture:
        fit_bass(args.bass_capture)
    score = arrangement(notes, ppqn, bpm, args.bars, args.candidates)
    bank = instrument_bank.load_bank()
    instrument_bank.verify_sources(bank)
    roles = instrument_bank.describe_assignments(score['instruments'], bank)
    _, meta = builder.compiler.to_inc(score, validate_size=False)
    # The specialization removes inactive voices. The final assembler validates
    # the real code plus data size; no guessed code size is used for this check.
    if meta['event_bytes'] > 256 or meta['playlist_bytes'] > 255:
        raise ValueError(f'Arrangement offsets do not fit: events {meta["event_bytes"]}/256')
    score['title'] = 'Robert Miles — Children'
    score['composer'] = 'Robert Miles'
    score['source_midi'] = dict(file='../../reference/children/source.mid',
        sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(), ppqn=ppqn,
        credit='MIDI metadata: Copyright © 1996 by Marcel Gonzalez; bka "DREAMS"',
        timeSignature='4/4', sourcePitchedNotes=len([n for n in notes if n[1] != 9]))
    score['arrangement'] = dict(sourceQuarterBeats=args.bars * 4, sourceBars4_4=args.bars,
        cadenceQuarterBeats=4, firstSourceQuarterBeat=0,
        lead='Main piano melody, MIDI track 1; one highest active note on a sixteenth grid',
        accompaniment='Quiet FluidR3 program35 fretless-bass approximation at exact source pitches C#2/A#1/F1; synthetic guitar and percussion omitted',
        tempo='Steady 140 BPM; original MIDI changes from approximately 140 to 137 BPM at beat 160',
        scope='The complete main piano track followed by an F cadence; later MIDI-only layers and multichannel polyphony are omitted'
            if args.bars == maximum else 'Opening excerpt of the main piano track followed by an F cadence',
        compression='Lossless automatic repeated byte phrases after the documented musical reduction; heuristic dictionary search')
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ['avr_core.js', 'FluidR3-MIT.txt']:
        shutil.copyfile(BASE / name, OUT / name)
    (OUT / 'synth.S').write_text(clean_engine(roles), encoding='utf-8', newline='\n')
    eeprom, waves = clean_tables(score['instruments'], bank)
    (OUT / 'eeprom.bin').write_bytes(eeprom)
    (OUT / 'waveforms.json').write_text(json.dumps(waves, indent=2) + '\n', encoding='utf-8', newline='\n')
    (OUT / 'score.json').write_text(json.dumps(score, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    metadata = source_metadata(notes, ppqn)
    (SOURCE.parent / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    builder.build(OUT)
    report = json.loads((OUT / 'build-report.json').read_text(encoding='utf-8'))
    report['articulation']['attack'] = 'Program0 piano: immediate full-level attack followed by the measured three-rate decay'
    report['articulation']['retrigger'] = 'Full level143, same oscillator phase; explicit holds skip retrigger'
    report['instruments'] = score['instruments']
    report['score']['instruments'] = score['instruments']
    report['instrumentAssignments'] = roles
    report['instrumentBank'] = dict(file='../../instruments/bank.json',
                                    sha256=hashlib.sha256(instrument_bank.BANK_PATH.read_bytes()).hexdigest(),
                                    firmwareSpecialization='Two active voices; quiet held bass level from the bank; canonical piano helper release is two levels per tick')
    (OUT / 'build-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(f'Children: {args.bars} source bars + cadence, {report["flashBytes"]} Flash bytes, {(args.bars + 1) * 4 * 60 / bpm:.6f} seconds')


if __name__ == '__main__':
    main()

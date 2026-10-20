"""Verify that Children retains every main-piano note and its quantized timing."""
from pathlib import Path
import hashlib
import importlib.util
import json

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'ATtiny13A/Music/variants/children'
SOURCE = ROOT / 'ATtiny13A/Music/reference/children/source.mid'
spec = importlib.util.spec_from_file_location('children_midi_reader', ROOT / 'tools/midi-reader.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
notes, ppqn, bpm = reader.read_midi(SOURCE)
source = sorted((n for n in notes if n[0] == 1), key=lambda n: (n[3], n[2]))
score = json.loads((FOLDER / 'score.json').read_text(encoding='utf-8'))
assert score['source_midi']['sha256'] == hashlib.sha256(SOURCE.read_bytes()).hexdigest()
assert score['tempo_bpm'] == bpm == 140
assert score['arrangement']['firstSourceQuarterBeat'] == 0
assert score['arrangement']['sourceQuarterBeats'] == 428
assert len(source) == 256

# Build the source's sixteenth grid directly from SMF events. Identities retain
# separate MIDI Note On events even when consecutive pitches are identical.
quantized = [(n[2], round(n[3] * 4 / ppqn),
              max(round(n[3] * 4 / ppqn) + 1, round(n[4] * 4 / ppqn)), identity)
             for identity, n in enumerate(source)]
expected, represented = [], set()
for position in range(428 * 4):
    active = [n for n in quantized if n[1] <= position < n[2]]
    selected = max(active, key=lambda n: (n[0], n[1])) if active else None
    if selected:
        represented.add(selected[3])
    expected.append(selected)
assert len(represented) == len(source), 'No source main-piano note may disappear'
expected_attacks = [(i, reader.note_name(n[0])) for i, n in enumerate(expected)
                    if n and (i == 0 or expected[i - 1] is None or expected[i - 1][3] != n[3])]

actual, actual_attacks = [], []
prior_note, tie = None, False
for name in score['playlist'][:-1]:
    for bar in score['patterns'][name]:
        bar_units = 0
        for piece in bar.split():
            pitch, duration = piece.split(':')
            units = round(float(duration.rstrip('~')) * 4)
            assert units > 0
            if pitch != 'R' and not (tie and prior_note == pitch):
                actual_attacks.append((len(actual), pitch))
            actual.extend([pitch] * units)
            prior_note, tie = pitch, duration.endswith('~')
            bar_units += units
        assert bar_units == 16
assert actual == [reader.note_name(n[0]) if n else 'R' for n in expected]
assert actual_attacks == expected_attacks
assert actual_attacks[:4] == [(0, 'F5'), (24, 'G#5'), (28, 'G5'), (30, 'D#5')]
assert score['patterns']['ending'] == ['F4:1 R:3']
report = json.loads((FOLDER / 'build-report.json').read_text(encoding='utf-8'))
assert report['flashBytes'] <= 1024
assert report['flashSha256'] == hashlib.sha256((FOLDER / 'synth.bin').read_bytes()).hexdigest()
assert report['score']['compression']['verifiedLossless']
assert report['score']['compression']['packedBytes'] < report['score']['compression']['sourceLayoutBytes']
assert score['instruments'] == dict(lead='acoustic-grand-piano', keys='fretless-bass', pluck='off', percussion='off')
assert score['lead_envelope_model'] == 'piano' and score['lead_retrigger'] == 'full'
assert score['percussion_enabled'] is False and score['accompaniment_envelope_model'] == 'constant'
assert 'render_drum' not in report['labels'] and 'drum_trigger' not in report['labels']
original_programs = json.loads((SOURCE.parent / 'metadata.json').read_text(encoding='utf-8'))['trackMetadata']
assert original_programs[1]['programs'][0]['zeroBasedProgram'] == 0
assert original_programs[4]['programs'][0]['zeroBasedProgram'] == 35
source_bass = {n[2] for n in notes if n[0] == 4 and n[3] < 428 * ppqn}
assert source_bass == set(score['chord_roots'].values()) == {29, 34, 37}
rom = (FOLDER / 'synth.bin').read_bytes()
chord_address = report['labels']['chord_steps']
for i, chord in enumerate(report['score']['chords']):
    step = rom[chord_address + i * 4] | rom[chord_address + i * 4 + 1] << 8
    midi = score['chord_roots'][chord]
    assert step == round(440 * 2 ** ((midi - 69) / 12) * 65536 / 18750)
eeprom = (FOLDER / 'eeprom.bin').read_bytes()
bank_spec = importlib.util.spec_from_file_location('children_instrument_bank', ROOT / 'tools/instrument-bank.py')
instrument_bank = importlib.util.module_from_spec(bank_spec)
bank_spec.loader.exec_module(instrument_bank)
bank = instrument_bank.load_bank()
assert instrument_bank.verify_sources(bank)
assert eeprom == instrument_bank.build_eeprom(score['instruments'], bank), 'All tables come from the assigned shared profiles'
roles = instrument_bank.describe_assignments(score['instruments'], bank)
assert report['instrumentAssignments'] == roles
assert roles['lead']['gmProgram'] == 0 and roles['lead']['envelope']['model'] == 'piano'
assert roles['keys']['gmProgram'] == 35 and roles['keys']['level'] == 6
waves = json.loads((FOLDER / 'waveforms.json').read_text(encoding='utf-8'))
bass = waves['fretless_bass']
assert len(bass) == 16 and max(abs(n) for n in bass) <= 4 and sum(bass) == 0
assert eeprom[16:24] == bytes((bass[i] + 8) | (bass[i + 1] + 8) << 4 for i in range(0, 16, 2))
assert eeprom[32:] == bytes([0x88] * 32), 'Inactive instrument banks are silent'
print(f'Children: all {len(source)} source main-piano Note On events retained; '
      f'{len(actual)} sixteenth cells checked; recognizable opening kept; '
      f'{report["flashBytes"]}/1024 Flash bytes; lossless packed score verified; '
      'correct program0 piano and program35 bass, exact source bass register, no guitar or added percussion.')

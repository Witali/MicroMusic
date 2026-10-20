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
print(f'Children: all {len(source)} source main-piano Note On events retained; '
      f'{len(actual)} sixteenth cells checked; recognizable opening kept; '
      f'{report["flashBytes"]}/1024 Flash bytes; lossless packed score verified.')

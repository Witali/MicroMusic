"""Verify that Children retains every main-piano note and its quantized timing."""
from pathlib import Path
import hashlib
import importlib.util
import json
import math
import subprocess
import tempfile
import shutil

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'ATtiny13A/Music/variants/children'
SOURCE = ROOT / 'ATtiny13A/Music/reference/children/source-events.json'
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
assert score['engine'] == 'instrument-bank'
assert score['lead_envelope_model'] == 'piano' and score['lead_retrigger'] == 'full'
assert score['lead_max_level'] == 15 and score['lead_release_step'] == 2
assert score['percussion_enabled'] is False and score['accompaniment_envelope_model'] == 'pluck'
assert score['keys_max_level'] == 6 and score['keys_decay_mask'] == 3 and score['keys_release_step'] == 1
assert score['keys_retrigger'] == 'full' and score['keys_release_model'] == 'shared-decay'
assert score['pluck_envelope_model'] == 'off' and score['pluck_max_level'] == 0
assert 'render_drum' not in report['labels'] and 'drum_trigger' not in report['labels']
original_programs = json.loads((SOURCE.parent / 'metadata.json').read_text(encoding='utf-8'))['trackMetadata']
assert original_programs[1]['programs'][0]['zeroBasedProgram'] == 0
assert original_programs[4]['programs'][0]['zeroBasedProgram'] == 35
source_bass = {n[2] for n in notes if n[0] == 4 and n[3] < 428 * ppqn}
assert source_bass == set(score['chord_roots'].values()) == {29, 34, 37}
source_bass_events = sorted((n for n in notes if n[0]==4 and n[3]<428*ppqn),key=lambda n:n[3])
bass_controls = score['timed_controls']['intro']
actual_bass_attacks = [(c['unit'],score['chord_roots'][c['chord']]) for c in bass_controls if 'chord' in c]
assert actual_bass_attacks == [(math.ceil(n[3]*4/ppqn),n[2]) for n in source_bass_events]
assert len(actual_bass_attacks) == score['bass_source_note_ons'] == 345
for note in source_bass_events:
    off = min(1712,math.floor(note[4]*4/ppqn))
    assert off==1712 or any(c['unit']==off for c in bass_controls), 'Every bass NoteOff is a real gap or an atomic replacement'
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
assert roles['keys']['envelope']['model'] == 'pluck' and roles['keys']['envelope']['decayMask'] == 3
assert report['instrumentBankSha256'] == hashlib.sha256(instrument_bank.BANK_PATH.read_bytes()).hexdigest()
waves = json.loads((FOLDER / 'waveforms.json').read_text(encoding='utf-8'))
bass = waves['fretless_bass']
assert len(bass) == 16 and max(abs(n) for n in bass) <= 4 and sum(bass) == 0
assert eeprom[16:24] == bytes((bass[i] + 8) | (bass[i + 1] + 8) << 4 for i in range(0, 16, 2))
assert eeprom[32:48] == bytes([0x88] * 16), 'Inactive tonal bank is silent; shared piano attack occupies48..63'
engine_spec = importlib.util.spec_from_file_location('children_instrument_engine', ROOT / 'tools/build-instrument-engine.py')
engine = importlib.util.module_from_spec(engine_spec)
engine_spec.loader.exec_module(engine)
expected_source, expected_settings = engine.specialize(score, roles)
assert score['release_tail_slots'] == report['releaseChannels']['tailSlots'] == 2
release_spec=importlib.util.spec_from_file_location('children_release_engine',ROOT/'tools/build-release-engine.py')
release_engine=importlib.util.module_from_spec(release_spec);release_spec.loader.exec_module(release_engine)
expected_source=release_engine.specialize(score,expected_source)
with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='children-rebuild-check-') as temporary:
    temporary=Path(temporary)
    for filename in ('config.inc','score.inc'):shutil.copyfile(FOLDER/filename,temporary/filename)
    (temporary/'synth.S').write_text(expected_source,encoding='utf-8',newline='\n')
    rebuilt,_=release_engine.assemble_relaxed(temporary/'synth.S')
    assert rebuilt==(FOLDER/'synth.bin').read_bytes(),'Assigned profiles reproduce the exact AVR image'
    assert (temporary/'synth.S').read_text(encoding='utf-8')==(FOLDER/'synth.S').read_text(encoding='utf-8')
assert all(score[key] == value for key, value in expected_settings.items())
runtime_check = r'''
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore} from './web-player/lib/avr-core.js';
const folder='ATtiny13A/Music/variants/children';
const {labels}=JSON.parse(fs.readFileSync(folder+'/build-report.json'));
const c=new AVRCore(fs.readFileSync(folder+'/synth.bin'),fs.readFileSync(folder+'/eeprom.bin'),{fastIdle:false});
function until(target){let n=0;while(c.pc!==target){c.step();assert.ok(++n<200,'Reach envelope/event boundary');}}
function tick(){c.pc=labels.music_tick/2;until(labels['.L0a8']/2);return c.data[101]&15;}
c.data[101]=150;
assert.deepEqual(Array.from({length:16},tick),[...Array(15).fill(6),5],'Bass decays even while a long source note remains held');
c.data[101]=22;
assert.deepEqual(Array.from({length:7},tick),[5,4,3,2,1,0,0],'Bass release is one level per tick and saturates at zero');
c.data[101]=150;c.data[102]=0x34;c.data[103]=0x12;c.r[16]=224;c.pc=labels.chord_event/2;
until(labels.read_event/2);
assert.equal(c.data[101]&15,6,'Each real bass NoteOn restarts at the quiet six-level peak');
assert.equal(c.data[102]|c.data[103]<<8,0x1234,'Bass phase is continuous');
c.data[96]=194;c.data[97]=0x78;c.data[98]=0x56;c.r[16]=0;
c.r[30]=labels.first_section&255;c.r[31]=labels.first_section>>8;c.pc=labels.melodic_event/2;
until(labels.hold_sample/2);
assert.equal(c.data[96]&15,15,'Piano always attacks at full level');
assert.equal(c.data[97]|c.data[98]<<8,0x5678,'Piano phase is continuous');
'''
checked = subprocess.run(['node', '--input-type=module', '-e', runtime_check], cwd=ROOT,
                         capture_output=True, text=True, check=False)
assert checked.returncode == 0, checked.stdout + checked.stderr
print(f'Children: all {len(source)} source main-piano Note On events retained; '
      f'{len(actual)} sixteenth cells checked; recognizable opening kept; '
      f'{report["flashBytes"]}/1024 Flash bytes; lossless packed score verified; '
      'correct program0 piano and program35 bass, exact source bass register, no guitar or added percussion.')

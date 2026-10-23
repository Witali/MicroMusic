"""Assemble every bank assignment and execute independent envelope/note oracles."""
from pathlib import Path
import copy
import importlib.util
import itertools
import json
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


bank_module = module('instrument_bank', ROOT / 'tools/instrument-bank.py')
engine = module('instrument_engine', ROOT / 'tools/build-instrument-engine.py')
assembler = module('avr_assembler', ROOT / 'tools/assemble-avr.py')
CONFIG = '''.set REST_INDEX, 1
.set HOLD_INDEX, 2
.set PLAYLIST_LEN, 1
.set FIRST_PLAYLIST_INDEX, 0
.set GRID_STEP_LOW, 164
.set GRID_STEP_HIGH, 18
.set GRID_INITIAL_HIGH, 238
'''
SCORE = '''playlist:
.byte 0
durations:
.byte 1,2,3,4,6,8,16
note_steps:
.byte 0,2
chord_steps:
.byte 0,1,0,2
melody_data:
first_section:
.byte 0,255
'''


def independent_size(source, config, score):
    """Instruction widths and explicit data lengths; no assembler code reused."""
    text = source.replace('.include "config.inc"', config).replace('.include "score.inc"', score)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    size = 0
    before_playlist = None
    for line in map(str.strip, text.splitlines()):
        if line == 'playlist:':
            before_playlist = size
        if not line or line.endswith(':') or line.startswith(('.section', '.global', '.set')):
            continue
        if line.startswith('.byte '):
            size += len(line[6:].split(','))
        else:
            if line.startswith('.'):
                raise AssertionError(f'Unexpected directive: {line}')
            size += 4 if line.split()[0] in ('lds', 'sts') else 2
    return (size + 1) // 2 * 2, before_playlist


class InstrumentEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = bank_module.load_bank()
        (ROOT / 'build/instrument-engine').mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix='test-', dir=ROOT / 'build/instrument-engine')
        cls.folder = Path(cls.temporary.name)
        (cls.folder / 'config.inc').write_text(CONFIG, newline='\n')
        (cls.folder / 'score.inc').write_text(SCORE, newline='\n')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def compile(self, assignments, score=None):
        roles = bank_module.describe_assignments(assignments, self.bank)
        source, metadata = engine.specialize(score or {'beats_per_bar': 4}, roles)
        (self.folder / 'synth.S').write_text(source, encoding='utf-8', newline='\n')
        binary, labels = assembler.assemble(self.folder / 'synth.S')
        self.assertEqual((len(binary), labels['playlist']), independent_size(source, CONFIG, SCORE))
        return source, metadata, binary, labels

    def test_every_bank_and_noise_combination_assembles_within_flash(self):
        sizes = []
        for ids in itertools.product(self.bank['instruments'], repeat=3):
            for kit in ('off', 'natural-kit'):
                with self.subTest(ids=ids, percussion=kit):
                    source, meta, binary, labels = self.compile(dict(zip(engine.ROLES, ids)) | {'percussion': kit})
                    self.assertLessEqual(len(binary), 1024)
                    self.assertEqual(meta['percussion_enabled'], kit == 'natural-kit')
                    sizes.append(len(binary))
        self.assertEqual(len(sizes), len(self.bank['instruments']) ** 3 * 2)
        self.assertGreater(max(sizes), min(sizes))

    def test_unused_renderers_envelopes_and_noise_are_removed(self):
        all_source, _, full, _ = self.compile(dict(zip(engine.ROLES, ('violin', 'acoustic-grand-piano', 'acoustic-guitar-nylon'))) | {'percussion': 'natural-kit'})
        for role, instruction in (('lead', '  add r2, r4\n'), ('keys', '  add r6, r8\n'), ('pluck', '  add r10, r12\n')):
            assignments = dict(zip(engine.ROLES, ('violin', 'acoustic-grand-piano', 'acoustic-guitar-nylon')))
            assignments[role] = 'off'
            source, meta, binary, _ = self.compile(assignments | {'percussion': 'natural-kit'})
            self.assertNotIn(instruction, source)
            self.assertLess(len(binary), len(full))
        source, meta, binary, labels = self.compile({})
        self.assertNotIn('render_tone', labels)
        self.assertNotIn('update_envelope', labels)
        self.assertNotIn('drum_trigger', labels)
        self.assertNotIn('  lpm r8, Z+\n', source)
        self.assertNotIn('  lpm r4, Z+\n', source)
        self.assertNotIn('  lds r27, 96\n', source)
        self.assertLess(len(binary), len(full) // 2)
        zero, _, zero_binary, _ = self.compile({'lead': {'instrument': 'violin', 'level': 0}})
        self.assertEqual(zero_binary, binary)

    def test_rest_or_encoding_has_the_real_avr_opcode(self):
        _, _, binary, labels = self.compile({'keys': 'violin', 'pluck': 'cello'})
        # OR Rd,Rr is 0010 10rd dddd rrrr, independent of the encoder.
        self.assertEqual(int.from_bytes(binary[labels['keys_sounding'] - 6:labels['keys_sounding'] - 4], 'little'), 0x2909)
        self.assertEqual(int.from_bytes(binary[labels['pluck_sounding'] - 6:labels['pluck_sounding'] - 4], 'little'), 0x290d)

    def test_rest_guards_are_removed_only_for_proven_nonzero_dds_tables(self):
        assignments = {'keys': 'violin', 'pluck': 'cello'}
        _, _, unknown, _ = self.compile(assignments)
        cases = [
            ({'chord_pairs': [['a', 'b']], 'chord_notes': {'a': [60, 48], 'b': ['D4', 'E3']}}, (False, False)),
            ({'chord_pairs': [['a', 'a']], 'chord_notes': {'a': [None, 48]}}, (True, False)),
            ({'chord_pairs': [['a', 'a']], 'chord_notes': {'a': [60, 'R']}}, (False, True)),
            ({'chord_pairs': [['a', 'a']], 'chord_notes': {'a': [0, 0]}}, (False, False)),
            ({'chord_pairs': [['a', 'a']], 'chord_notes': {'a': [-200, 48]}}, (True, False)),
            ({'chord_pairs': [['Bm', 'Gmaj7'], ['Em', 'F#']]}, (False, False)),
            ({'chord_pairs': [['a', 'a']], 'chord_roots': {'a': 0}}, (False, False)),
            ({'chord_pairs': [['a', 'a']], 'chord_roots': {'a': None}}, (True, True)),
            ({'chord_pairs': [['unknown', 'unknown']]}, (True, True)),
            ({'chord_pairs': None}, (True, True)),
            # Overrides are included in the emitted DDS table. An unrelated
            # dictionary entry that cannot be referenced does not need a guard.
            ({'chord_pairs': [['a', 'a']], 'chord_notes': {'a': [60, 48], 'unused': [None, None]}}, (False, False)),
            ({'chord_pairs': [['a', 'a']], 'chord_overrides': {'intro': [['a', 'b']]},
              'chord_notes': {'a': [60, 48], 'b': [None, 48]}}, (True, False)),
        ]
        for score, expected in cases:
            with self.subTest(score=score):
                source, meta, binary, labels = self.compile(assignments, score)
                self.assertEqual((meta['keys_rest_check'], meta['pluck_rest_check']), expected)
                self.assertEqual(len(unknown) - len(binary), 8 * (2 - sum(expected)))
                for role, check in zip(('keys', 'pluck'), expected):
                    self.assertEqual(role + '_sounding' in labels, check)

    def test_current_lumiere_and_two_piano_march_fit_with_their_actual_score_tables(self):
        assignments = {
            'rhythmic': dict(lead='violin', keys='acoustic-grand-piano', pluck='acoustic-guitar-nylon', percussion='natural-kit'),
            'turkish-march': dict(lead='acoustic-grand-piano', keys={'instrument': 'acoustic-grand-piano', 'level': 10},
                                 pluck='off', percussion='off')}
        try:
            for name, selection in assignments.items():
                with self.subTest(name=name):
                    folder = ROOT / 'ATtiny13A/Music/variants' / name
                    data = json.loads((folder / 'score.json').read_text(encoding='utf-8'))
                    config = (folder / 'config.inc').read_text(encoding='utf-8')
                    score = (folder / 'score.inc').read_text(encoding='utf-8')
                    source, _ = engine.specialize(data, bank_module.describe_assignments(selection, self.bank))
                    (self.folder / 'config.inc').write_text(config, encoding='utf-8', newline='\n')
                    (self.folder / 'score.inc').write_text(score, encoding='utf-8', newline='\n')
                    (self.folder / 'synth.S').write_text(source, encoding='utf-8', newline='\n')
                    binary, labels = assembler.assemble(self.folder / 'synth.S')
                    self.assertLessEqual(len(binary), 1024)
                    self.assertEqual((len(binary), labels['playlist']), independent_size(source, config, score))
        finally:
            (self.folder / 'config.inc').write_text(CONFIG, newline='\n')
            (self.folder / 'score.inc').write_text(SCORE, newline='\n')

    def test_invalid_models_steps_and_noise_meters_fail(self):
        roles = bank_module.describe_assignments({'lead': 'flute'}, self.bank)
        for field, value in (('model', 'saw'), ('attackStep', 0), ('attackStep', True), ('releaseStep', 16)):
            invalid = copy.deepcopy(roles)
            invalid['lead']['envelope'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                engine.specialize({}, invalid)
        kit = bank_module.describe_assignments({'percussion': 'natural-kit'}, self.bank)
        with self.assertRaises(ValueError):
            engine.specialize({'beats_per_bar': 3}, kit)

    def test_attack_release_masks_are_validated_and_require_supported_models(self):
        for instrument in ('violin', 'flute', 'off'):
            for field in ('attackMask', 'releaseMask'):
                for value in (-1, 2, 4, 16, 31, True, 1.0, '1', None):
                    roles = bank_module.describe_assignments({'lead': instrument}, self.bank)
                    roles['lead']['envelope'][field] = value
                    with self.subTest(instrument=instrument, field=field, value=value), self.assertRaisesRegex(ValueError, field):
                        engine.specialize({}, roles)
        for instrument in ('acoustic-grand-piano', 'acoustic-guitar-nylon', 'off'):
            for field in ('attackMask', 'releaseMask'):
                roles = bank_module.describe_assignments({'lead': instrument}, self.bank)
                roles['lead']['envelope'][field] = 1
                with self.subTest(instrument=instrument, field=field), self.assertRaisesRegex(ValueError, 'require bowed or sustain'):
                    engine.specialize({}, roles)
        for field in ('attack_mask', 'release_mask'):
            with self.subTest(direct=field), self.assertRaisesRegex(ValueError, 'must be'):
                engine.envelope(1, 'bowed', 15, 'test', **{field: 2})

    def test_default_and_explicit_zero_masks_generate_identical_rom(self):
        # Zero adds no instruction to any existing bank profile, including
        # inactive voices and the unrelated shared piano/pluck decay helper.
        for instrument, profile in self.bank['instruments'].items():
            if any(profile['envelope'].get(phase + 'Mask', 0) for phase in ('attack', 'release')):
                continue
            roles = bank_module.describe_assignments(dict.fromkeys(engine.ROLES, instrument), self.bank)
            source, metadata = engine.specialize({}, roles)
            for role in engine.ROLES:
                roles[role]['envelope'].update(attackMask=0, releaseMask=0)
            explicit_source, explicit_meta = engine.specialize({}, roles)
            with self.subTest(instrument=instrument):
                self.assertEqual(explicit_source, source)
                self.assertEqual(explicit_meta, metadata)
                binaries = []
                for text in (source, explicit_source):
                    (self.folder / 'synth.S').write_text(text, encoding='utf-8', newline='\n')
                    binaries.append(assembler.assemble(self.folder / 'synth.S')[0])
                self.assertEqual(*binaries)

    def test_runtime_envelope_retrigger_rest_and_phase_oracles(self):
        cases = []
        for instrument in ('violin', 'acoustic-grand-piano', 'acoustic-guitar-nylon', 'fretless-bass', 'flute', 'cello', 'clarinet', 'off'):
            assignment = dict.fromkeys(engine.ROLES, instrument)
            source, metadata, binary, labels = self.compile(assignment)
            cases.append(dict(instrument=instrument, roles=bank_module.describe_assignments(assignment, self.bank),
                              meta=metadata, binary=list(binary), labels=labels))
        # Exercise saturation below one attack increment, an optional full
        # sustained retrigger, and a release step that could underflow at level 1.
        roles = bank_module.describe_assignments(dict.fromkeys(engine.ROLES, {'instrument': 'flute', 'level': 3}), self.bank)
        for role in engine.ROLES:
            roles[role]['envelope'].update(attackStep=7, releaseStep=2, retrigger='full')
        source, metadata = engine.specialize({}, roles)
        (self.folder / 'synth.S').write_text(source, encoding='utf-8', newline='\n')
        binary, labels = assembler.assemble(self.folder / 'synth.S')
        cases.append(dict(instrument='custom-sustained-full', roles=roles, meta=metadata, binary=list(binary), labels=labels))
        # The GM50 pad needs attack every other tick and release every eighth
        # tick. Exercise all supported nonzero periods, independent per phase
        # and voice, for both bowed and sustain models. Low caps/steps also
        # expose saturation and release underflow on the selected clock ticks.
        masks = (1, 3, 7, 15)
        for index, mask in enumerate(masks):
            roles = bank_module.describe_assignments(dict(zip(engine.ROLES, ('violin', 'flute', 'cello'))), self.bank)
            for role_index, role in enumerate(engine.ROLES):
                roles[role]['level'] = 3
                roles[role]['envelope'].update(attackStep=1, releaseStep=1 if index == 0 else 2,
                                              attackMask=masks[(index + role_index) % len(masks)],
                                              releaseMask=masks[(index + role_index + 2) % len(masks)])
            source, metadata = engine.specialize({}, roles)
            (self.folder / 'synth.S').write_text(source, encoding='utf-8', newline='\n')
            binary, labels = assembler.assemble(self.folder / 'synth.S')
            for role in engine.ROLES:
                self.assertEqual(metadata[role + '_attack_mask'], roles[role]['envelope']['attackMask'])
                self.assertEqual(metadata[role + '_release_mask'], roles[role]['envelope']['releaseMask'])
            cases.append(dict(instrument=f'masked-{mask}', roles=roles, meta=metadata, binary=list(binary), labels=labels))
        path = self.folder / 'runtime-cases.json'
        path.write_text(json.dumps(cases), encoding='utf-8', newline='\n')
        program = r'''
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore} from './web-player/lib/avr-core.js';
const cases=JSON.parse(fs.readFileSync(process.argv[1]));
const registers=[1,19,20],roles=['lead','keys','pluck'];
const modelNames=['lead_envelope_model','accompaniment_envelope_model','pluck_envelope_model'];
let envelopeChecks=0,retriggerChecks=0,restChecks=0;
function oracle(value,tick,role,meta,profiles){
  const model=meta[modelNames[role]],name=roles[role],cap=meta[name+'_max_level'];
  if(model==='off')return 0;
  if(model==='piano'||model==='pluck'){
    const level=value&15;if(!level)return value;
    if(!(value&128))return Math.max(0,value-meta[name+'_release_step']);
    let period=meta[name+'_decay_mask']+1;
    if(level<10)period*=2;if(level<7)period*=2;
    return value-Number(tick%period===0);
  }
  const phase=value&128?'attackMask':'releaseMask',period=(profiles[name].envelope[phase]??0)+1;
  if(tick%period!==0)return value;
  if(value&128)return Math.min(128+cap,value+meta[name+'_attack_step']);
  if(model==='bowed'&&role===0&&meta[name+'_release_model']==='fast-above-8'){let released=Math.max(0,value-1);if(released&8)released--;return released;}
  return Math.max(0,value-meta[name+'_release_step']);
}
function run(c,target){let steps=0;while(c.pc!==target){c.step();assert.ok(++steps<300,'Control flow reaches boundary');}}
for(const fixture of cases){
  const {meta,labels}=fixture,ep=new Uint8Array(64).fill(0x88);
  const c=new AVRCore(Uint8Array.from(fixture.binary),ep,{fastIdle:false});
  for(const tick of [...Array(32).keys(),254,255])for(let level=0;level<16;level++)for(const held of [false,true]){
    c.pc=labels.music_tick/2;c.r[24]=tick;c.sp=159;c.r[0]=0;
    const prior=registers.map((reg,role)=>{const v=meta[modelNames[role]]==='off'?0:level+(held?128:0);c.r[reg]=v;return v;});
    run(c,labels['.L0a8']/2);
    assert.deepEqual(registers.map(r=>c.r[r]),prior.map((v,role)=>oracle(v,tick+1,role,meta,fixture.roles)),fixture.instrument+' envelope');
    assert.equal(c.r[24],(tick+1)&255,'One shared envelope clock tick, including wrap');
    assert.equal(c.sp,159,'Envelope helper balances stack');envelopeChecks++;
  }
  for(let level=0;level<16;level++){
    c.pc=labels.melodic_event/2;c.r[16]=0;c.r[30]=labels.first_section&255;c.r[31]=labels.first_section>>8;c.r[0]=0;
    c.r[1]=meta.lead_envelope_model==='off'?0:128+level;c.r[2]=0x34;c.r[3]=0x12;c.sp=159;
    run(c,labels.hold_sample/2);
    const expected=meta.lead_envelope_model==='off'?0:128+(meta.lead_retrigger==='half'?level>>1:meta.lead_max_level);
    assert.equal(c.r[1],expected,fixture.instrument+' lead retrigger');assert.equal(c.r[2]|c.r[3]<<8,0x1234,'Lead phase continues');retriggerChecks++;
  }
  for(const frequencies of [[0,1,0,2],[1,0,2,0],[0,0,0,0]]){
    const binary=Uint8Array.from(fixture.binary);binary.set(frequencies,labels.chord_steps);
    const chord=new AVRCore(binary,ep,{fastIdle:false});chord.pc=labels.chord_event/2;chord.r[16]=224;
    chord.r[6]=0x34;chord.r[7]=0x12;chord.r[10]=0x78;chord.r[11]=0x56;
    for(let role=1;role<3;role++)chord.r[registers[role]]=meta[modelNames[role]]==='off'?0:138;
    run(chord,labels.read_event/2);
    for(let role=1;role<3;role++){
      const name=roles[role],sounding=frequencies[(role-1)*2]||frequencies[(role-1)*2+1];
      const expected=meta[modelNames[role]]==='off'||!sounding?0:128+(meta[name+'_retrigger']==='half'?5:meta[name+'_max_level']);
      assert.equal(chord.r[registers[role]],expected,fixture.instrument+' companion rest/retrigger');restChecks++;
    }
    assert.equal(chord.r[6]|chord.r[7]<<8,0x1234,'Keys phase continues');
    assert.equal(chord.r[10]|chord.r[11]<<8,0x5678,'Pluck phase continues');
  }
}
console.log(JSON.stringify({envelopeChecks,retriggerChecks,restChecks}));
'''
        completed = subprocess.run(['node', '--input-type=module', '-e', program, str(path)], cwd=ROOT,
                                   capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        checks = json.loads(completed.stdout)
        self.assertEqual(checks, dict(envelopeChecks=len(cases) * 34 * 16 * 2,
                                     retriggerChecks=len(cases) * 16, restChecks=len(cases) * 6))


if __name__ == '__main__':
    unittest.main(verbosity=2)

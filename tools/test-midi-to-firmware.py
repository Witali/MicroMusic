"""Independent SMF fixtures and end-to-end checks for the one-command converter.

Uses only Python's standard library; Node is required for the AVR playback check.
Fixtures and generated files live in automatically removed OS temporary folders.
No MIDI test file is written into the repository.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('midi_conversion_under_test', ROOT/'tools/midi-to-firmware.py')
conversion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(conversion)


def vlq(value):
    result = [value & 127]
    while value >> 7:
        value >>= 7
        result.append(128 | (value & 127))
    return bytes(reversed(result))


def track(events, end_tick=None):
    # Stable order preserves explicit NoteOff-before-NoteOn at the same tick.
    data = bytearray();previous = 0
    for tick, event in sorted(events, key=lambda e: e[0]):
        data.extend(vlq(tick-previous));data.extend(event);previous = tick
    data.extend(vlq((previous if end_tick is None else end_tick)-previous))
    data.extend(b'\xff\x2f\x00')
    return bytes(data)


def smf(tracks, ppqn=480, format=None):
    format = (0 if len(tracks)==1 else 1) if format is None else format
    return b'MThd'+struct.pack('>IHHH',6,format,len(tracks),ppqn)+b''.join(b'MTrk'+struct.pack('>I',len(t))+t for t in tracks)


def note_events(pitch, start, end, channel=0):
    return [(start,bytes([0x90|channel,pitch,100])),(end,bytes([0x80|channel,pitch,0]))]


def decode_hex(text):
    """Independent Intel HEX checksum/address verification, no assembler reuse."""
    result = {};ended = False
    for line in text.splitlines():
        if not line:continue
        if ended or not line.startswith(':'):raise AssertionError('Invalid HEX framing')
        row = bytes.fromhex(line[1:])
        if len(row)!=row[0]+5 or sum(row)&255:raise AssertionError('Invalid HEX checksum')
        address = int.from_bytes(row[1:3],'big')
        if row[3]==0:
            for i,value in enumerate(row[4:-1]):
                if address+i in result:raise AssertionError('Overlapping HEX data')
                result[address+i]=value
        elif row[3]==1:
            if row[:4]!=b'\x00\x00\x00\x01':raise AssertionError('Invalid EOF')
            ended = True
        else:raise AssertionError('Unexpected extended HEX record')
    if not ended or sorted(result)!=list(range(len(result))):raise AssertionError('Missing EOF or noncontiguous HEX')
    return bytes(result[i] for i in range(len(result)))


class MidiConversionTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='micromusic-midi-test-')
        self.folder=Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def source(self, data, name='input.mid'):
        path=self.folder/name;path.write_bytes(data);return path

    def run_cli(self, *args):
        return subprocess.run([sys.executable,str(ROOT/'tools/midi-to-firmware.py'),*map(str,args)],
            cwd=ROOT,text=True,encoding='utf-8',errors='replace',capture_output=True,timeout=90)

    def fixture(self):
        conductor=track([(0,b'\xff\x51\x03\x07\xa1\x20'),(0,b'\xc0\x00')])
        lead=track(note_events(60,120,360)+note_events(60,360,600)+note_events(62,720,960))
        bass=track([(0,b'\xc1\x23')]+note_events(40,0,120,1)+note_events(40,240,360,1))
        return smf([conductor,lead,bass])

    def score(self, source, **settings):
        notes,ppqn,bpm=conversion.reader.read_midi(source)
        programs,_=conversion.midi_metadata(source)
        return conversion.make_score(notes,ppqn,bpm,settings,programs)

    def test_repeated_note_identity_source_start_and_bass_noteoff_gaps(self):
        score=self.score(self.source(self.fixture()),lead_track=1,bass_track=2)
        self.assertEqual(score['patterns']['intro'],['R:0.25 C4:0.5 C4:0.5 R:0.25 D4:0.5 R:2'])
        self.assertEqual(score['instruments'],{'lead':'acoustic-grand-piano','keys':'fretless-bass','pluck':'off','percussion':'off'})
        self.assertEqual(score['timed_controls']['intro'],[
            {'unit':0,'chord':'bass_40'},{'unit':1,'offMask':2},
            {'unit':2,'chord':'bass_40'},{'unit':3,'offMask':2}])
        self.assertEqual(score['chord_notes']['bass_40'],[40,None])
        self.assertEqual(score['patterns']['silence'],['R:4'])
        self.assertEqual(score['timed_controls']['silence'],[{'unit':0,'offMask':6}])

    def test_channel_program_changes_in_another_track_are_resolved(self):
        data=smf([track([(0,b'\xc2\x49')]),track(note_events(72,0,480,2))])
        score=self.score(self.source(data),lead_track=1)
        self.assertEqual(score['instruments']['lead'],'flute')

    def test_program_change_after_default_piano_requires_explicit_override(self):
        data=smf([track([(480,b'\xc0\x28')]),track(note_events(60,0,240)+note_events(64,480,720))])
        source=self.source(data)
        with self.assertRaisesRegex(ValueError,'changes instruments|explicit'):
            self.score(source,lead_track=1)
        score=self.score(source,lead_track=1,lead_instrument='violin')
        self.assertEqual(score['instruments']['lead'],'violin')

    def test_unknown_gm_requires_explicit_measured_bank_override(self):
        source=self.source(smf([track([(0,b'\xc0\x7f')]+note_events(60,0,480))]))
        output=self.folder/'unknown'
        result=self.run_cli(source,'--output',output)
        self.assertNotEqual(result.returncode,0);self.assertIn('GM program 127',result.stderr)
        self.assertFalse(output.exists())
        score=self.score(source,lead_instrument='flute')
        self.assertEqual(score['instruments']['lead'],'flute')

    def test_selected_bass_ending_is_not_silently_truncated_to_lead_length(self):
        data=smf([track(note_events(72,0,480)),track([(0,b'\xc1\x23')]+note_events(40,0,3840,1))])
        score=self.score(self.source(data),lead_track=0,bass_track=1)
        self.assertEqual(score['conversion']['sourceBars'],2)
        self.assertEqual(sum(len(score['patterns'][p]) for p in score['playlist']),3)
        self.assertEqual(score['patterns']['intro'][1],'R:4')

    def test_existing_output_is_preserved_byte_for_byte(self):
        source=self.source(self.fixture());output=self.folder/'existing';output.mkdir()
        sentinel=output/'synth.hex';sentinel.write_bytes(b'USER EXISTING IMAGE\r\n')
        result=self.run_cli(source,'--output',output,'--lead-track',1)
        self.assertNotEqual(result.returncode,0);self.assertIn('Output already exists',result.stderr)
        self.assertEqual(sentinel.read_bytes(),b'USER EXISTING IMAGE\r\n')
        self.assertEqual([p.name for p in output.iterdir()],['synth.hex'])

    def test_zero_bars_and_zero_tempo_are_rejected_instead_of_ignored(self):
        source=self.source(self.fixture())
        for option in ('--bars','--tempo'):
            with self.subTest(option=option):
                output=self.folder/option[2:]
                result=self.run_cli(source,'--output',output,'--lead-track',1,option,0)
                self.assertNotEqual(result.returncode,0)
                self.assertFalse(output.exists())

    def test_subgrid_bass_notes_can_disappear_without_breaking_the_build(self):
        source=self.source(smf([track(note_events(72,0,480)),track([(0,b'\xc1\x23')]+note_events(40,0,60,1))]))
        output=self.folder/'short-bass'
        result=self.run_cli(source,'--output',output,'--lead-track',0,'--bass-track',1)
        self.assertEqual(result.returncode,0,result.stderr)
        score=json.loads((output/'score.json').read_text(encoding='utf-8'))
        self.assertEqual(score['timed_controls']['intro'],[])

    def test_budget_rejection_leaves_no_output_directory(self):
        rng=random.Random(710)
        events=[]
        for i in range(1024):events.extend(note_events(60+rng.randrange(24),i*120,(i+1)*120))
        source=self.source(smf([track(events)]));output=self.folder/'too-large'
        result=self.run_cli(source,'--output',output,'--candidates',8)
        self.assertNotEqual(result.returncode,0);self.assertIn('Conversion failed',result.stderr)
        self.assertFalse(output.exists())

    def test_malformed_smf_fails_cleanly_and_leaves_no_output(self):
        note_track=track(note_events(60,0,480))
        valid=smf([note_track])
        malformed={
            'short-header':b'MThd',
            'zero-ppqn':smf([note_track],ppqn=0),
            'missing-track':valid[:14],
            'truncated-channel':smf([b'\x00\x90\x3c']),
            'truncated-meta':smf([note_track[:-4]+b'\x00\xff\x03\x08a']),
            'oversized-chunk':valid[:18]+struct.pack('>I',len(note_track)+8)+valid[22:],
            'running-status-without-event':smf([b'\x00\x3c\x40']),
            'truncated-sysex':smf([note_track[:-4]+b'\x00\xf0\x08\x01']),
            'overlong-vlq':smf([b'\x81\x81\x81\x81\x00\x90\x3c\x40']),
            'smpte-division':smf([note_track],ppqn=0xe728),
            'format2':smf([note_track],format=2),
        }
        for name,data in malformed.items():
            with self.subTest(name=name):
                output=self.folder/name
                result=self.run_cli(self.source(data,name+'.mid'),'--output',output)
                self.assertNotEqual(result.returncode,0,name)
                self.assertNotIn('Traceback',result.stderr,name)
                self.assertFalse(output.exists(),name)

    def test_solo_soft_piano_and_explicit_flute_approximation_build(self):
        source=self.source(smf([track(note_events(72,0,480)+note_events(72,480,960))]))
        for instrument,slots in (('acoustic-grand-piano-soft',2),('flute',0)):
            with self.subTest(instrument=instrument):
                output=self.folder/instrument
                result=self.run_cli(source,'--output',output,'--lead-instrument',instrument)
                self.assertEqual(result.returncode,0,result.stderr)
                score=json.loads((output/'score.json').read_text(encoding='utf-8'))
                report=json.loads((output/'build-report.json').read_text(encoding='utf-8'))
                self.assertEqual(score['instruments']['lead'],instrument)
                self.assertEqual(score.get('release_tail_slots',0),slots)
                self.assertEqual(report.get('releaseChannels',{}).get('tailSlots',0),slots)
                self.assertEqual((output/'eeprom.bin').read_bytes(),conversion.builder.bank.build_eeprom(score['instruments']))

    def test_cyrillic_input_and_output_paths_work_with_windows_stdio(self):
        source=self.source(smf([track(note_events(72,0,480))]),'Мелодия с пробелами.mid')
        output=self.folder/'Новая прошивка'
        result=self.run_cli(source,'--output',output,'--name','Русское название')
        self.assertEqual(result.returncode,0,result.stderr)
        retained=json.loads((output/'source-events.json').read_text(encoding='utf-8'))
        self.assertEqual(retained['source']['sha256'],hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertTrue((output/'synth.hex').is_file())

    def test_config_cli_overrides_reproducible_images_and_real_avr_clean_loop(self):
        source=self.source(self.fixture());output=self.folder/'firmware'
        config=self.folder/'config.json'
        config.write_text(json.dumps(dict(input=str(source),output=str(output),lead_track=1,bass_track=2,
            tempo=90,candidates=128,name='Fixture title')),encoding='utf-8')
        result=self.run_cli('--config',config,'--tempo',120,'--name','CLI title')
        self.assertEqual(result.returncode,0,result.stderr)
        expected_files={'source-events.json','score.json','score.inc','config.inc','conversion.json','synth.S','synth.bin','synth.hex',
            'eeprom.bin','eeprom.hex','build-report.json','avr_core.js','FluidR3-MIT.txt','player.html'}
        self.assertTrue(expected_files.issubset({p.name for p in output.iterdir()}))
        score=json.loads((output/'score.json').read_text(encoding='utf-8'))
        report=json.loads((output/'build-report.json').read_text(encoding='utf-8'))
        self.assertEqual(score['release_tail_slots'],2)
        self.assertEqual(report['releaseChannels']['tailSlots'],2)
        self.assertEqual(report['releaseChannels']['pwmRingBytes'],16)
        self.assertEqual(score['tempo_bpm'],120);self.assertEqual(score['title'],'CLI title')
        self.assertEqual(score['source_midi']['file'],'source-events.json')
        self.assertEqual(score['source_midi']['originalMidiSha256'],hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(score['source_midi']['sha256'],hashlib.sha256((output/'source-events.json').read_bytes()).hexdigest())
        retained=json.loads((output/'source-events.json').read_text(encoding='utf-8'))
        self.assertEqual(retained['source']['sha256'],hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(conversion.reader.read_midi(output/'source-events.json'),conversion.reader.read_midi(source))
        self.assertFalse(any(p.suffix.lower() in ('.mid','.midi') for p in output.rglob('*')))
        self.assertEqual(decode_hex((output/'synth.hex').read_text()),(output/'synth.bin').read_bytes())
        self.assertEqual(decode_hex((output/'eeprom.hex').read_text()),(output/'eeprom.bin').read_bytes())
        self.assertLessEqual(report['flashBytes'],1024);self.assertEqual(report['eepromBytes'],64)
        self.assertEqual(report['flashSha256'],hashlib.sha256((output/'synth.bin').read_bytes()).hexdigest())
        self.assertEqual((output/'eeprom.bin').read_bytes(),conversion.builder.bank.build_eeprom(score['instruments']))
        output2=self.folder/'again'
        result=self.run_cli('--config',config,'--output',output2,'--tempo',120,'--name','CLI title')
        self.assertEqual(result.returncode,0,result.stderr)
        for name in ('synth.bin','eeprom.bin','synth.S','score.inc','config.inc'):
            self.assertEqual((output/name).read_bytes(),(output2/name).read_bytes(),name)
        if shutil.which('node') is None:self.skipTest('Node is required for actual AVR playback')
        # The VM executes the produced image. No JS substitute for the score,
        # envelopes, tail channels or PWM samples is used by this check.
        node_source="""
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const folder=process.argv[1];
const {AVRCore}=await import(pathToFileURL(process.cwd()+'/web-player/lib/avr-core.js'));
const m=JSON.parse(fs.readFileSync(folder+'/build-report.json'));
const rom=fs.readFileSync(folder+'/synth.bin'),c=new AVRCore(rom,fs.readFileSync(folder+'/eeprom.bin'));
let samples=0,nonzero=0,checked=false,events=0,underruns=0;
const step=c.step.bind(c),labels=m.labels;
c.step=()=>{
 if(!c.inIRQ&&c.pc===labels.read_event/2){
  events++;
  if(c.cyc>9600000*3.8&&!checked){
   const amps=m.releaseChannels?m.releaseChannels.voiceAddresses.map(a=>c.data[a]&15):[c.r[1]&15,c.r[19]&15,c.r[20]&15];
   assert.ok(amps.every(v=>v===0),'all voices silent before restart');checked=true;
  }
 }
 if(c.inIRQ&&labels.ring_read!==undefined&&c.pc===labels.ring_read/2&&((c.r[22]-c.r[28]+16)&15)===0)underruns++;
 step();
};
while(c.cyc<9600000*4.1){const duty=c.nextDuty();samples++;if(duty!==128)nonzero++;}
assert.ok(checked&&events>0&&nonzero>0);assert.equal(c.lost,0);assert.equal(c.workLost,0);assert.equal(underruns,0);
console.log(JSON.stringify({samples,nonzero,events,maxISR:c.maxIRQ,ringUnderruns:underruns}));
"""
        playback=subprocess.run(['node','--input-type=module','-e',node_source,str(output)],cwd=ROOT,
            text=True,encoding='utf-8',capture_output=True,timeout=30)
        self.assertEqual(playback.returncode,0,playback.stderr)


if __name__=='__main__':unittest.main()

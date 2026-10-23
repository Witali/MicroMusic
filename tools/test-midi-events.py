"""Structured-event import regression tests; SMF fixtures exist only in OS_TEMP."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


def module(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/filename)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


events=module('json_events_under_test','midi-events.py')
fixtures=module('external_smf_fixtures','test-midi-to-firmware.py')
smf,track,note_events=fixtures.smf,fixtures.track,fixtures.note_events


class EventJsonTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='micromusic-events-test-')
        self.folder=Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def source(self,data,name='external.mid'):
        result=self.folder/name;result.write_bytes(data);return result

    def test_all_channel_message_fields_meta_sysex_order_and_source_hash(self):
        data=smf([track([
            (0,b'\xff\x03\x04Lead'),(0,b'\xff\x51\x03\x07\xa1\x20'),
            (0,b'\xff\x58\x04\x06\x03\x18\x08'),(0,b'\x92\x3c\x64'),
            (10,b'\xa2\x3c\x16'),(20,b'\xb2\x40\x7f'),(30,b'\xc2\x28'),
            (40,b'\xd2\x37'),(50,b'\xe2\x01\x41'),(60,b'\x82\x3c\x40'),
            (70,b'\x92\x3e\x00'),(80,b'\xf0\x03\x01\x02\xf7'),
            (90,b'\xf7\x02\x03\x04'),(100,b'\xff\x7f\x04\xde\xad\xbe\xef'),
            (110,b'\xff\x02\x04Caf\xe9')],end_tick=120)])
        source=self.source(data);document=events.from_midi(source);row=document['tracks'][0]
        self.assertEqual(document['source'],{'fileName':'external.mid','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        self.assertEqual(document['schema'],'micromusic-midi-events');self.assertEqual(document['version'],1)
        self.assertEqual(document['format'],0);self.assertEqual(document['ppqn'],480)
        self.assertEqual(row['name'],'Lead')
        kinds={e['type']:e for e in row['events']}
        self.assertEqual(kinds['polyphonicPressure']['pressure'],22)
        self.assertEqual((kinds['controlChange']['controller'],kinds['controlChange']['value']),(64,127))
        self.assertEqual(kinds['programChange']['program'],40)
        self.assertEqual(kinds['channelPressure']['pressure'],55)
        self.assertEqual(kinds['pitchBend']['value'],8321)
        self.assertEqual(kinds['noteOff']['velocity'],64)
        self.assertEqual(kinds['noteOn']['velocity'],0,'Zero-velocity NoteOn remains an original event')
        self.assertEqual([(e['status'],e['dataHex']) for e in row['events'] if e['type']=='systemExclusive'],[(240,'0102f7'),(247,'0304')])
        self.assertEqual(kinds['meta']['dataHex'],'deadbeef')
        self.assertEqual(kinds['text']['text'],'Café')
        self.assertEqual(kinds['timeSignature']['numerator'],6);self.assertEqual(kinds['timeSignature']['denominator'],8)
        self.assertEqual(document['tempoMap'][0]['bpm'],120)
        self.assertEqual(row['summary']['noteOnCount'],1)
        self.assertEqual(row['summary']['instruments'][0]['program'],0,'Later ProgramChange cannot change an earlier NoteOn')
        tick=0
        for event in row['events']:
            tick+=event['delta'];self.assertEqual(event['tick'],tick)
        self.assertEqual(events.notes(document),([(0,2,60,0,60,100)],480,120))

    def test_running_status_is_expanded_without_losing_ticks_or_zero_noteoffs(self):
        source=self.source(smf([b'\x00\x90\x3c\x64\x0a\x3d\x6e\x0a\x3c\x00\x0a\x3d\x00\x00\xff\x2f\x00']))
        document=events.from_midi(source)
        self.assertEqual([e['status'] for e in document['tracks'][0]['events']],[144,144,144,144,255])
        self.assertEqual(events.notes(document)[0],[(0,0,60,0,20,100),(0,0,61,10,30,110)])
        for reset in (b'\x00\xff\x01\x01x',b'\x00\xf0\x01\xf7'):
            with self.subTest(reset=reset.hex()):
                invalid=self.source(smf([b'\x00\x90\x3c\x64'+reset+b'\x00\x3d\x6e']))
                with self.assertRaisesRegex(ValueError,'running'):events.from_midi(invalid)

    def test_overlapping_equal_pitches_use_fifo_and_last_tick_closes_open_notes(self):
        data=smf([track([(0,b'\x90\x3c\x0a'),(10,b'\x90\x3c\x14'),(15,b'\x90\x40\x1e'),
                         (20,b'\x80\x3c\x00'),(30,b'\x90\x3c\x00')],end_tick=50)])
        self.assertEqual(events.notes(events.from_midi(self.source(data)))[0],
            [(0,0,60,0,20,10),(0,0,60,10,30,20),(0,0,64,15,50,30)])

    def test_channel_wide_program_summary_and_percussion_are_human_readable(self):
        data=smf([track([(20,b'\xc0\x28')]),
            track([(0,b'\xff\x03\x04Tune')]+note_events(60,0,10)+note_events(64,20,40)),
            track(note_events(42,0,10,9))])
        document=events.from_midi(self.source(data));summary=document['tracks'][1]['summary']
        self.assertEqual([r['program'] for r in summary['instruments']],[0,40])
        self.assertTrue(all(r['name'] for r in summary['instruments']))
        self.assertEqual(document['tracks'][1]['name'],'Tune')
        self.assertEqual(summary['pitchRange'],[60,64])
        self.assertTrue(document['tracks'][2]['summary']['instruments'][0]['percussion'])
        self.assertEqual(document['tracks'][2]['summary']['instruments'][0]['name'],'GM percussion')

    def test_json_roundtrip_and_reader_have_identical_notes_source_sha_and_metadata(self):
        source=self.source(smf([track(note_events(60,0,480))]))
        document=events.from_midi(source);path=self.folder/'retained.json'
        path.write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        self.assertEqual(events.load(path),document)
        self.assertEqual(events.notes(events.load(path)),fixtures.conversion.reader.read_midi(source))
        self.assertEqual(fixtures.conversion.reader.read_midi(path),fixtures.conversion.reader.read_midi(source))
        self.assertEqual(document['source']['sha256'],hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertFalse(any(k in document for k in ('midiBase64','rawMidi','binary')))

    def test_schema_and_ordered_integer_ticks_are_validated(self):
        valid=events.from_midi(self.source(smf([track(note_events(60,0,480))])))
        changed=[]
        for key,value in (('schema','unknown'),('version',2),('ppqn',0)):
            row=copy.deepcopy(valid);row[key]=value;changed.append(row)
        for tick in (-1,.5,'0'):
            row=copy.deepcopy(valid);row['tracks'][0]['events'][0]['tick']=tick;changed.append(row)
        row=copy.deepcopy(valid);row['tracks'][0]['events'][-1]['tick']=100;changed.append(row)
        for i,row in enumerate(changed):
            with self.subTest(case=i):
                path=self.folder/'invalid.json';path.write_text(json.dumps(row),encoding='utf-8')
                with self.assertRaises(ValueError):events.load(path)

    def test_header_extension_and_trailing_payload_are_retained_as_structured_hex(self):
        raw=smf([track(note_events(60,0,480))])
        extended=raw[:4]+struct.pack('>I',8)+raw[8:14]+b'\xaa\x55'+raw[14:]+b'\x00\x01'
        document=events.from_midi(self.source(extended))
        self.assertEqual(document['headerExtraHex'],'aa55');self.assertEqual(document['trailingDataHex'],'0001')

    def test_invalid_tempo_is_rejected_without_division_by_zero(self):
        for payload in (b'\x00\x00\x00', b'\x01\x02'):
            raw=smf([b'\x00\xff\x51'+bytes([len(payload)])+payload+b'\x00\xff\x2f\x00'])
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                events.from_midi(self.source(raw))
        document=events.from_midi(self.source(smf([track(note_events(60,0,480))])))
        for tempo in (0,-1,.5,'500000',0x1000000):
            row=copy.deepcopy(document)
            row['tracks'][0]['events'].insert(0,dict(type='tempo',tick=0,microsecondsPerQuarter=tempo))
            path=self.folder/'invalid-tempo.json';path.write_text(json.dumps(row),encoding='utf-8')
            with self.subTest(tempo=tempo), self.assertRaises(ValueError):events.load(path)

    def test_cli_cyrillic_paths_write_only_event_json(self):
        source=self.source(smf([track(note_events(60,0,480))]),'Внешняя мелодия.mid')
        destination=self.folder/'результат'/'Ноты.json'
        result=subprocess.run([sys.executable,str(ROOT/'tools/midi-events.py'),str(source),str(destination)],
            cwd=ROOT,text=True,encoding='utf-8',errors='replace',capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(events.load(destination)['source']['sha256'],hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual([p.suffix for p in destination.parent.iterdir()],['.json'])


if __name__=='__main__':unittest.main()

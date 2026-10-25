"""Real external-MIDI/JSON pipeline and atomic failure regressions.

Raw MIDI exists only in OS temporary storage and is removed after the test.
Requires the same AVR toolchain as the firmware builder.
"""
from pathlib import Path
import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


pipeline=module('pipeline_under_test','compile-universal-music.py')
fixtures=module('um_pipeline_smf_fixtures','test-midi-to-firmware.py')


class Pipeline(unittest.TestCase):
    def setUp(self):
        (ROOT/'build/universal').mkdir(parents=True,exist_ok=True)
        self.work=tempfile.TemporaryDirectory(dir=ROOT/'build/universal',prefix='pipeline-test-')
        self.external=tempfile.TemporaryDirectory(prefix='external-um88-midi-')
        self.addCleanup(self.work.cleanup);self.addCleanup(self.external.cleanup)
        self.folder=Path(self.work.name)
        self.config=self.folder/'arrangement.json'
        self.config.write_text(json.dumps(dict(schema='micromusic-um88-arrangement',version=1,name='pipeline-test',
                                instruments={'1':'flute'},tracks=[1])),encoding='utf-8')

    def test_real_external_midi_retains_events_and_produces_audited_mono_package(self):
        raw=fixtures.smf([fixtures.track([(0,b'\xc0\x49'),(0,b'\xff\x51\x03\x07\xa1\x20'),
                              (240,b'\xff\x51\x03\x06\x1a\x80')],end_tick=480),
                          fixtures.track(fixtures.note_events(60,0,240)+[(120,b'\xd0\x30')],end_tick=480)])
        source=Path(self.external.name)/'external.mid';source.write_bytes(raw)
        with contextlib.redirect_stdout(io.StringIO()):
            result=pipeline.compile_music(source,self.config,self.folder/'result',backend='avr-asm')
        retained=json.loads((result/'source-events.json').read_text(encoding='utf-8'))
        self.assertEqual(retained['source']['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(retained['tracks']),2)
        kinds={e['type'] for t in retained['tracks'] for e in t['events']}
        self.assertTrue({'tempo','noteOn','noteOff','programChange','channelPressure'}<=kinds)
        self.assertFalse(any(p.suffix.lower() in ('.mid','.midi','.smf') for p in result.rglob('*')))
        package=json.loads((result/'player-package.json').read_text(encoding='utf-8'))
        self.assertTrue(package['verification']['allPwmFramesMatch']);self.assertEqual(package['score']['channels'],1)
        self.assertEqual(package['arrangementReport']['ignoredEvents'],{'channelPressure':1})
        self.assertTrue((result/'FluidR3-MIT.txt').exists())

    def test_existing_output_is_preserved_before_reading_inputs(self):
        output=self.folder/'existing';output.mkdir();marker=output/'keep.txt';marker.write_text('keep')
        with self.assertRaisesRegex(ValueError,'already exists'):
            pipeline.compile_music(self.folder/'missing.json',self.config,output)
        self.assertEqual(marker.read_text(),'keep')

    def test_unsupported_json_does_not_publish_partial_output(self):
        source=self.folder/'invalid.json';source.write_text('{}')
        with self.assertRaises(ValueError):pipeline.compile_music(source,self.config,self.folder/'result')
        self.assertFalse((self.folder/'result').exists())

    def test_c_deadline_failure_keeps_diagnostics_without_publishing(self):
        events=[]
        for note in (60,62,64,65,67):events+=fixtures.note_events(note,0,480)
        source=Path(self.external.name)/'five.mid';source.write_bytes(fixtures.smf([fixtures.track(events,end_tick=480)]))
        self.config.write_text(json.dumps(dict(schema='micromusic-um88-arrangement',version=1,name='pipeline-test-c-fail',
                                voices=5,instruments={'0':'flute'})),encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,'FIFO underrun.*diagnostic report'):
            pipeline.compile_music(source,self.config,self.folder/'not-published',backend='c')
        self.assertFalse((self.folder/'not-published').exists())
        diagnostic=ROOT/'build/universal/failures/pipeline-test-c-fail-c-8000000.json'
        self.assertFalse(json.loads(diagnostic.read_text(encoding='utf-8'))['passed'])

    def test_excessive_explicit_gain_is_rejected_without_publishing(self):
        events=[]
        for note in (60,64,67):events+=fixtures.note_events(note,0,480)
        source=Path(self.external.name)/'loud.mid';source.write_bytes(fixtures.smf([fixtures.track(events,end_tick=480)]))
        self.config.write_text(json.dumps(dict(schema='micromusic-um88-arrangement',version=1,name='pipeline-test-clips',
                                voices=3,gainShift=0,instruments={'0':'flute'})),encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,'PWM clipping.*diagnostic report'):
            pipeline.compile_music(source,self.config,self.folder/'not-published',backend='avr-asm')
        self.assertFalse((self.folder/'not-published').exists())


if __name__=='__main__':unittest.main()

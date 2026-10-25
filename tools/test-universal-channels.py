"""Check fixed-channel header selection and per-profile UM88 builder output."""
from pathlib import Path
from unittest.mock import patch
import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('channel_builder',ROOT/'tools/build-universal-music.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


def fixture(name,channels):
    return dict(schema='micromusic-um88-score',version=1,name=name,voices=2,channels=channels,
                waves=[i|(15-i)<<4 for i in range(16)]*4,contexts=[[0,0,1,128]],
                envelopes=[[v for level in range(16) for v in (level,0,0)]],pitches=[None,60],
                commands=[64,0,72,1,143,65,0,73,1,159,32,0],controlTicks=32,
                groupGain=False,normalizer=[],normalizerMinimum=0,masterShift=0,
                source=dict(kind='original deterministic channel fixture',license='CC0-1.0',
                            events=[dict(tick=0,program=24,note=60)]))


class Selection(unittest.TestCase):
    def test_retained_auto_groups_and_explicit_overrides(self):
        scores=[(ROOT/'ATtiny88/Music/universal/songs'/name/'score.json',
                 json.loads((ROOT/'ATtiny88/Music/universal/songs'/name/'score.json').read_text(encoding='utf-8')))
                for name in builder.NAMES]
        original=copy.deepcopy(scores)
        groups=builder.channel_groups(scores,'auto')
        self.assertEqual({n:len(rows) for n,rows in groups.items()},{1:8,2:1})
        for selection,channels in [('mono',1),('stereo',2)]:
            rows=builder.channel_groups(scores,selection)[channels]
            self.assertEqual(len(rows),9)
            for row,(_,source) in zip(rows,scores):
                self.assertEqual(row['sourceChannels'],source['channels'])
                self.assertEqual(row['score'],dict(source,channels=channels))
        self.assertEqual(scores,original,'Channel selection leaves all source content intact')

    def test_invalid_channel_settings_rejected(self):
        for channels in (0,3,True,'mono'):
            with self.assertRaisesRegex(ValueError,'Source channels'):
                builder.channel_groups([(Path('fixture.json'),fixture('fixture',channels))],'auto')


class CompiledChannels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools=builder.legacy.toolchain(None)
        (ROOT/'build/universal').mkdir(parents=True,exist_ok=True)

    def evaluate(self,definition='',request=None,assembly=False):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/universal',prefix='channel-header-') as work:
            folder=Path(work);source=folder/('channel.S' if assembly else 'channel.c')
            obj=folder/'channel.o';binary=folder/'channel.bin'
            value=('.section .channels,"a",@progbits\n.byte UM_OUTPUT_CHANNELS\n' if assembly else
                   '#include <stdint.h>\nconst uint8_t channel __attribute__((section(".channels")))=UM_OUTPUT_CHANNELS;\n')
            source.write_text(definition+'\n#include "audio-channels.h"\n'+value)
            command=[str(self.tools['avr-gcc']),'-mmcu=attiny88','-I'+str(ROOT/'ATtiny88/Music/universal')]
            if request is not None:command+=['-DUM_REQUESTED_OUTPUT_CHANNELS='+str(request)]
            result=subprocess.run(command+['-c',str(source),'-o',str(obj)],capture_output=True,text=True)
            if result.returncode:return None,result.stderr
            builder.legacy.run(self.tools['avr-objcopy'],'-O','binary','-j','.channels',obj,binary)
            return int.from_bytes(binary.read_bytes(),'little'),''

    def test_default_explicit_and_assembler_safe_header(self):
        for assembly in (False,True):
            self.assertEqual(self.evaluate(assembly=assembly)[0],1)
            for channels in (1,2):
                self.assertEqual(self.evaluate(request=channels,assembly=assembly)[0],channels)
            self.assertEqual(self.evaluate('#define UM_OUTPUT_CHANNELS (1 + 1)',2,assembly)[0],2)

    def test_header_conflicts_and_invalid_counts(self):
        for assembly in (False,True):
            value,message=self.evaluate('#define UM_OUTPUT_CHANNELS 2',1,assembly)
            self.assertIsNone(value);self.assertIn('disagrees',message)
            for channels in (0,3,-1):
                self.assertIsNone(self.evaluate(request=channels,assembly=assembly)[0])
                self.assertIsNone(self.evaluate('#define UM_OUTPUT_CHANNELS '+str(channels),assembly=assembly)[0])

    def check_output(self,folder,source,selection,channels,backend,board='bare-8mhz'):
        score=json.loads((folder/'score.json').read_text(encoding='utf-8'))
        report=json.loads((folder/'build-report.json').read_text(encoding='utf-8'))
        image=(folder/'synth.bin').read_bytes()
        self.assertEqual(score,dict(source,channels=channels))
        self.assertEqual(report['sourceChannels'],source['channels'])
        self.assertEqual(report['configuredChannels'],channels)
        self.assertEqual(report['channels'],channels)
        self.assertEqual(report['channelSelection'],selection)
        self.assertEqual(report['renderABI'],'mono-s16' if channels==1 else 'packed-stereo-u32')
        self.assertEqual(report['backend'],backend)
        self.assertNotIn('um_channels',report['labels'])
        self.assertEqual(report['pwmBufferFrames'],report['pwmBufferBytes']//channels)
        self.assertEqual(image[report['songAddress']:report['songAddress']+6],b'UM88'+bytes([2,channels]))
        self.assertLessEqual(report['songPaddingBytes'],2)
        self.assertEqual(report['songAddress']&1,0)
        self.assertEqual(report['songAddress']-report['engineBytes'],report['songPaddingBytes'])
        self.assertEqual(hashlib.sha256(image).hexdigest(),report['flashSha256'])
        self.assertIn('ATtiny88/Music/universal/audio-channels.h',report['sourceInputs'])
        self.assertEqual(report['applicationFlashLimit'],6012 if board=='mh-et-live-16mhz' else 8192)
        self.assertLessEqual(len(image),report['applicationFlashLimit'])
        if board=='mh-et-live-16mhz':
            self.assertTrue(report['preserveFactoryFuses'])
            self.assertFalse(report['eepromRequired'])
            self.assertEqual(report['deviceDefinitions']['version'],'3.4.278')
        return report

    def test_both_explicit_choices_and_backends_preserve_sources(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/universal',prefix='channel-builder-') as work:
            folder=Path(work)
            for backend,selection,source_channels in [('c','mono',2),('c','stereo',1),
                                                       ('avr-asm','mono',2),('avr-asm','stereo',1)]:
                source=fixture('channel-fixture',source_channels)
                score_path=folder/'source.json';score_path.write_text(json.dumps(source))
                before=score_path.read_bytes();output=folder/(backend+'-'+selection)
                builder.legacy.run(sys.executable,ROOT/'tools/build-universal-music.py','--score',score_path,
                                   '--backend',backend,'--channels',selection,'--output-dir',output)
                self.check_output(output/source['name'],source,selection,1 if selection=='mono' else 2,backend)
                self.assertEqual(score_path.read_bytes(),before)

    def test_mixed_auto_catalog_has_one_core_per_channel_profile(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/universal',prefix='channel-catalog-') as work:
            output=Path(work);calls=[];run=builder.legacy.run
            def capture(*args):
                if '-DUM_SONG_ADDRESS=0' in args:
                    calls.append(next(a for a in args if str(a).startswith('-DUM_REQUESTED_OUTPUT_CHANNELS=')))
                return run(*args)
            names=('greensleeves','rhythmic','lumiere-stereo')
            with patch.object(builder,'NAMES',names),patch.object(builder.legacy,'run',capture),\
                 patch.object(sys,'argv',['build-universal-music.py','--backend','avr-asm','--output-dir',str(output)]):
                builder.main()
            self.assertEqual(calls,['-DUM_REQUESTED_OUTPUT_CHANNELS=1','-DUM_REQUESTED_OUTPUT_CHANNELS=2'])
            summary=json.loads((output/'build-report.json').read_text())
            self.assertNotIn('engineSha256',summary,'A mixed summary must not claim one shared core')
            self.assertEqual([p['configuredChannels'] for p in summary['profiles']],[1,2])
            self.assertEqual([len(p['songs']) for p in summary['profiles']],[2,1])
            reports=[json.loads((output/name/'build-report.json').read_text()) for name in names]
            self.assertEqual(reports[0]['engineSha256'],reports[1]['engineSha256'])
            self.assertNotEqual(reports[0]['engineSha256'],reports[2]['engineSha256'])
            for profile in summary['profiles']:
                name='mono' if profile['configuredChannels']==1 else 'stereo'
                snapshot=ROOT/'build/universal'/name/'engine-avr-asm.bin'
                self.assertEqual(hashlib.sha256(snapshot.read_bytes()).hexdigest(),profile['engineSha256'])

    def test_mixed_platform_conflict_writes_no_output(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/universal',prefix='channel-conflict-') as work:
            folder=Path(work);output=folder/'output';header=folder/'platform.h'
            header.write_text('#define UM_OUTPUT_CHANNELS 1\n')
            snapshots=[ROOT/'build/universal'/profile/('engine-avr-asm.'+extension)
                       for profile in ('','mono','stereo') for extension in ('bin','json')]
            before={path:path.read_bytes() if path.exists() else None for path in snapshots}
            with patch.object(builder,'NAMES',('greensleeves','lumiere-stereo')),\
                 patch.object(sys,'argv',['build-universal-music.py','--backend','avr-asm',
                              '--platform-header',str(header),'--output-dir',str(output)]):
                with self.assertRaisesRegex(RuntimeError,'disagrees'):
                    builder.main()
            self.assertFalse(output.exists(),'No song or summary may be published before channel preflight')
            self.assertEqual({path:path.read_bytes() if path.exists() else None for path in snapshots},before,
                             'Rejected mixed builds must leave existing core snapshots intact')

    def test_conversion_cannot_overwrite_its_source_score(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/universal',prefix='channel-source-') as work:
            output=Path(work);folder=output/'source-fixture';folder.mkdir()
            score_path=folder/'score.json';score_path.write_text(json.dumps(fixture(folder.name,2)))
            source_before=score_path.read_bytes()
            snapshots=[ROOT/'build/universal'/profile/('engine-avr-asm.'+extension)
                       for profile in ('','mono','stereo') for extension in ('bin','json')]
            before={path:path.read_bytes() if path.exists() else None for path in snapshots}
            with patch.object(sys,'argv',['build-universal-music.py','--backend','avr-asm',
                              '--score',str(score_path),'--channels','mono','--output-dir',str(output)]):
                with self.assertRaisesRegex(ValueError,'overwrite its source'):
                    builder.main()
            self.assertEqual(score_path.read_bytes(),source_before)
            self.assertEqual(list(folder.iterdir()),[score_path],'Rejected conversion publishes no song files')
            self.assertFalse((output/'build-report.json').exists())
            self.assertEqual({path:path.read_bytes() if path.exists() else None for path in snapshots},before)

    def test_explicit_default_directory_and_micronucleus_limit(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/universal',prefix='channel-default-') as work:
            name=Path(work).name;source=fixture(name,2);score_path=Path(work)/'source.json'
            score_path.write_text(json.dumps(source));before=score_path.read_bytes()
            output=ROOT/'build/universal/avr-asm-mono-micronucleus'/name
            self.assertFalse(output.exists())
            try:
                builder.legacy.run(sys.executable,ROOT/'tools/build-universal-music.py','--score',score_path,
                                   '--backend','avr-asm','--channels','mono','--board','mh-et-live-16mhz')
                self.check_output(output,source,'mono',1,'avr-asm','mh-et-live-16mhz')
                self.assertEqual(score_path.read_bytes(),before)
                header=Path(work)/'platform.h';header.write_text('#define UM_OUTPUT_CHANNELS 2\n')
                result=subprocess.run([sys.executable,str(ROOT/'tools/build-universal-music.py'),
                    '--score',str(score_path),'--channels','mono','--platform-header',str(header),
                    '--output-dir',str(Path(work)/'conflict')],cwd=ROOT,capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0);self.assertIn('disagrees',result.stderr)
            finally:
                self.assertTrue(output.is_relative_to(ROOT/'build/universal'))
                if output.exists():shutil.rmtree(output)


if __name__=='__main__':unittest.main()

"""Real AVR inputs and host validation must invalidate separate cache layers."""
import copy,json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import benchmark_speech_flash as factory
import measure_speech_firmware as collector
from speech_compact import repack,decode_model
from test_speech_v4 import fixture
from standard_metrics import pwm_duties


class MeasurementProvenanceTests(unittest.TestCase):
    def test_compilation_inventory_excludes_uncompiled_model_oracles(self):
        src=factory.ROOT/'src';compiled=factory.compilation_sources(src)
        self.assertTrue({'Lpx4HybridCore.cpp','Lpx4HybridCore.h','Lpx4Math.h'}<=set(compiled))
        self.assertNotIn('cos_table.inc',compiled);self.assertNotIn('scale_table.inc',compiled)
        env={'source_sha256':{'compiled':'a','oracle':'old'},'compile_source_sha256':{'compiled':'a'},
             'dependencies':{'avr-g++':'x'},'harness_sha256':'h','settings':dict(factory.BASE),'compact_only':True}
        reference=factory.build_provenance(env);env['source_sha256']['oracle']='new';env['host']='new'
        self.assertEqual(factory.build_provenance(env),reference)
        env['compile_source_sha256']['compiled']='b'
        self.assertNotEqual(factory.build_provenance(env),reference)
        with patch.object(factory,'validation_sources',return_value={'model':'first'}):
            first=factory.validation_provenance(runtime={'runner':'r'})
        with patch.object(factory,'validation_sources',return_value={'model':'changed'}):
            second=factory.validation_provenance(runtime={'runner':'r'})
        self.assertNotEqual(first,second)

    def test_alternate_harness_and_default_abi_do_not_read_runner_sources(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);avr=folder/'bin';avr.mkdir();cc1=folder/'cc1plus';cc1.write_bytes(b'cc1')
            for name in ('avr-g++','avr-as','avr-ld'):
                factory.toolpath(avr,name).write_bytes(name.encode())
            harness=folder/'release.cpp';harness.write_text('// release-only harness')
            def output(command,**kwargs):
                if '-print-prog-name=cc1plus' in command:return str(cc1)
                if '--version' in command:return 'test AVR compiler\n'
                return str(folder/'absent')
            with patch.object(factory.subprocess,'check_output',side_effect=output):
                env=factory.environment(factory.ROOT/'src',avr,True,harness=harness,required_symbols=(),retained_symbols=())
                self.assertEqual(env['required_symbols'],[]);self.assertEqual(env['retained_profile_symbols'],[])
                self.assertEqual(env['harness_sha256'],factory.digest(harness))
                self.assertNotIn('sim_profile.c',env['dependencies']);self.assertNotIn('q0_model.py',env['dependencies'])
                env['settings'].update(queue=256,prefill=192)
                flags=factory.command_flags(env,factory.CANDIDATES['unroll1-tune0-lto-call-relax'])
                self.assertIn('-DLPX4_PROFILE_QUEUE=256',flags);self.assertIn('-DLPX4_PROFILE_PREFILL=192',flags)
                self.assertFalse(any(flag.startswith('-Wl,-u,profile_') for flag in flags))
                legacy=factory.environment(factory.ROOT/'src',avr,legacy_only=True)
                self.assertFalse(legacy['settings']['speech']);self.assertIn('__bss_end',legacy['required_symbols'])
                self.assertTrue(legacy['retained_profile_symbols'])

    def test_streaming_coverage_is_strict_and_historical_is_explicit(self):
        for samples in (1,64000,64001,281632):
            new={'decode_calls':samples,'decode_statistics':'streaming-v2','statistics_overflow':0}
            self.assertTrue(factory.timing_coverage(new,samples)['decode_timing_complete'])
            old={'decode_calls':min(samples,64000)}
            with self.assertRaises(ValueError):factory.timing_coverage(old,samples)
            coverage=factory.timing_coverage(old,samples,historical=True)
            self.assertTrue(coverage['historical_runner']);self.assertEqual(coverage['decode_timing_complete'],samples<=64000)
            for damage in ({'decode_calls':samples-1},{'statistics_overflow':1},{'statistics_overflow':False}):
                with self.assertRaises(AssertionError):factory.timing_coverage(dict(new,**damage),samples)
        with self.assertRaises(ValueError):factory.timing_coverage({'decode_calls':320,'decode_statistics':'unknown'},320,historical=True)

    def test_timing_cache_revalidates_host_changes_without_changing_image_cost(self):
        blob=repack(fixture(4,320))[0];expected=pwm_duties(decode_model(blob)).tobytes();src=factory.ROOT/'src'
        cost={'samples':320,'image_sha256':'e'*64,'environment':{'source_sha256':factory.source_hashes(src)}}
        def run(command,**kwargs):
            Path(command[-2]).write_bytes(expected)
            Path(command[-1]).write_text(json.dumps({'done':1,'decoder_error':0,'underruns':0,
                'played':320,'produced':320,'timer_ticks':320,'decode_calls':320,'stack_margin_bytes':500,
                'cpu_hz':16000000,'audio_hz':8000,'decode_statistics':'streaming-v2','statistics_overflow':0}))
        with tempfile.TemporaryDirectory(dir=collector.REPOSITORY/'build') as td:
            folder=Path(td)
            with patch.object(collector,'measure',return_value=cost) as measure, \
                 patch.object(collector,'validation_provenance',return_value={'validator':'first'}) as provenance, \
                 patch.object(collector.subprocess,'run',side_effect=run) as runner:
                first=collector.simulate([blob],folder,'unused',folder/'runner')
                self.assertEqual(runner.call_count,1);self.assertEqual(first['done'],1)
                second=collector.simulate([blob],folder,'unused',folder/'runner')
                self.assertEqual(first,second);self.assertEqual(runner.call_count,1)
                provenance.return_value={'validator':'new binary/model/runtime'}
                third=collector.simulate([blob],folder,'unused',folder/'runner')
                self.assertEqual(runner.call_count,2);self.assertEqual(third['cost'],cost)
                (folder/'valid.pcm8').write_bytes(b'corrupt')
                collector.simulate([blob],folder,'unused',folder/'runner');self.assertEqual(runner.call_count,3)
                (folder/'timing.json').write_text('{}')
                collector.simulate([blob],folder,'unused',folder/'runner');self.assertEqual(runner.call_count,4)
                saved=json.loads((folder/'verification.json').read_text());saved['played']=0
                (folder/'verification.json').write_text(json.dumps(saved))
                collector.simulate([blob],folder,'unused',folder/'runner');self.assertEqual(runner.call_count,5)
                self.assertTrue(all(call.args[0]==[blob] for call in measure.call_args_list))


if __name__=='__main__':unittest.main()

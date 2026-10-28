"""Collector boundary/cache checks; actual AVR/IRQ validation is separate."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import measure_speech_firmware as collector
from speech_compact import repack
from test_speech_v4 import fixture


class FirmwareCollectorTests(unittest.TestCase):
    def test_invalid_api_inputs_fail_before_tool_invocation(self):
        stream = repack(fixture(4,320))[0]
        with patch.object(collector,'environment') as environment:
            for streams, kwargs in (([],{}),([stream]*256,{}),([123],{}),
                                    ([stream],{'assembly':1}),([stream],{'irq':True}),
                                    ([stream],{'irq':-1}),([stream],{'irq':601}),
                                    ([stream],{'irq':1.5}),([stream[:-1]],{})):
                with self.subTest(kwargs=kwargs,count=len(streams)):
                    with self.assertRaises(ValueError):
                        collector.measure(streams,collector.REPOSITORY/'build/test-invalid','unused',**kwargs)
            environment.assert_not_called()

    def test_output_escape_and_chain_harness_fail_closed(self):
        base = collector.REPOSITORY/'build'
        self.assertEqual(collector.checked_output(base/'nested'),(base/'nested').resolve())
        for path in (collector.REPOSITORY,base/'..'/'outside',collector.REPOSITORY.parent/'build'):
            with self.assertRaises(ValueError): collector.checked_output(path)
        # Reset cost is timed together with next(), and output IRQ stays active.
        chain = collector.chain_harness([321,641])
        active = chain.index('profile_decode_active = 1;')
        reset = chain.index('if(decoder.finished() && segment+1<2)')
        next_sample = chain.index('const bool ok = decoder.next(value);')
        inactive = chain.index('profile_decode_active = 0;',next_sample)
        self.assertLess(active,reset); self.assertLess(reset,next_sample); self.assertLess(next_sample,inactive)
        self.assertIn('const uint32_t total = 962UL;',chain)
        for operation in ('ISR(TIMER1_COMPA_vect)','sei();','pgm_read_ptr(&profile_voices[segment])',
                          'pgm_read_word(&profile_sizes[segment])','if (!decoder.finished()) profile_error = 1;'):
            self.assertIn(operation,chain)
        with patch.object(Path,'read_text',return_value='incompatible harness'):
            with self.assertRaises(ValueError): collector.chain_harness([320])

    def test_complete_link_cost_and_cache_bind_exact_inputs_and_artifacts(self):
        streams = [repack(fixture(4,320))[0]]
        source = Path(collector.__file__).resolve().parents[1]/'src'
        env = {'source_sha256':collector.source_hashes(source)}
        compiles = []
        def run(command,**kwargs):
            if str(command[0]).endswith(('avr-g++.exe','avr-g++')):
                compiles.append(command)
                Path(command[-1]).write_bytes(b'linked '+b''.join(streams))
            else:
                Path(command[-1]).write_bytes(b'load '+b''.join(streams))
            class Result:
                stdout=b''; stderr=b''; returncode=0
            return Result()
        proof = {'ranges':[[0,1]],'hardware_address_constants':{}}
        with tempfile.TemporaryDirectory(dir=collector.REPOSITORY/'build') as td:
            folder = Path(td)
            with patch.object(collector,'environment',return_value=env), \
                 patch.object(collector,'command_flags',return_value=['-mmcu=atmega328p']), \
                 patch.object(collector.subprocess,'run',side_effect=run), \
                 patch.object(collector.subprocess,'check_output',return_value='text data bss dec hex filename\n500 20 30 550 226 profile.elf\n'), \
                 patch.object(collector,'embedded_streams',return_value=proof):
                cost = collector.measure(streams,folder,'unused')
                self.assertEqual(cost['flash_bytes'],520)
                self.assertEqual(cost['program_flash_bytes'],520-len(streams[0]))
                self.assertEqual(cost['static_sram_bytes'],50)
                self.assertFalse(cost['timing_verified'])
                self.assertEqual(collector.measure(streams,folder,'unused'),cost)
                self.assertEqual(len(compiles),1)
                # Mutated linked binaries cannot reuse a matching metadata record.
                (folder/'program.bin').write_bytes(b'changed')
                collector.measure(streams,folder,'unused'); self.assertEqual(len(compiles),2)
                metadata = json.loads((folder/'cost.json').read_text())
                metadata['cost']['flash_bytes'] += 1
                (folder/'cost.json').write_text(json.dumps(metadata))
                collector.measure(streams,folder,'unused'); self.assertEqual(len(compiles),3)
                # Same geometry/toolchain but different stream content is comparable,
                # while cached images and stream hashes remain distinct.
                streams[:] = [repack(fixture(6,320))[0]]
                alternative = collector.measure(streams,folder,'unused')
                self.assertEqual(len(compiles),4)
                self.assertEqual(alternative['build_fingerprint'],cost['build_fingerprint'])
                self.assertNotEqual(alternative['stream_sha256'],cost['stream_sha256'])
                streams[:] = [repack(fixture(6,321))[0]]
                changed_geometry = collector.measure(streams,folder,'unused')
                self.assertNotEqual(changed_geometry['build_fingerprint'],cost['build_fingerprint'])
                # Source changes during linking fail instead of recording stale cost.
                with patch.object(collector,'source_hashes',return_value={'changed':'0'*64}):
                    with self.assertRaises(ValueError):
                        collector.measure(streams,folder/'changed-source','unused')

    def test_api_guards_source_runner_and_output_aliases_before_tools(self):
        stream = repack(fixture(4,320))[0]
        with tempfile.TemporaryDirectory(dir=collector.REPOSITORY/'build') as td:
            folder = Path(td)
            with patch.object(collector,'environment') as environment:
                source = folder/'source'; source.mkdir()
                (source/'Lpx4HybridCore.cpp').write_text('// source placeholder')
                conflict = source/'chain.cpp'; conflict.write_bytes(b'preserve source')
                with self.assertRaises(ValueError): collector.measure([stream],source,'unused',source=source)
                self.assertEqual(conflict.read_bytes(),b'preserve source')
                target = folder/'profile.elf'; target.write_bytes(b'preserve runner')
                with self.assertRaises(ValueError): collector.simulate([stream],folder,'unused',target)
                self.assertEqual(target.read_bytes(),b'preserve runner')
                target.unlink()
                input_file = folder/'original.l4hy'; input_file.write_bytes(stream)
                os.link(input_file,target)
                self.assertGreater(target.stat().st_nlink,1)
                with self.assertRaises(ValueError): collector.measure([stream],folder,'unused')
                self.assertEqual(input_file.read_bytes(),stream)
                target.unlink()
                # The CLI also supplies stream path identities, including an exact
                # stream/output collision without a link.
                target.write_bytes(stream)
                with patch('sys.argv',['measure_speech_firmware.py',str(folder),str(target),'--avr-bin','unused']):
                    with self.assertRaises(ValueError): collector.main()
                self.assertEqual(target.read_bytes(),stream)
                target.unlink()
                # Windows may require a user privilege for real symlink creation.
                try:
                    target.symlink_to(input_file)
                except OSError:
                    pass
                else:
                    with self.assertRaises(ValueError): collector.measure([stream],folder,'unused')
                    self.assertEqual(input_file.read_bytes(),stream)
                    target.unlink()
                environment.assert_not_called()

    def test_exact_embedded_arrays_and_duplicate_storage_proof(self):
        names = ['profile_pwm_address','profile_spl_address','profile_sph_address']
        env = {'required_symbols':names,'retained_profile_symbols':names}
        metadata = '\n'.join(f'{0x800100+2*i:08x} 00000002 D {name}' for i,name in enumerate(names))
        sections = '  1 .data 00000006 00800100 00000040 00000000 2**0\n'
        with tempfile.TemporaryDirectory(dir=collector.REPOSITORY/'build') as td:
            folder = Path(td); binary = folder/'program.bin'; elf=folder/'profile.elf'
            data = bytearray(70); data[32:35]=b'one'; data[40:43]=b'one'; data[64:70]=b'\x01\0\x02\0\x03\0'
            binary.write_bytes(data)
            symbols = '00000020 00000003 t profile_voice_0\n00000028 00000003 t profile_voice_1\n'+metadata
            with patch.object(collector.subprocess,'check_output',side_effect=[symbols,sections]):
                proof = collector.embedded_streams(elf,binary,'unused',[b'one',b'one'],env)
            self.assertEqual(proof['ranges'],[[32,35],[40,43]])
            self.assertEqual(proof['hardware_address_constants'],dict(zip(names,(1,2,3))))
            for invalid in (symbols.replace('00000028','00000020'),
                            symbols.replace('profile_voice_1','unrelated'),
                            symbols.replace(names[-1],'missing')):
                with patch.object(collector.subprocess,'check_output',side_effect=[invalid,sections]):
                    with self.assertRaises(ValueError):
                        collector.embedded_streams(elf,binary,'unused',[b'one',b'one'],env)
            data[40]=0;binary.write_bytes(data)
            with patch.object(collector.subprocess,'check_output',side_effect=[symbols,sections]):
                with self.assertRaises(ValueError):
                    collector.embedded_streams(elf,binary,'unused',[b'one',b'one'],env)


if __name__=='__main__': unittest.main()

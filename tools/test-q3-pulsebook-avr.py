"""EEPROM pulse templates: source compatibility, exact AVR bytes and budgets."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
from hq4_core import pack_stream,unpack_stream
from hq4_q3 import render as floor_render
from hq4_q3_rounded import render as rounded_render
from q3_pulsebook import legacy_tables

spec = importlib.util.spec_from_file_location('pulsebook_avr_test_builder',ROOT/'tools/build-q3-pulsebook.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def toolchains(test):
    suffix = '.exe' if os.name == 'nt' else ''
    avr = Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
    node = Path(os.environ.get('NODE',ROOT.parents[1]/('build/toolchains/node-22.22.3/node'+suffix)))
    if not (avr/('avr-gcc'+suffix)).exists() or not node.exists():
        test.skipTest('Set AVR_BIN and NODE for the repository toolchains')
    return avr,node


class PulsebookAvrTests(unittest.TestCase):
    def test_table_inputs_preserve_signed_values_and_reject_invalid_memory_layouts(self):
        build = ROOT/'build'
        build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='test-q3-pulse-',dir=build) as temporary:
            self.assertTrue(Path(temporary).resolve().is_relative_to(build.resolve()))
            folder = Path(temporary)
            table = np.arange(64,dtype=np.int8).reshape(4,16)%15-7
            for name,value in (('array.json',table.tolist()),('model.json',dict(pulsebook=table.tolist()))):
                source = folder/name
                source.write_text(json.dumps(value))
                np.testing.assert_array_equal(builder.load_table(source),table)
            source = folder/'table.bin'
            source.write_bytes(table.tobytes())
            np.testing.assert_array_equal(builder.load_table(source),table)
            for value in (b'\0'*63,b'\0'*65,b'\x80'*64):
                source.write_bytes(value)
                with self.assertRaises(ValueError):
                    builder.load_table(source)
            source = folder/'bad.json'
            for value in ([[0]*15]*4,[[8]*16]*4,[[.5]*16]*4,[[True]*16]*4):
                source.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    builder.load_table(source)

    def test_full_legacy_vinni_templates_match_frozen_floor_and_rounded_pcm_in_three_engines(self):
        avr,node = toolchains(self)
        stream = ROOT/'ATtiny13A/Sound/research/hq4-q3/public-vinni/speech.hq'
        frames,durations = unpack_stream(stream.read_bytes())
        output = ROOT/'build/q3-pulsebook-validation'
        output.mkdir(parents=True,exist_ok=True)
        table = output/'legacy.bin'
        table.write_bytes(legacy_tables().tobytes())
        for rounded,oracle in ((False,floor_render),(True,rounded_render)):
            with self.subTest(rounded=rounded):
                destination = output/('legacy-rounded' if rounded else 'legacy-floor')
                report = builder.build(stream,table,destination,avr,node,rounded=rounded,expected_samples=22272)
                self.assertEqual(report['status'],'verified',json.dumps(report.get('verification')))
                expected,counts = oracle(frames,durations,1)
                self.assertEqual(report['phrasePcmSha256'],builder.sha(expected.tobytes()))
                np.testing.assert_array_equal(report['intermediateWraps'],counts)
                self.assertEqual(report['codeBytes'],410 if rounded else 408)
                self.assertEqual(report['flashBytes'],1014 if rounded else 1012)
                self.assertEqual(report['verification']['verifiedSamples'],66816)
                self.assertEqual(report['verification']['mismatches'],0)
                self.assertEqual(report['verification']['lostOverflows'],0)
                self.assertEqual(report['verification']['missedSamples'],0)
                self.assertEqual(report['eepromUsedBytes'],64)
                self.assertEqual(report['verification']['eepromSha256'],report['eepromSha256'])
                self.assertGreater(report['verification']['foregroundTiming']['minimumSlackCycles'],0)

    def test_extreme_signed_template_entries_all_modes_and_noise_execute_exactly(self):
        avr,node = toolchains(self)
        output = ROOT/'build/q3-pulsebook-validation/extreme'
        output.mkdir(parents=True,exist_ok=True)
        table = np.array([[-7,7]*8,[7,-7]*8,[-7]*16,[7]*16],np.int8)
        table[3,15] = -7  # Exercise the maximum EEPROM address63 explicitly.
        table_path = output/'table.bin'
        table_path.write_bytes(table.tobytes())
        frames = np.array([[17,15,0x99,0x88,0x88,0x88],
                           [31,0x1f,0x77,0x88,0x88,0x88],
                           [90,0x2f,0x99,0x88,0x88,0x88],
                           [17,0x3f,0x77,0x88,0x88,0x88],
                           [0,3,0x88,0x88,0x88,0x88]],np.uint8)
        durations = np.array([64,128,192,256,64],np.uint16)
        source = output/'speech.hq'
        source.write_bytes(pack_stream(frames,durations))
        for rounded in (False,True):
            with self.subTest(rounded=rounded):
                report = builder.build(source,table_path,output/str(rounded),avr,node,
                                       rounded=rounded,expected_samples=704)
                self.assertEqual(report['status'],'verified',json.dumps(report.get('verification')))
                self.assertEqual(report['verification']['verifiedSamples'],2112)
                self.assertEqual(report['verification']['engines'],['reference','wasm','wasm-unoptimized'])
                self.assertEqual(report['verification']['missedSamples'],0)
                self.assertEqual(report['verification']['lostOverflows'],0)

    def test_exact_maximum_streams_fill_1024_flash_and_extra_bytes_are_rejected(self):
        avr,node = toolchains(self)
        output = ROOT/'build/q3-pulsebook-validation/maximum'
        output.mkdir(parents=True,exist_ok=True)
        table = output/'table.bin'
        table.write_bytes(legacy_tables().tobytes())
        for rounded in (False,True):
            frames = [[40,1 | ((i%4)<<4),*([0x79 if i%2 else 0x97]*4)] for i in range(102)]
            frames[-1][0] = 90
            durations = [64]*101+[192]
            if not rounded:
                repeat = frames[-1].copy()
                repeat[0] = 40
                frames.append(repeat)
                durations.append(64)
            source = output/('rounded.hq' if rounded else 'floor.hq')
            payload = pack_stream(np.array(frames,np.uint8),np.array(durations,np.uint16))
            self.assertEqual(len(payload),613 if rounded else 615)
            source.write_bytes(payload)
            report = builder.build(source,table,output/str(rounded),avr,node,rounded=rounded)
            self.assertEqual(report['status'],'verified',json.dumps(report.get('verification')))
            self.assertEqual(report['flashBytes'],1024)
            self.assertEqual(report['eepromUsedBytes'],64)
            source.write_bytes(payload+b'\0')
            with self.assertRaisesRegex(ValueError,'stream bytes'):
                builder.load_stream(source,legacy_tables(),rounded=rounded)


if __name__ == '__main__':
    unittest.main()

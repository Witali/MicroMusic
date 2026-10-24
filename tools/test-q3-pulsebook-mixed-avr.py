"""Actual mixed-source EEPROM cache, LFSR timing, legacy PCM and complete budgets."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_core import pack_stream,unpack_stream
from hq4_q3 import render as floor_render
from hq4_q3_rounded import render as rounded_render
from q3_pulsebook_mixed import encode_book,legacy_tables

spec = importlib.util.spec_from_file_location('mixed_pulsebook_avr_builder',ROOT/'tools/build-q3-pulsebook-mixed.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class MixedPulsebookAvrTests(unittest.TestCase):
    def tools(self):
        suffix = '.exe' if os.name == 'nt' else ''
        avr = Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node = Path(os.environ.get('NODE',ROOT.parents[1]/('build/toolchains/node-22.22.3/node'+suffix)))
        if not (avr/('avr-gcc'+suffix)).exists() or not node.exists():
            self.skipTest('Set AVR_BIN and NODE for the repository toolchains')
        return avr,node

    def execute(self,name,frames,durations,table,rounded):
        avr,node = self.tools()
        output = ROOT/'build/q3-pulsebook-mixed-validation'/name
        output.mkdir(parents=True,exist_ok=True)
        stream,table_path = output/'source.hq',output/'table.bin'
        stream.write_bytes(pack_stream(frames,durations))
        table_path.write_bytes(table.tobytes())
        report = builder.build(stream,table_path,output/'avr',avr,node,rounded=rounded,
                               expected_samples=int(durations.sum()))
        self.assertEqual(report['status'],'verified',json.dumps(report.get('verification')))
        self.assertEqual(report['codeBytes'],420 if rounded else 418)
        self.assertEqual(report['eepromUsedBytes'],64)
        self.assertEqual(report['verification']['verifiedSamples'],int(durations.sum())*3)
        self.assertEqual(report['verification']['engines'],['reference','wasm','wasm-unoptimized'])
        self.assertEqual(report['verification']['mismatches'],0)
        self.assertEqual(report['verification']['lostOverflows'],0)
        self.assertEqual(report['verification']['missedSamples'],0)
        self.assertEqual(report['verification']['eepromSha256'],builder.sha(table.tobytes()))
        self.assertGreater(report['verification']['foregroundTiming']['minimumSlackCycles'],0)
        return report,output/'avr'

    def test_zero_flags_reproduce_frozen_full_vinni_pcm_in_both_profiles(self):
        payload = (ROOT/'ATtiny13A/Sound/research/hq4-q3/public-vinni/speech.hq').read_bytes()
        frames,durations = unpack_stream(payload)
        for rounded,oracle in ((False,floor_render),(True,rounded_render)):
            report,folder = self.execute('legacy-'+str(rounded),frames,durations,legacy_tables(),rounded)
            expected,counts = oracle(frames,durations,1)
            self.assertEqual(report['phrasePcmSha256'],builder.sha(expected.tobytes()))
            self.assertEqual((folder/'actual.raw').read_bytes()[:len(expected)],expected.tobytes())
            np.testing.assert_array_equal(report['intermediateWraps'],counts)
            self.assertEqual(report['flashBytes'],1024 if rounded else 1022)
            self.assertEqual(report['verification']['verifiedSamples'],66816)

    def test_flags_one_clock_lfsr_through_gain_zero_one_and_then_unvoiced_exactly_once(self):
        frames = np.array([[64,0,0x88,0x88,0x88,0x88],[64,1,0x88,0x88,0x88,0x88],
                           [64,6,0x88,0x88,0x88,0x88],[0,6,0x88,0x88,0x88,0x88]],np.uint8)
        durations = np.full(4,64,np.uint16)
        table = encode_book(np.zeros((4,16),np.int8),[1,0,0,0])
        seed,previous,expected = 0xa7,0,[]
        for sample in range(256):
            index = 0 if sample < 63 or sample == 255 else (sample+1)//64
            gain = (0,1,6,6)[index]
            low = seed & 1
            seed >>= 1
            if low:
                seed ^= 0xb8
            amplitude = gain if index == 3 else gain >> 1
            excitation = -amplitude if seed & 1 else amplitude
            value = excitation+previous-(previous >> 1)
            previous = ((value+128)&255)-128
            expected.append(previous+128)
        expected = bytes(expected)
        for rounded in (False,True):
            report,folder = self.execute('clock-'+str(rounded),frames,durations,table,rounded)
            self.assertEqual(report['phrasePcmSha256'],builder.sha(expected))
            self.assertEqual((folder/'actual.raw').read_bytes()[:256],expected)

    def test_mode_specific_cache_long_zero_pulse_tail_signed_extremes_and_eeprom63(self):
        coefficients = np.array([[-7,7]*8,[7,-7]*8,[-7]*16,[7]*16],np.int8)
        coefficients[3,15] = -7
        table = encode_book(coefficients,[1,0,1,1])
        frames = np.array([[17,15,0x99,0x88,0x88,0x88],[31,0x1f,0x77,0x88,0x88,0x88],
                           [90,0x2f,0x99,0x88,0x88,0x88],[17,0x3f,0x77,0x88,0x88,0x88],
                           [0,3,0x88,0x88,0x88,0x88]],np.uint8)
        durations = np.array([64,128,192,256,64],np.uint16)
        for rounded in (False,True):
            self.execute('extreme-'+str(rounded),frames,durations,table,rounded)

    def test_maximum605_and603_byte_streams_fill_1024_flash_and_larger_inputs_reject(self):
        table = encode_book(np.zeros((4,16),np.int8),[1,0,1,0])
        for rounded in (False,True):
            count = 99 if rounded else 100
            frames = [[40,1 | ((i%4)<<4),*([0x79 if i%2 else 0x97]*4)] for i in range(count)]
            durations = [64]*count
            if rounded:
                frames += [[90,1,0x88,0x88,0x88,0x88],[40,1,0x88,0x88,0x88,0x88]]
                durations += [192,64]
            else:
                frames += [[90,1,0x88,0x88,*frames[-1][4:]]]
                durations += [192]
            frames,durations = np.array(frames,np.uint8),np.array(durations,np.uint16)
            payload = pack_stream(frames,durations)
            self.assertEqual(len(payload),603 if rounded else 605)
            report,folder = self.execute('maximum-'+str(rounded),frames,durations,table,rounded)
            self.assertEqual(report['flashBytes'],1024)
            self.assertEqual(report['maximumStreamBytes'],len(payload))
            source = folder.parent/'excessive.hq'
            source.write_bytes(payload+b'\0')
            with self.assertRaisesRegex(ValueError,'stream bytes'):
                builder.load_stream(source,table,rounded=rounded)

    def test_encoded_memory_bounds_row_flag_consistency_and_old_schema_reject(self):
        output = ROOT/'build/q3-pulsebook-mixed-validation/invalid'
        output.mkdir(parents=True,exist_ok=True)
        source = output/'table.bin'
        for payload in (b'\x08'*63,b'\x08'*65,b'\x00'*64,b'\x10'*64,b'\x20'*64,b'\x80'*64):
            source.write_bytes(payload)
            with self.assertRaises(ValueError):
                builder.load_table(source)
        inconsistent = legacy_tables().copy()
        inconsistent[0,0] |= 16
        source.write_bytes(inconsistent.tobytes())
        with self.assertRaisesRegex(ValueError,'uniform noise flag'):
            builder.load_table(source)
        source = output/'old-model.json'
        source.write_text(json.dumps(dict(schema='hq4-q3-pulsebook-v1',pulsebook=legacy_tables().tolist())))
        with self.assertRaisesRegex(ValueError,'explicitly tagged'):
            builder.load_table(source)


if __name__ == '__main__':
    unittest.main()

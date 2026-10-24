"""Programming image checks and exact speech loop/DC expectations."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
spec = importlib.util.spec_from_file_location('tiny_builder', ROOT/'tools/build-tiny-speech.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
from dc_blocker import block_dc
from fixed_period import decode_fixed


def parse_hex(source):
    """Independent record/checksum reader, sufficient for 1 KiB images."""
    result = bytearray()
    eof = False
    for line in source.splitlines():
        record = bytes.fromhex(line[1:])
        if line[0]!=':' or sum(record) & 255 or len(record)!=record[0]+5:
            raise ValueError('Invalid HEX record')
        length, high, low, kind = record[:4]
        if kind == 1:
            if record != bytes((0,0,0,1,255)):
                raise ValueError('Invalid EOF record')
            eof = True
        elif kind == 0 and not eof:
            address = high*256+low
            if address != len(result):
                raise ValueError('Noncontiguous HEX records')
            result.extend(record[4:4+length])
        else:
            raise ValueError('Unexpected HEX record')
    if not eof:
        raise ValueError('Missing HEX EOF')
    return bytes(result)


def model():
    return dict(schema='period-fixed-v1', sample_rate=7500, hop=64, samples=128,
                phase_bits=4, initial_phase_u16=56231, noise_seed_u16=0xace1,
                codebook=[[3]*32]+[[0]*32 for _ in range(15)],
                noise_filters=[[0]*8 for _ in range(3)], frames=[[100,0xf0,0]]*2,
                dc_block_shift=5)


class BuildTest(unittest.TestCase):
    def test_flash_and_eeprom_programming_hex_roundtrip(self):
        for length in (1,15,16,17,63,64,1023,1024):
            data = bytes((i*37+19) & 255 for i in range(length))
            self.assertEqual(parse_hex(builder.intel_hex(data)), data)
        self.assertEqual(parse_hex(builder.intel_hex(bytes([255])*64)),bytes([255])*64)

    def test_expected_three_loops_keep_dc_history(self):
        source = model()
        before = deepcopy(source)
        raw = deepcopy(source)
        raw.pop('dc_block_shift')
        expected = block_dc(np.tile(decode_fixed(raw),3),5)[0]
        np.testing.assert_array_equal(builder.expected_loops(source),expected)
        self.assertFalse(np.array_equal(expected,np.tile(decode_fixed(source),3)))
        self.assertEqual(source,before)

    def test_expected_without_dc_restarts_phrase(self):
        source = model()
        source.pop('dc_block_shift')
        np.testing.assert_array_equal(builder.expected_loops(source),np.tile(decode_fixed(source),3))

    def test_one_shot_keeps_the_full_phrase_then_centers_the_output(self):
        source = model()
        expected = builder.expected_loops(source,play_once=True)
        np.testing.assert_array_equal(expected[:source['samples']],decode_fixed(source))
        self.assertEqual(len(expected),source['samples']*3)
        self.assertTrue(np.all(expected[source['samples']:]==128))
        self.assertFalse(np.array_equal(expected[source['samples']:2*source['samples']],decode_fixed(source)))

    def test_symbol_parser_keeps_absolute_constants_and_code_labels(self):
        parsed = builder.parse_symbols('00000078 A STACK_FLOOR\n00000200 T wave_data\n         U undefined\n')
        self.assertEqual(parsed,{'STACK_FLOOR':0x78,'wave_data':0x200})


if __name__ == '__main__':
    unittest.main()

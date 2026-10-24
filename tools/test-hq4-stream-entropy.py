"""Independent decoding, exact grammar separation and complete byte counts."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hq4_entropy_tested', ROOT/'tools/probe-hq4-stream-entropy.py')
codec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codec)


class StreamEntropyTests(unittest.TestCase):
    def test_every_method_roundtrips_all_byte_values_and_counts_every_byte(self):
        source = bytes(range(256))*2
        for method in codec.MODES:
            with self.subTest(method=method):
                blob, info = codec.encode(source, method)
                self.assertEqual(codec.decode(blob), source)
                self.assertEqual(len(blob), info['header_bytes']+info['codebook_bytes']+info['payload_bytes'])
                self.assertEqual(info['payload_bytes'], (info['payload_bits']+7)//8)

    def test_empty_single_symbol_and_skewed_nibbles_do_not_swap_low_and_high(self):
        for source in (b'', b'\x88'*31, b'\x98'*127+bytes(range(64))):
            for method in codec.MODES:
                with self.subTest(size=len(source), method=method):
                    blob, _ = codec.encode(source, method)
                    self.assertEqual(codec.decode(blob), source)

    def test_compact_tree_is_at_most31_bytes_and_decodes_without_canonical_table(self):
        source = bytes(range(256))
        blob, info = codec.encode(source, 'nibble-tree')
        self.assertEqual(info['codebook_bytes'], 1+31)
        self.assertEqual(codec.decode(blob), source)
        # A single-symbol tree needs no bits, just one leaf and decoded count.
        blob, info = codec.encode(b'\x88'*10, 'nibble-tree')
        self.assertEqual(info['payload_bits'], 0)
        self.assertEqual(codec.decode(blob), b'\x88'*10)

    def test_invalid_canonical_lengths_trailing_data_and_truncation_fail(self):
        with self.assertRaises(ValueError):
            codec.canonical({0: 1, 1: 1, 2: 1})
        for method in codec.MODES:
            blob, _ = codec.encode(bytes(range(64)), method)
            with self.subTest(method=method):
                with self.assertRaises(ValueError): codec.decode(blob+b'\0')
                with self.assertRaises(ValueError): codec.decode(blob[:-1])

    def test_split_headers_and_coefficients_rejoin_exact_full_half_and_reuse_updates(self):
        # Normal full update, extended pitch/reuse, first-half then second-half.
        source = bytes([0x40|35, 0x03, 0x88,0x99,0x76,0xba,
                        0xc2,70,0x40|2,
                        0x80|34,0x80|4,0x98,0x87,
                        0x40|34,0xc0|5,0xa9,0x67])
        headers, coefficients, frames = codec.split_stream(source)
        self.assertEqual(len(frames), 4)
        self.assertEqual(len(coefficients), 8)
        self.assertEqual(codec.join_stream(headers, coefficients), source)
        for method in codec.MODES:
            blob, info = codec.encode_split(source, method)
            self.assertEqual(codec.decode_split(blob), source)
            self.assertEqual(len(blob), 8+len(headers)+info['header_bytes']+info['codebook_bytes']+info['payload_bytes'])
        with self.assertRaises(ValueError): codec.split_stream(source[:-1])
        with self.assertRaises(ValueError): codec.split_stream(source+b'\xff')
        with self.assertRaises(ValueError): codec.join_stream(headers, coefficients+b'\0')


if __name__ == '__main__':
    unittest.main()

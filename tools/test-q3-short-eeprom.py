"""Exact layouts, tails and storage accounting for short Q3 excitation."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'ATtiny13A/Sound/codec'))
from q3_short_eeprom import (WIDTHS, PACKINGS, encode_book, decode_book,
                             minimum_width, split_storage, candidates)


class ShortEepromTests(unittest.TestCase):
    def test_every_tap_and_supported_width_round_trips_without_quantization(self):
        for width in WIDTHS:
            for offset in range(15):
                table = np.zeros((4, 16), np.int8)
                table[:, :width] = ((np.arange(4*width).reshape(4, width)+offset)%15)-7
                for packing in PACKINGS:
                    encoded = encode_book(table, width, packing)
                    self.assertEqual(len(encoded), (4 if packing == 'raw' else 2)*width)
                    np.testing.assert_array_equal(decode_book(encoded, width, packing), table)

    def test_width_selection_rejects_lossy_tail_trimming(self):
        table = np.zeros((4, 16), np.int8)
        self.assertEqual(minimum_width(table), 4)
        for lag, expected in ((3, 4), (4, 8), (7, 8), (8, 16), (15, 16)):
            table[:] = 0
            table[3, lag] = -7
            self.assertEqual(minimum_width(table), expected)
            for width in WIDTHS:
                if width < expected:
                    with self.assertRaisesRegex(ValueError, 'nonzero pulse tails'):
                        encode_book(table, width, 'nibble')

    def test_prefix_is_exact_at_every_split_including_short_streams(self):
        table = np.zeros((4, 16), np.int8)
        for length in (1, 6, 47, 48, 56, 64, 620):
            payload = bytes(i%256 for i in range(length))
            for packing in PACKINGS:
                capacity = min(length, 48 if packing == 'raw' else 56)
                for prefix in range(capacity+1):
                    layout = split_storage(table, payload, 4, packing, prefix)
                    self.assertEqual(len(layout['eeprom']), 64)
                    actual = layout['eeprom'][layout['prefix_start']:layout['prefix_end']]+layout['flash_suffix']
                    self.assertEqual(actual, payload)
                    self.assertEqual(layout['free_eeprom_bytes'], 64-layout['book_bytes']-prefix)
                    self.assertEqual(layout['flash_suffix'], payload[prefix:])

    def test_invalid_physical_codes_and_sizes_cannot_silently_decode(self):
        for data, packing in ((b'\x88'*8, 'nibble'), (b'\x01'*16, 'raw'),
                              (b'\x80'*16, 'raw'), (b'\xff', 'raw')):
            with self.assertRaises(ValueError):
                decode_book(data, 4, packing)
        with self.assertRaises(ValueError):
            split_storage(np.zeros((4, 16), np.int8), b'', 4, 'raw')
        for prefix in (-1, 49, True, 0.5):
            with self.assertRaises(ValueError):
                split_storage(np.zeros((4, 16), np.int8), b'a'*100, 4, 'raw', prefix)

    def test_total_accounting_can_prefer_bytes_over_nibbles(self):
        layouts = list(candidates(np.zeros((4, 16), np.int8), b'a'*620))
        best = min(layouts, key=lambda value:value['flash_bytes'])
        self.assertEqual((best['width'], best['packing'], best['prefix_bytes']), (4, 'raw', 48))
        self.assertEqual((best['code_bytes'], best['flash_bytes']), (398, 972))
        self.assertEqual(best['maximum_stream_bytes'], 673)
        nibble = next(value for value in layouts if value['width'] == 4
                      and value['packing'] == 'nibble' and value['prefix_bytes'])
        self.assertEqual((nibble['book_bytes'], nibble['prefix_bytes'], nibble['flash_bytes']), (8, 56, 976))


if __name__ == '__main__':
    unittest.main()

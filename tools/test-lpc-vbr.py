"""LPV1 canonical packing, carried decoder state and honest raw error targets."""
from pathlib import Path
import struct
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from lpc_vbr import HEADER, WIDTHS, pack, unpack, encode, decode, encode_output_block


def base_header(samples, sr=7500):
    base = bytearray(36)
    base[:4] = b'LPC2'
    base[4:6] = bytes([2, 10])
    struct.pack_into('<H', base, 6, sr)
    struct.pack_into('<I', base, 16, samples)
    return bytes(base)


class LpcVbrTests(unittest.TestCase):
    def provider(self, samples, pre=.7):
        def result(base):
            self.assertEqual(base, base_header(samples))
            coefficients = np.zeros((samples, 10))
            coefficients[:, 0] = -.25
            coefficients[:, 1] = .05
            return pre, 7500, coefficients
        return result

    def test_mixed_widths_cross_byte_boundaries_and_exact_total_size(self):
        blocks = [(width, 90+index, (np.arange(20) % (1 << width)).astype(np.uint8)) for index, width in enumerate(WIDTHS)]
        blob = pack(base_header(100), 7500, 100, 20, blocks)
        base, actual, info = unpack(blob)
        self.assertEqual(base, base_header(100))
        self.assertEqual(len(blob), HEADER.size+36+(5*11+20*sum(WIDTHS)+7)//8)
        self.assertEqual(info['block_header_bits'], 55)
        for expected, got in zip(blocks, actual):
            self.assertEqual(expected[:2], got[:2])
            np.testing.assert_array_equal(expected[2], got[2])
        self.assertEqual(pack(base, 7500, 100, 20, actual), blob)
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            unpack(blob[:-1])
        with self.assertRaisesRegex(ValueError, 'trailing'):
            unpack(blob+b'\0')

    def test_invalid_width_index_and_nonzero_padding_rejected(self):
        blocks = [(3, 128, np.zeros(21, np.uint8))]
        blob = bytearray(pack(base_header(21), 7500, 21, 21, blocks))
        blob[HEADER.size+36] |= 7
        with self.assertRaisesRegex(ValueError, 'width index'):
            unpack(bytes(blob))
        blob = bytearray(pack(base_header(21), 7500, 21, 21, blocks))
        self.assertNotEqual((11+21*3) % 8, 0)
        blob[-1] |= 128
        with self.assertRaisesRegex(ValueError, 'padding'):
            unpack(bytes(blob))

    def test_parameter_only_decode_matches_independent_scalar_carried_state(self):
        reference = .2*np.sin(np.arange(203)*.17)+.03
        provider = self.provider(len(reference))
        data, expected, info = encode(reference, 7500, base_header(len(reference)), provider,
            target_snr_db=24, block_samples=25)
        base, blocks, parsed = unpack(data)
        pre, _, coefficients = provider(base)
        history, previous, outputs, position = [0.]*10, 0., [], 0
        for width, scale_code, codes in blocks:
            scale = .001*2**((scale_code-128)/16)
            for code in codes:
                prediction = sum(float(coefficients[position, k])*history[k] for k in range(10))
                emphasized = min(2., max(-2., (int(code)-(1 << (width-1)))*scale-prediction))
                history = [emphasized]+history[:9]
                previous = emphasized+pre*previous
                outputs.append(previous)
                position += 1
        np.testing.assert_array_equal(expected, np.asarray(outputs))
        np.testing.assert_array_equal(decode(data, provider)[0], expected)
        self.assertEqual(len(expected), 203)
        self.assertTrue(info['parameter_only_decode_exact'])
        self.assertEqual(info['emphasized_guard_hits'], 0)

    def test_causal_quantizer_uses_actual_output_state_on_every_sample(self):
        reference = np.full(40, .2)
        coefficients = np.zeros((40, 10))
        codes = encode_output_block(reference, coefficients, np.zeros(10), .85, -.5, .001, 8)
        previous = -.5
        errors = []
        for code in codes:
            output = (int(code)-128)*.001+.85*previous
            # Once the first deliberately out-of-range correction recovers,
            # quantization error must not recurse through the .85 de-emphasis.
            errors.append(abs(output-.2))
            previous = output
        self.assertLess(max(errors[-10:]), .00051)

    def test_output_overshoot_survives_without_normalization_or_unit_clipping(self):
        reference = np.full(160, 1.125)
        provider = self.provider(len(reference), pre=0.)
        data, audio, info = encode(reference, 7500, base_header(len(reference)), provider,
            target_snr_db=28, block_samples=40)
        self.assertGreater(float(audio.min()), 1)
        self.assertEqual(info['output_samples_outside_unit_interval'], len(audio))
        self.assertFalse(info['output_clipping'])
        self.assertFalse(info['gain_normalization'])
        np.testing.assert_array_equal(decode(data, provider)[0], audio)

    def test_unattainable_target_reports_failure_and_smallest_feasible_width_selected(self):
        reference = .2*np.sin(np.arange(150)*.173)
        provider = self.provider(len(reference))
        _, _, impossible = encode(reference, 7500, base_header(len(reference)), provider,
            target_snr_db=120, block_samples=25)
        self.assertGreater(impossible['target_failed_blocks'], 0)
        _, _, easy = encode(reference, 7500, base_header(len(reference)), provider,
            target_snr_db=-20, block_samples=25)
        self.assertEqual(easy['width_block_counts'], {'2':6})
        self.assertEqual(easy['target_failed_blocks'], 0)


if __name__ == '__main__':
    unittest.main()

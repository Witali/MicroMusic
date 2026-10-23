"""Nearest-product Q3 arithmetic, unchanged lifecycle, and actual AVR execution."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from hq4_core import pack_stream
from hq4_q3 import render as floor_render
from hq4_q3_rounded import multiply, render


def independent_byte(value):
    return int.from_bytes(bytes([value % 256]), 'little', signed=True)


class Q3RoundedTests(unittest.TestCase):
    def test_all_signed_products_match_independent_integer_nearest_rule(self):
        for value in range(-128, 128):
            for coefficient in range(-8, 8):
                signed_input = independent_byte(-value) if coefficient < 0 else value
                product = signed_input*abs(coefficient)
                quotient, remainder = divmod(product, 8)
                expected = independent_byte(quotient+int(remainder >= 4))
                self.assertEqual(multiply(value, coefficient), expected, (value, coefficient))
        self.assertEqual(multiply(1, 4), 1)
        self.assertEqual(multiply(-1, 4), 0)
        self.assertEqual(multiply(-128, -7), -112)

    def test_zero_coefficients_preserve_every_pulse_noise_and_boundary_sample(self):
        frames = np.array([[37, 3, 0x88, 0x88, 0x88, 0x88],
                           [0, 5, 0x88, 0x88, 0x88, 0x88],
                           [71, 0x23, 0x88, 0x88, 0x88, 0x88],
                           [29, 0x34, 0x88, 0x88, 0x88, 0x88]], np.uint8)
        durations = np.array([64, 128, 192, 256], np.uint16)
        for tilt in (0, 1):
            old, old_counts = floor_render(frames, durations, tilt)
            new, new_counts = render(frames, durations, tilt)
            np.testing.assert_array_equal(old, new)
            np.testing.assert_array_equal(old_counts, new_counts)

    def test_rounding_does_not_disable_intermediate_overflow_audit(self):
        frames = np.array([[18, 15, 0xff, 0xff, 0xff, 0xff]], np.uint8)
        pcm, counts = render(frames, np.array([256], np.uint16), 1)
        self.assertEqual(len(pcm), 256)
        self.assertGreater(int(counts.sum()), 0)

    def test_actual_422_byte_avr_core_matches_three_emulator_engines(self):
        suffix = '.exe' if os.name == 'nt' else ''
        avr = Path(os.environ.get('AVR_BIN', ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node = Path(os.environ.get('NODE', ROOT.parents[1]/('build/toolchains/node-22.22.3/node'+suffix)))
        if not (avr/('avr-gcc'+suffix)).exists() or not node.exists():
            self.skipTest('Set AVR_BIN and NODE for the existing repository toolchains')
        spec = importlib.util.spec_from_file_location('rounded_q3_test_builder', ROOT/'tools/build-hq4-oneshot.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        builder.TEMPLATE = CODEC/'q3-rounded/hq4-t1.S'
        builder.decode = lambda frames, durations, keep_phase=0: render(frames, durations, 1)[0]
        # Cover both signs/extreme coefficients, all pulse shapes, noise, gain
        # changes, compact and extended pitch/duration headers, and EOF silence.
        frames = np.array([[37, 3, 0x19, 0xe7, 0xb5, 0x6a],
                           [0, 4, 0x7f, 0x99, 0x6a, 0xb5],
                           [71, 0x12, 0x5b, 0x6a, 0x97, 0x88],
                           [29, 0x23, 0xc4, 0x4c, 0x88, 0x6a],
                           [126, 0x31, 0x97, 0xa6, 0x88, 0x79],
                           [0, 0, 0x88, 0x88, 0x88, 0x88]], np.uint8)
        durations = np.array([64, 128, 192, 256, 64, 128], np.uint16)
        output = ROOT/'build/q3-rounded-validation'
        output.mkdir(parents=True, exist_ok=True)
        stream = output/'synthetic.hq'
        stream.write_bytes(pack_stream(frames, durations))
        report = builder.build('q3-rounded-synthetic', output/'firmware', avr, node,
                               stream=stream, expected_samples=int(durations.sum()))
        self.assertEqual(report['status'], 'verified', json.dumps(report.get('verification')))
        self.assertEqual(report['codeBytes'], 422)
        self.assertEqual(report['codePaddingBytes'], 0)
        self.assertLessEqual(report['flashBytes'], 1024)
        self.assertEqual(report['phraseSamples'], 832)
        self.assertEqual(report['silenceSamplesVerified'], 1664)
        self.assertEqual(report['eepromBytes'], 0)
        self.assertEqual(report['verifiedLoops'], 1)


if __name__ == '__main__':
    unittest.main()

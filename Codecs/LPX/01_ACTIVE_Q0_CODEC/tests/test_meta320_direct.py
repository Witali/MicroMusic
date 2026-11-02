"""Default-off v9 parser: expansion, complete tails, strict flags and state size."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from batch_decoder import ROOT
from speech_meta320 import pack, unpack, expand, decode_model, POSITIONS
from lpx4 import BitWriter
from speech_compact import put_spectrum
from standard_metrics import pwm_duties
from test_sparse80_direct import native


def fixture(n, seed=9, pre=13926, bright=0):
    rng = np.random.default_rng(seed)
    count = (n+319)//320
    spectra = [sorted(map(int, rng.choice(32, 10, replace=False))) for _ in range(count)]
    params = [(int(rng.integers(32)), int(rng.integers(18, 146)), 2*int(rng.integers(8))) for _ in range(count)]
    pulses = [(POSITIONS[int(rng.integers(16))], (-8, 8)[int(rng.integers(2))]) for _ in range(count*16)]
    return pack(n, spectra, params, pulses, pre, bright)


class Meta320DirectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.directory = Path(cls.temp.name)
        cls.compiler = os.environ.get('LPX_NATIVE_CXX', 'g++')
        cls.pairs = {segments: (native(cls.directory/f'common-{segments}.so', cls.compiler, segments, compact=False),
            native(cls.directory/f'meta-{segments}.so', cls.compiler, segments,
                   defines=['-DLPX4_ENABLE_META320=1']),
            native(cls.directory/f'v5-{segments}.so', cls.compiler, segments)) for segments in (1, 2, 4)}

    @classmethod
    def tearDownClass(cls):
        cls.pairs.clear()
        cls.temp.cleanup()

    def test_full_pcm_pwm_and_strict_opt_in(self):
        for segments, (common, direct, disabled) in self.pairs.items():
            for n in (1, 19, 20, 39, 40, 41, 159, 160, 161, 319, 320, 321, 641, 1280):
                blob = fixture(n)
                expected = common.decode_one_s16(expand(blob), n)
                self.assertIsNotNone(expected)
                np.testing.assert_array_equal(direct.decode_one_s16(blob, n), expected)
                np.testing.assert_array_equal(direct.decode_one(blob, n), pwm_duties(expected))
                self.assertIsNone(disabled.decode_one(blob, n))
                self.assertIsNone(common.decode_one(blob, n))
                if segments == 2:
                    np.testing.assert_array_equal(expected, decode_model(blob))
            ordinary = expand(fixture(641))
            np.testing.assert_array_equal(direct.decode_one_s16(ordinary, 641), disabled.decode_one_s16(ordinary, 641))

    def test_every_final_packet_tail(self):
        for common, direct, _ in self.pairs.values():
            for total in (320, 640):
                blob = fixture(total)
                expected = common.decode_one_s16(expand(blob), total)
                for n in range(total-319, total+1):
                    shortened = bytearray(blob)
                    shortened[8:12] = n.to_bytes(4, 'little')
                    shortened = bytes(shortened)
                    np.testing.assert_array_equal(direct.decode_one_s16(shortened, n), expected[:n])
                    np.testing.assert_array_equal(direct.decode_one(shortened, n), pwm_duties(expected[:n]))

    def test_malformed_complete_packets_and_v5_flags(self):
        for _, direct, _ in self.pairs.values():
            for n in (1, 20, 39, 40, 159, 160, 161, 319, 320, 321):
                blob = fixture(n)
                bad = [blob[:cut] for cut in range(22)]
                for cut in (1, 2, 3, 8):
                    value = bytearray(blob[:-cut]);value[20:22] = (len(value)-22).to_bytes(2, 'little');bad.append(bytes(value))
                value = bytearray(blob+b'\0');value[20:22] = (len(value)-22).to_bytes(2, 'little');bad.append(bytes(value))
                value = bytearray(blob);value[22] &= 254;bad.append(bytes(value))  # first spectrum cannot repeat
                writer, previous = BitWriter(), None
                for vector in unpack(blob)[1]:
                    put_spectrum(writer,list(vector),previous,5);previous=list(vector)
                padding = (-(writer.total+95*len(unpack(blob)[1]))) % 8
                if padding:
                    value = bytearray(blob);value[-1] |= 1 << (8-padding);bad.append(bytes(value))
                for offset in (4, 5, 6, 16, 18):
                    value = bytearray(blob);value[offset] ^= 1;bad.append(bytes(value))
                for value in bad:
                    self.assertIsNone(direct.decode_one_s16(value, n))
                ordinary = bytearray(expand(blob));ordinary[5] |= 32
                self.assertIsNone(direct.decode_one_s16(bytes(ordinary), n))

    def test_maximum_supported_count(self):
        common, direct, _ = self.pairs[2]
        blob = fixture(64000)
        expected = common.decode_one_s16(expand(blob),64000)
        self.assertIsNotNone(expected)
        np.testing.assert_array_equal(direct.decode_one_s16(blob,64000),expected)

    def test_random_boundaries_and_fallback_layouts(self):
        common = self.pairs[2][0]
        for batched, rom, sparse in ((0, 0, False), (0, 1, False), (1, 0, False), (1, 1, True)):
            direct = native(self.directory/f'fallback-{batched}-{rom}-{int(sparse)}.so', self.compiler, 2,
                sparse80=sparse, defines=['-DLPX4_ENABLE_META320=1',
                    f'-DLPX4_BATCHED_REMAINING={batched}', f'-DLPX4_ROM_POINTER={rom}'])
            for index, n in enumerate((1, 40, 159, 160, 161, 319, 320, 321, 639, 640, 641)):
                blob = fixture(n, seed=index, pre=(0, 8192, 16384)[index % 3], bright=(0, 11469)[index % 2])
                expected = common.decode_one_s16(expand(blob), n)
                np.testing.assert_array_equal(direct.decode_one_s16(blob, n), expected)
                np.testing.assert_array_equal(direct.decode_one(blob, n), pwm_duties(expected))

    def test_compile_guards_and_no_new_state(self):
        for definitions in (['-DLPX4_ENABLE_META320=2'], ['-DLPX4_ENABLE_META320=1']):
            result = subprocess.run([self.compiler, '-std=c++11', *definitions, '-I'+str(ROOT/'src'),
                '-x', 'c++', '-fsyntax-only', '-'], input='#include "Lpx4HybridCore.h"\n', capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
        # A changed class layout would alter this exported array's symbol size.
        probe = self.directory/'state.cpp'
        probe.write_text('#include "Lpx4HybridCore.h"\nextern "C" { char state_size[sizeof(Lpx4HybridCore)]; }\n', encoding='utf-8')
        for meta in (0, 1):
            result = subprocess.run([self.compiler, '-std=c++11', '-S', '-DLPX4_ENABLE_SPEECH=1',
                '-DLPX4_ENABLE_SPEECH_COMPACT=1', '-DLPX4_COMPACT_ONLY=1', f'-DLPX4_ENABLE_META320={meta}',
                '-I'+str(ROOT/'src'), str(probe), '-o', str(self.directory/f'state-{meta}.s')], capture_output=True)
            self.assertEqual(result.returncode, 0)
        self.assertEqual((self.directory/'state-0.s').read_bytes(), (self.directory/'state-1.s').read_bytes())


if __name__ == '__main__':
    unittest.main()

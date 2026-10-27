"""Independent arithmetic and container checks for the host-only LPWB study."""
import copy
import unittest

import numpy as np

from batch_decoder import BatchSession
from lpx4 import BitWriter
import period_excitation as period
import speech_compact as compact
from test_speech_v4 import fixture


def model(profile=6, n=641, words=2):
    book = [[((i * (word + 1)) % 15) - 7 for i in range(32)] for word in range(words)]
    return period.from_compact(compact.repack(fixture(profile, n))[0], book,
                               initial_phase=65520, noise_seed=0xACE1)


def independent_oscillators(m):
    phase = m['initial_phase']
    seed = m['noise_seed']
    previous = 0
    phases, noise = [], []
    for code in m['phase_codes']:
        for _ in range(160):
            phases.append(phase)
            phase = (phase + code * 32) % 65536
            for _ in range(8):
                seed = (seed >> 1) ^ (0xB400 if seed & 1 else 0)
            current = (seed % 256) - 128
            noise.append(current - previous)
            previous = current
    return phases, noise


def independent_q(m):
    phases, noise = independent_oscillators(m)

    def sample(wave, phase, value):
        index, gain, level = wave
        at, frac = phase // 2048, (phase // 128) % 16
        a, b = m['book'][index][at], m['book'][index][(at + 1) % 32]
        return ((a * 16 + (b - a) * frac) * gain + 64) // 128 + (value * level + 64) // 128

    result = []
    for j, phase in enumerate(phases):
        block, offset = divmod(j, 160)
        if m['modes'][block]:
            value = sample(m['wave_params'][block], phase, noise[j])
            if block and m['modes'][block - 1] and offset < 16:
                old = sample(m['wave_params'][block - 1], phase, noise[j])
                value = (old * (16 - offset) + value * offset + 8) // 16
        else:
            _, lag, gain = m['params'][block]
            old = result[j - lag] if j >= lag else 0
            value = min(31, max(-32, (gain * old + 8) // 16))
            pos, amp = m['pulses'][j // 20]
            ep, ea = m['extras'][j // 40]
            value += (amp if j % 20 == pos else 0) + (ea if j % 40 == ep else 0)
        result.append(min(31, max(-32, value)))
    return np.asarray(result, np.int64)


class PeriodExcitationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = BatchSession('batch', v3_features=24, speech=True, speech_compact=True)
        cls.decoder = cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.session.__exit__()

    def test_all_legacy_native_v4_v5_parity_and_partial_packets(self):
        for profile in (4, 6):
            for n in (1, 19, 159, 160, 319, 320, 321, 641, 64000):
                old = bytearray(fixture(profile, n))
                old[14:16] = (4000).to_bytes(2, 'little')
                old = bytes(old)
                chunks = ((n + 319) // 320) * 8
                enhanced = compact.repack(old, extras=[(i % 40, -8 if i & 1 else 7)
                                                     for i in range(chunks)])[0]
                for source in (old, compact.repack(old)[0], enhanced):
                    m = period.from_compact(source, [[0] * 32])
                    # Evolving unused oscillators must not affect legacy output.
                    m['phase_codes'] = [255 if i & 1 else 1 for i in range(len(m['params']))]
                    data = period.pack(m)
                    expected = self.decoder.decode_one_s16(source, n)
                    np.testing.assert_array_equal(period.decode_model(data), expected)
                    np.testing.assert_array_equal(period.render_q(m), independent_q(m))
                    self.assertEqual(period.pack(period.unpack(data)), data)
                    self.assertIsNone(self.decoder.decode_one_s16(data, n))

    def test_book_integer_reference_wrap_noise_crossfade_and_mixed_history(self):
        for profile in (4, 6):
            m = model(profile, 641)
            m['modes'] = [1, 1, 0, 1, 1, 0]
            m['phase_codes'] = [255, 7, 0, 91, 1, 128]
            m['wave_params'] = [[0, 31, 15], [1, 31, 9], [0, 0, 0],
                                [0, 21, 1], [1, 29, 15], [0, 0, 0]]
            m['params'][2] = [17, 18, 14]
            m['params'][5] = [20, 145, 14]
            m['enhanced'] = True
            m['extras'] = [[0, 7], [39, -8]] * 12
            expected = independent_q(m)
            actual = period.render_q(m)
            np.testing.assert_array_equal(actual, expected)
            self.assertGreaterEqual(int(actual.min()), -32)
            self.assertLessEqual(int(actual.max()), 31)
            self.assertTrue(np.any(actual == -32) or np.any(actual == 31))
            payload = period.pack(m)
            restored = period.unpack(payload)
            np.testing.assert_array_equal(period.render_q(restored), expected)
            self.assertEqual(period.pack(restored), payload)
            self.assertEqual(period.decode_model(payload).shape, (641,))
            self.assertEqual(period.coefficients(restored).shape, (960, 10))
            phase, noise = period.oscillators(m)
            p, z = independent_oscillators(m)
            np.testing.assert_array_equal(phase, p)
            np.testing.assert_array_equal(noise, z)
            self.assertEqual(phase.dtype, np.uint16)
            self.assertEqual(noise.dtype, np.int16)
            changed = copy.deepcopy(m)
            changed['modes'] = [0] * len(changed['modes'])
            for a, b in zip(period.oscillators(changed), (phase, noise)):
                np.testing.assert_array_equal(a, b)
            # Legacy prediction must use preceding book excitation.
            zero_history = copy.deepcopy(m)
            zero_history['wave_params'][1] = [0, 0, 0]
            self.assertFalse(np.array_equal(actual[320:338], period.render_q(zero_history)[320:338]))

    def test_same_phase_fade_then_clip_and_no_boundary_fade(self):
        m = model(6, 640)
        m['book'] = [[7] * 32, [-7] * 32]
        m['modes'] = [1, 1, 0, 1]
        m['wave_params'] = [[0, 31, 0], [1, 31, 0], [0, 0, 0], [0, 31, 0]]
        m['phase_codes'] = [1, 255, 7, 19]
        q = period.render_q(m)
        old, new = 27, -27
        np.testing.assert_array_equal(q[160:176],
                                      [(old * (16 - j) + new * j + 8) >> 4 for j in range(16)])
        self.assertEqual(q[176], new)
        self.assertEqual(q[480], old)
        book = np.asarray([[7] * 32, [-7] * 32], np.int64)
        self.assertEqual(period.book_sample(book, 0, 31, 15, 65535, 255), 57)
        self.assertEqual(period.book_sample(book, 1, 31, 15, 65535, -255), -57)

    def test_dictionary_sizes_signed_nibbles_header_and_zero_seed(self):
        self.assertEqual(period.HEADER.size, 23)
        for words in (1, 2, 4, 8, 16):
            m = model(6, 1, words)
            m['noise_seed'] = 0
            m['modes'] = [1, 1]
            m['wave_params'] = [[words - 1, 31, 15], [0, 0, 0]]
            data = period.pack(m)
            header = period.HEADER.unpack_from(data)
            self.assertEqual(header[:4], (b'LPWB', 1, 6, 8000))
            self.assertEqual(len(data), 23 + 16 * words + header[-1])
            restored = period.unpack(data)
            self.assertEqual(restored['book'], m['book'])
            np.testing.assert_array_equal(period.render_q(restored), independent_q(m))
            self.assertEqual(period.oscillators(restored)[1][0], -128)

    def test_invalid_models_reject_without_silent_coercion(self):
        base = model()
        mutations = [
            ('n', 0), ('n', 64001), ('n', 3.5), ('profile', 5), ('pre', 16385),
            ('bright', 11470), ('enhanced', 2), ('initial_phase', -1), ('noise_seed', 65536),
            ('book', [[0] * 32] * 3), ('book', [[-8] * 32]), ('book', [[0] * 31]),
            ('phase_codes', [256] * 6), ('modes', [2] * 6), ('modes', [0]),
            ('params', [[1, 17, 0]] * 6), ('params', [[1, 18, 3]] * 6),
            ('params', [[32, 18, 0]] * 6), ('wave_params', [[2, 1, 0]] * 6),
            ('wave_params', [[0, 32, 0]] * 6), ('wave_params', [[0, 1, 16]] * 6),
            ('spectra', [[1] * 10] * 3), ('pulses', [[20, 0]] * 48),
            ('extras', [[0, 1]] * 24), ('pulses', [[0, 1.5]] * 48),
        ]
        for field, value in mutations:
            with self.subTest(field=field, value=repr(value)[:80]):
                m = copy.deepcopy(base)
                m[field] = value
                with self.assertRaises(ValueError):
                    period.pack(m)
        m = model(4)
        m['pulses'][0] = [0, 0]
        with self.assertRaises(ValueError):
            period.pack(m)
        del base['book']
        with self.assertRaises(ValueError):
            period.render_q(base)

    def test_truncation_header_dictionary_and_trailing_corruption(self):
        m = model(6, 320)
        data = period.pack(m)
        for cut in range(len(data)):
            with self.assertRaises(ValueError):
                period.unpack(data[:cut])
        bad = []
        for offset, value, width in ((0, 0, 4), (4, 2, 1), (5, 7, 1), (6, 7500, 2),
                                      (8, 0, 4), (8, 64001, 4), (12, 16385, 2),
                                      (14, 11470, 2), (16, 3, 1), (21, 0, 2)):
            b = bytearray(data)
            b[offset:offset + width] = value.to_bytes(width, 'little')
            bad.append(bytes(b))
        b = bytearray(data)
        b[23] = (b[23] & 240) | 8
        bad.append(bytes(b))
        bad.append(data + b'\0')
        b = bytearray(data + b'\0')
        b[21:23] = (int.from_bytes(data[21:23], 'little') + 1).to_bytes(2, 'little')
        bad.append(bytes(b))
        # Spectrum repeat/delta cannot appear before the first spectrum.
        for code in (0, 3):
            b = bytearray(data)
            start = 23 + len(m['book']) * 16
            b[start] = (b[start] & 252) | code
            bad.append(bytes(b))
        for b in bad:
            with self.assertRaises(ValueError):
                period.unpack(b)

    def test_bad_legacy_pair_extra_position_and_nonzero_padding(self):
        m = model(6, 320)
        m['enhanced'] = True
        data = period.pack(m)
        writer = BitWriter()
        compact.put_spectrum(writer, m['spectra'][0], None, 6)
        first_pair = writer.total + 9 + 15
        start = period.HEADER.size + len(m['book']) * 16

        def set_bits(data, at, width, value):
            b = bytearray(data)
            for bit in range(width):
                offset, shift = divmod(at + bit, 8)
                b[start + offset] = (b[start + offset] & ~(1 << shift)) | (((value >> bit) & 1) << shift)
            return bytes(b)

        with self.assertRaises(ValueError):
            period.unpack(set_bits(data, first_pair, 9, 511))
        # Insert an active marker and illegal position; keep payload length intact.
        b = set_bits(data, first_pair + 17, 1, 1)
        b = set_bits(b, first_pair + 18, 6, 63)
        with self.assertRaises(ValueError):
            period.unpack(b)
        # Pick packet geometry with tail padding and change only a pad bit.
        for n in (1, 321, 641):
            original = period.pack(model(4, n))
            b = bytearray(original)
            b[-1] |= 128
            if bytes(b) != original:
                with self.assertRaises(ValueError):
                    period.unpack(bytes(b))
                break
        else:
            self.fail('Expected a fixture with a zero final padding bit')


if __name__ == '__main__':
    unittest.main()

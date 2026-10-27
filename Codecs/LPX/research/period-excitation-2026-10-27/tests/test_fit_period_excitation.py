"""Bounded synthetic tests; fitted candidates are proposals without quality floors."""
import unittest

import numpy as np

import fit_period_excitation as fitter
import period_excitation as codec
import speech_compact as compact
from q0_model import synthesize, table
from test_speech_v4 import fixture


def synthetic(profile=6, n=1281):
    time = np.arange(n, dtype=np.float64) / 8000.
    reference = (4200 * np.sin(2 * np.pi * 175 * time) +
                 1600 * np.sin(2 * np.pi * 350 * time + .3)).astype(np.int16)
    source = bytearray(fixture(profile, n))
    source[14:16] = (3500).to_bytes(2, 'little')
    count = ((n + 319) // 320) * 8
    baseline = compact.repack(bytes(source), extras=[(i % 40, 7 if i & 1 else -8)
                                                   for i in range(count)])[0]
    return reference, baseline


class FitPeriodExcitationTests(unittest.TestCase):
    def test_reused_analysis_still_requires_valid_pcm16(self):
        reference, baseline = synthetic()
        analysis = fitter.analyze(reference, baseline)
        for invalid in (reference.astype(float), reference.astype(np.int64)+65536,
                        reference.reshape(1, -1), np.empty(0, np.int16)):
            with self.subTest(dtype=str(invalid.dtype), shape=invalid.shape):
                with self.assertRaises(ValueError):
                    fitter.fit(invalid, baseline, analysis=analysis)

    def test_k0_k4_serialized_exactness_determinism_zero_dc_and_byte_accounting(self):
        for profile in (4, 6):
            reference, baseline = synthetic(profile)
            analysis = fitter.analyze(reference, baseline)
            self.assertEqual(len(analysis['reference']), 1600)
            np.testing.assert_array_equal(analysis['reference'][:len(reference)], reference)
            self.assertFalse(np.any(analysis['reference'][len(reference):]))
            for words in (0, 4):
                first, report, returned = fitter.fit(reference, baseline, words=words,
                                                     rate_weight=.2, seed=123, analysis=analysis)
                cached = {key: value.copy() for key, value in analysis['book_cache'].items()}
                second, again, reused = fitter.fit(reference, baseline, words=words,
                                                   rate_weight=.2, seed=123, analysis=analysis)
                self.assertIs(returned, analysis)
                self.assertIs(reused, analysis)
                self.assertEqual(first, second)
                for key, value in cached.items():
                    np.testing.assert_array_equal(analysis['book_cache'][key], value)
                self.assertEqual({k: v for k, v in report.items() if k != 'seconds'},
                                 {k: v for k, v in again.items() if k != 'seconds'})
                model = codec.unpack(first)
                self.assertEqual(model['n'], len(reference))
                self.assertEqual(len(model['modes']), 10)
                self.assertEqual(len(codec.decode_model(first)), len(reference))
                q = codec.render_q(model)
                expected = synthesize(q[:len(reference)],
                                      np.repeat(np.asarray(model['params'])[:, 0] * 8, 2),
                                      codec.coefficients(model)[:len(reference)],
                                      table('scale_table.inc'), model['pre'], model['bright'])
                np.testing.assert_array_equal(codec.decode_model(first), expected)
                self.assertTrue(report['serialized_decode_exact'])
                self.assertEqual(report['candidate_bytes'], len(first))
                self.assertEqual(report['header_bytes'], codec.HEADER.size)
                self.assertEqual(report['dictionary_bytes'], len(model['book']) * 16)
                self.assertEqual(report['candidate_bytes'], report['header_bytes'] +
                                 report['dictionary_bytes'] + report['payload_bytes'])
                book = np.asarray(model['book'], np.int64)
                self.assertTrue(np.all(book >= -7))
                self.assertTrue(np.all(book <= 7))
                np.testing.assert_array_equal(book.sum(axis=1), np.zeros(len(book), np.int64))
                counts = report['mode_counts']
                self.assertEqual(counts['legacy'] + counts['book'], len(model['modes']))
                self.assertEqual(counts['periodic_active'] + counts['noise_only'] + counts['silent'],
                                 counts['book'])
                if words == 0:
                    self.assertFalse(np.any(book))
                    self.assertEqual(counts['periodic_active'], 0)

    def test_partial_minimum_and_full_packet_samples(self):
        for n in (1, 159, 160, 319, 320, 321):
            reference, baseline = synthetic(n=n)
            for words in (0, 4):
                data, report, analysis = fitter.fit(reference, baseline, words=words, rate_weight=.1)
                self.assertEqual(len(codec.decode_model(data)), n)
                self.assertEqual(codec.unpack(data)['n'], n)
                padded = ((n + 319) // 320) * 320
                self.assertEqual(len(analysis['reference']), padded)
                self.assertEqual(len(codec.render_q(codec.unpack(data))), padded)
                self.assertTrue(report['serialized_decode_exact'])

    def test_stale_analysis_rejects_changed_valid_reference_or_baseline(self):
        reference, baseline = synthetic()
        analysis = fitter.analyze(reference, baseline)
        changed = reference.copy()
        changed[17] += 1
        with self.assertRaisesRegex(ValueError, 'different input'):
            fitter.fit(changed, baseline, words=4, analysis=analysis)
        args = list(compact.unpack(baseline))
        args[3][0] = [19, 18, 0]
        other, _ = compact.pack(*args[:7], extras=args[7], force_extras=True)
        self.assertNotEqual(baseline, other)
        with self.assertRaisesRegex(ValueError, 'different input'):
            fitter.fit(reference, other, words=4, analysis=analysis)

    def test_invalid_dictionary_size_and_rate_values(self):
        reference, baseline = synthetic(n=320)
        for words in (-1, 1, 2, 3, 5, 32, 4.5, np.nan):
            with self.subTest(words=words), self.assertRaises(ValueError):
                fitter.fit(reference, baseline, words=words)
        for value in (-1., np.nan, np.inf, -np.inf):
            with self.subTest(rate_weight=value), self.assertRaises(ValueError):
                fitter.fit(reference, baseline, words=4, rate_weight=value)
        for value in (np.zeros(0, np.int16), np.zeros(320, np.float64),
                      np.zeros((320, 1), np.int16), np.full(320, 40000, np.int64)):
            with self.assertRaises(ValueError):
                fitter.fit(value, baseline, words=4)

    def test_advance_matches_mixed_decoder_pcm_state_and_actual_sample_error(self):
        reference, baseline = synthetic(n=641)
        m = codec.from_compact(baseline, [[7] * 16 + [-7] * 16,
                                         [((i * 3) % 15) - 7 for i in range(32)]])
        m['modes'] = [1, 1, 0, 1, 1, 0]
        m['wave_params'] = [[0, 31, 15], [1, 25, 7], [0, 0, 0],
                            [0, 18, 4], [1, 31, 15], [0, 0, 0]]
        m['phase_codes'] = [255, 7, 0, 1, 91, 32]
        m['initial_phase'] = 65520
        co = codec.coefficients(m)
        phases, noise = codec.oscillators(m)
        params = np.asarray(m['params'], np.int64)
        pulses = np.asarray(m['pulses'], np.int64)
        extras = np.asarray(m['extras'], np.int64)
        book = np.asarray(m['book'], np.int64)
        target = np.pad(reference.astype(np.int64), (0, len(co) - len(reference)))
        steps = table('scale_table.inc')
        h = np.zeros(10, np.int64)
        ring = np.zeros(256, np.int64)
        dd = cc = error = 0
        output = []
        for block, mode in enumerate(m['modes']):
            previous = m['modes'][block - 1] if block else 0
            wave = np.asarray(m['wave_params'][block], np.int64)
            old_wave = np.asarray(m['wave_params'][block - 1] if block else (0, 0, 0), np.int64)
            loss, h, dd, cc, ring, pcm = fitter._advance(
                block * 160, 160, mode, wave, previous, old_wave, book, params, pulses,
                extras, phases, noise, co, steps, m['pre'], m['bright'],
                h, dd, cc, ring, target, m['n'])
            output.append(pcm)
            error += int(loss)
        pcm = np.concatenate(output)
        q = codec.render_q(m)
        expected = synthesize(q, np.repeat(params[:, 0] * 8, 2), co,
                              steps, m['pre'], m['bright'])
        np.testing.assert_array_equal(pcm, expected)
        np.testing.assert_array_equal(codec.decode_model(codec.pack(m)), expected[:m['n']])
        delta = pcm[:m['n']].astype(np.int64) - reference.astype(np.int64)
        self.assertEqual(error, int(np.dot(delta, delta)))
        for j in range(len(q) - 256, len(q)):
            self.assertEqual(ring[j & 255], q[j])
        self.assertGreater(int(np.sum((pcm.astype(np.int64) - target) ** 2)), error)


if __name__ == '__main__':
    unittest.main()

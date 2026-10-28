"""Independent SciPy, state/branch/reset and exact-v5 objective checks."""
import unittest

import numpy as np
from scipy.signal import lfilter, lfiltic

from batch_decoder import BatchSession
from q0_model import coefficient_trace
import speech_compact as compact
from speech_objective import (SpeechObjective, WeightingState, denominator_gamma,
                              weight_error, weight_error_chunk)
from standard_metrics import pwm_duties
from test_speech_v4 import fixture
from wav_lpc import pack_frames


def scipy_variable_filter(error, co, gamma1=.9, gamma2=.6):
    """Independent direct-form-II SciPy state construction for every row.

    Rebuild the DF-II state from previous input/output history whenever LPC
    changes; carrying DF-II state directly across coefficient changes would
    implement a different time-varying filter.
    """
    output = []
    powers = np.arange(1, 11)
    for i, sample in enumerate(error):
        b = np.r_[1., co[i] / 4096. * gamma1 ** powers]
        a = np.r_[1., co[i] / 4096. * gamma2 ** powers]
        zi = lfiltic(b, a, output[max(0, i - 10):i][::-1],
                     error[max(0, i - 10):i][::-1])
        value, _ = lfilter(b, a, [sample], zi=zi)
        output.append(value[0])
    return np.array(output)


class SpeechObjectiveTests(unittest.TestCase):
    def test_constant_filter_matches_scipy_and_identity(self):
        rng = np.random.default_rng(148)
        error = rng.normal(0, 1000, 641)
        row = np.array([-2200, 500, 13, -7, 0, 0, 0, 0, 0, 0], np.int64)
        co = np.tile(row, (len(error), 1))
        for g1, g2 in ((.9, .6), (.95, .7)):
            b = np.r_[1., row / 4096. * g1 ** np.arange(1, 11)]
            a = np.r_[1., row / 4096. * g2 ** np.arange(1, 11)]
            np.testing.assert_allclose(weight_error(error, co, g1, g2),
                                       lfilter(b, a, error), rtol=1e-12, atol=1e-9)
        np.testing.assert_array_equal(weight_error(error, np.zeros_like(co)), error)

    def test_time_varying_filter_matches_independent_scipy_history_oracle(self):
        rng = np.random.default_rng(501)
        error = rng.integers(-30000, 30001, 681).astype(np.float64)
        co = np.zeros((len(error), 10), np.int64)
        # Changes cross both 160-sample interpolation and 320-sample packets.
        co[:, 0] = np.arange(len(error)) % 97 - 2100
        co[:, 1] = 480 + (np.arange(len(error)) // 160) * 13
        co[319:, 3] = -71
        expected = scipy_variable_filter(error, co)
        np.testing.assert_allclose(weight_error(error, co), expected,
                                   rtol=2e-12, atol=1e-8)

    def test_chunk_continuation_branch_copy_and_explicit_reset(self):
        rng = np.random.default_rng(81)
        error = rng.normal(size=641)
        co = np.tile(np.array([-2200, 500, 0, 0, 0, 0, 0, 0, 0, 0]), (641, 1))
        whole = weight_error(error, co)
        state = None
        parts = []
        for start, stop in zip((0, 1, 20, 159, 160, 319, 320, 500),
                               (1, 20, 159, 160, 319, 320, 500, 641)):
            part, state = weight_error_chunk(error[start:stop], co[start:stop], state=state)
            parts.append(part)
        np.testing.assert_array_equal(np.concatenate(parts), whole)
        _, checkpoint = weight_error_chunk(error[:320], co[:320])
        old_input = checkpoint.input_history.copy()
        old_output = checkpoint.output_history.copy()
        suffix, after = weight_error_chunk(error[320:], co[320:], state=checkpoint)
        branch, _ = weight_error_chunk(-error[320:], co[320:], state=checkpoint)
        again, _ = weight_error_chunk(error[320:], co[320:], state=checkpoint)
        np.testing.assert_array_equal(suffix, whole[320:])
        np.testing.assert_array_equal(suffix, again)
        np.testing.assert_array_equal(checkpoint.input_history, old_input)
        np.testing.assert_array_equal(checkpoint.output_history, old_output)
        self.assertFalse(np.shares_memory(checkpoint.input_history, after.input_history))
        self.assertFalse(np.array_equal(branch, suffix))
        reset, _ = weight_error_chunk(error[320:], co[320:], state=WeightingState.zero())
        np.testing.assert_array_equal(reset, weight_error(error[320:], co[320:]))
        self.assertFalse(np.array_equal(reset, suffix))
        empty, same = weight_error_chunk([], co[:0], state=checkpoint)
        self.assertEqual(len(empty), 0)
        np.testing.assert_array_equal(same.output_history, checkpoint.output_history)

    def test_frozen_reference_exact_sse_and_repeat_scoring(self):
        reference = np.array([-32768, 32767, 0, -11, 200], np.int16)
        candidate = np.array([32767, -32768, 0, 12, -200], np.int16)
        original = reference.copy()
        co = np.zeros((len(reference), 10), np.int64)
        sse = SpeechObjective(reference, co, mode='sse')
        weighted = SpeechObjective(reference, co)
        exact = sum((int(a) - int(b)) ** 2 for a, b in zip(reference, candidate))
        reference[:] = 0
        co[:] = 1000
        self.assertEqual(sse(candidate), exact)
        self.assertEqual(weighted(candidate), exact)
        self.assertEqual(weighted.score(original), 0)
        self.assertEqual(weighted(candidate), weighted(candidate))
        self.assertEqual(weighted.describe()['mode'], 'perceptual')

    def test_uniform_denominator_bound_handles_valid_unstable_clipped_lpc(self):
        rng = np.random.default_rng(43)
        co = rng.integers(-32768, 32768, (1281, 10), dtype=np.int64)
        reference = rng.integers(-32768, 32768, 1281, dtype=np.int16)
        candidate = rng.integers(-32768, 32768, 1281, dtype=np.int16)
        objective = SpeechObjective(reference, co)
        self.assertLess(objective.gamma2, .6)
        powers = objective.gamma2 ** np.arange(1, 11)
        self.assertLessEqual(float(np.max(np.abs(co.astype(float)) / 4096. @ powers)),
                             .950000000000001)
        error = candidate.astype(float) - reference
        expected = scipy_variable_filter(error, co, objective.gamma1, objective.gamma2)
        actual = weight_error(error, co, objective.gamma1, objective.gamma2)
        np.testing.assert_allclose(actual, expected, rtol=2e-12, atol=1e-8)
        numerator_bound = np.max(np.abs(error)) * (1 + np.max(
            np.abs(co.astype(float)) / 4096. @ (objective.gamma1 ** np.arange(1, 11))))
        self.assertLessEqual(np.max(np.abs(actual)), numerator_bound / (1 - .95))
        self.assertTrue(np.isfinite(objective(candidate)))
        self.assertEqual(denominator_gamma(np.zeros_like(co)), .6)
        self.assertEqual(objective.gamma2, denominator_gamma(co))

    def test_legal_v5_fixture_has_unstable_old_denominator_but_finite_objective(self):
        seed = compact.repack(fixture(6, 641))[0]
        fields = compact.unpack(seed)
        vectors = [[(x << 4) + 8 for x in row] for row in fields[2] for _ in range(2)]
        co = coefficient_trace(pack_frames(vectors[:5]), 641)
        # This legal ordered-spectrum seed is the regression that exposed the
        # old denominator assumption. Its final stationary pole radius is
        # about 4.11 at gamma2=.6, despite valid clipped integer decoding.
        denominator = np.r_[1., co[-1] / 4096. * .6 ** np.arange(1, 11)]
        self.assertGreater(float(np.max(np.abs(np.roots(denominator)))), 4.)
        objective = SpeechObjective.from_v5(np.zeros(641, np.int16), seed)
        self.assertLess(objective.gamma2, .11)
        self.assertTrue(np.isfinite(objective(compact.decode_model(seed))))

    def test_chain_resets_decoder_trace_but_keeps_weighting_history(self):
        blobs = [compact.repack(fixture(profile, n))[0]
                 for profile, n in ((4, 300), (6, 321))]
        reference = np.zeros(621, np.int16)
        candidate = np.concatenate([compact.decode_model(blob) for blob in blobs])
        objective = SpeechObjective.from_chain(reference, blobs)
        traces = []
        for blob in blobs:
            n, profile, spectra, *_ = compact.unpack(blob)
            shift = 5 if profile == 4 else 4
            vectors = [[(x << shift) + (1 << (shift - 1)) for x in row]
                       for row in spectra for _ in range(2)]
            traces.append(coefficient_trace(pack_frames(vectors[:(n + 159) // 160]), n))
        co = np.concatenate(traces)
        expected = scipy_variable_filter(candidate.astype(float), co,
                                         objective.gamma1, objective.gamma2)
        self.assertAlmostEqual(objective(candidate) / float(expected @ expected), 1., places=11)
        self.assertEqual(objective.describe()['seed_segment_samples'], [300, 321])
        independently_reset = np.concatenate([
            weight_error(candidate[:300], traces[0], objective.gamma1, objective.gamma2),
            weight_error(candidate[300:], traces[1], objective.gamma1, objective.gamma2)])
        self.assertFalse(np.allclose(expected, independently_reset, rtol=1e-12, atol=1e-10))
        for bad in ([], blobs[:1], blobs[0]):
            with self.assertRaises(ValueError):
                SpeechObjective.from_chain(reference, bad)

    def test_v5_seed_weights_and_native_model_pcm_pwm_partial_tails(self):
        with BatchSession('batch', v3_features=124, speech=True, speech_compact=True) as common, \
                BatchSession('batch', v3_features=124, speech=True, speech_compact=True,
                             compact_only=True) as only:
            for profile in (4, 6):
                for n in (1, 159, 180, 280, 300, 319, 320, 321, 500, 641):
                    seed = compact.repack(fixture(profile, n), extras=[
                        (i % 40, -8 if i & 1 else 7) for i in range(((n + 319) // 320) * 8)])[0]
                    pcm = compact.decode_model(seed)
                    for decoder in (common, only):
                        np.testing.assert_array_equal(decoder.decode_one_s16(seed, n), pcm)
                        np.testing.assert_array_equal(decoder.decode_one(seed, n), pwm_duties(pcm))
                    ref = np.resize(np.array([300, -800, 1000, 0], np.int16), n)
                    objective = SpeechObjective.from_v5(ref, seed)
                    fields = compact.unpack(seed)
                    shift = 5 if profile == 4 else 4
                    # Build the independent input geometry from expanded v4.
                    spectra = fields[2]
                    vectors = [[(x << shift) + (1 << (shift - 1)) for x in row]
                               for row in spectra for _ in range(2)]
                    co = coefficient_trace(pack_frames(vectors[:(n + 159) // 160]), n)
                    error = pcm.astype(np.float64) - ref
                    expected = scipy_variable_filter(error, co, objective.gamma1, objective.gamma2)
                    self.assertAlmostEqual(objective(pcm) / max(1., float(expected @ expected)),
                                           1., places=11)
                    # Candidate spectra may differ, but ranking weights stay fixed.
                    fields = list(fields)
                    fields[2] = [row.copy() for row in fields[2]]
                    fields[2][-1][4] += 1
                    candidate = compact.pack(*fields[:7], extras=fields[7])[0]
                    changed = compact.decode_model(candidate)
                    expected = scipy_variable_filter(changed.astype(float) - ref, co,
                                                     objective.gamma1, objective.gamma2)
                    self.assertAlmostEqual(objective(changed) / max(1., float(expected @ expected)),
                                           1., places=11)

    def test_rejects_non_integer_pcm_bad_weights_histories_and_lengths(self):
        ref = np.zeros(20, np.int16)
        co = np.zeros((20, 10), np.int64)
        for kwargs in ({'mode': 'other'}, {'gamma1': True}, {'gamma1': .5},
                       {'gamma2': float('nan')}, {'gamma2': 0}):
            with self.assertRaises(ValueError):
                SpeechObjective(ref, co, **kwargs)
        objective = SpeechObjective(ref, co)
        for bad in (ref.astype(float), ref[:, None], ref[:-1], [],
                    np.full(20, 32768, np.int64), np.ones(20, bool)):
            with self.assertRaises(ValueError):
                objective(bad)
        for bad in (co[:, :9], co.astype(float), np.full((20, 10), 32768, np.int64)):
            with self.assertRaises(ValueError):
                SpeechObjective(ref, bad)
        for args in ((np.zeros(9), np.zeros(10)), (np.zeros(10), np.full(10, np.inf))):
            with self.assertRaises(ValueError):
                WeightingState(*args)
        for bad in ({'requested': 0}, {'requested': True}, {'bound': 1},
                    {'bound': float('nan')}):
            with self.assertRaises(ValueError):
                denominator_gamma(co, **bad)
        with self.assertRaises(ValueError):
            weight_error_chunk([np.nan], co[:1])
        with self.assertRaises(ValueError):
            weight_error_chunk([0], co[:1], state=(np.zeros(10), np.zeros(10)))
        seed = compact.repack(fixture(4, 20))[0]
        with self.assertRaises(ValueError):
            SpeechObjective.from_v5(ref[:-1], seed)


if __name__ == '__main__':
    unittest.main()

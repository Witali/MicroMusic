import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from batch_decoder import BatchSession
from enhance_speech_compact import advance, sse
from q0_model import coefficient_trace, table
import refine_speech_trajectory as trajectory
from refine_speech_lpc import coefficient_patch
import speech_compact as compact
from speech_objective import SpeechObjective
from standard_metrics import error_metrics, pwm_duties, pwm_pcm16
from test_speech_v4 import fixture
from wav_lpc import pack_frames


def seed(profile=4, n=640):
    parts = list(compact.unpack(compact.repack(fixture(profile, n))[0]))
    parts[2] = [[2+3*i for i in range(10)] if profile == 4 else [3+6*i for i in range(10)]
                for _ in parts[2]]
    parts[3] = [(20, 60, 8)]*len(parts[3])
    parts[5] = parts[6] = 0
    return compact.pack(*parts[:7], extras=[(i % 40, 2) for i in range(len(parts[7]))])[0]


def altered(blob, frames):
    parts = list(compact.unpack(blob))
    parts[2] = [row.copy() for row in parts[2]]
    for frame in frames:
        parts[2][frame][4] += 1
    return compact.pack(*parts[:7], extras=parts[7])[0]


class TrajectoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = BatchSession('batch', speech=True, speech_compact=True, compact_only=True)
        cls.decoder = cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.session.__exit__()

    def test_non_speech_never_calls_stoi_and_keeps_exact_full_tail_output(self):
        for profile in (4, 6):
            blob = seed(profile, 641)
            reference = compact.decode_model(altered(blob, [0]))
            with patch.object(trajectory, 'quality', side_effect=AssertionError('Speech metrics used')):
                result, pcm, report, _ = trajectory.refine(reference, blob, self.decoder,
                    len(blob) + 32, frame_limit=1, spectral_candidates=1,
                    excitation_candidates=0, max_evaluations=16, speech=False)
            self.assertIsNotNone(result)
            self.assertEqual(report['quality_kind'], 'non-speech-numerical')
            self.assertGreater(report['full_synthesis_evaluations'], 0)
            self.assertEqual(report['selected']['pcm16'], error_metrics(reference, pcm))
            self.assertEqual(report['selected']['pwm8'], error_metrics(reference, pwm_pcm16(pcm)))
            self.assertIsNone(report['selected']['pcm16']['stoi'])
            self.assertIsNone(report['selected']['pwm8']['stoi'])
            np.testing.assert_array_equal(pcm, compact.decode_model(result))
            with BatchSession('batch', speech=True, speech_compact=True) as common:
                np.testing.assert_array_equal(pcm, common.decode_one_s16(result, 641))
                np.testing.assert_array_equal(pwm_duties(pcm), common.decode_one(result, 641))

    def test_default_speech_policy_is_identical_to_explicit_true(self):
        blob = seed()
        reference = compact.decode_model(altered(blob, [0]))
        options = dict(frame_limit=1, spectral_candidates=1, excitation_candidates=0, max_evaluations=16)
        implicit = trajectory.refine(reference, blob, self.decoder, len(blob) + 32, **options)
        explicit = trajectory.refine(reference, blob, self.decoder, len(blob) + 32, speech=True, **options)
        self.assertEqual(implicit[0], explicit[0])
        self.assertEqual(implicit[3], explicit[3])
        self.assertEqual(implicit[2]['selected'], explicit[2]['selected'])
        self.assertEqual(implicit[2]['quality_kind'], 'speech')
        for invalid in (None, 1, 'speech'):
            with self.assertRaisesRegex(ValueError, 'boolean'):
                trajectory.refine(reference, blob, self.decoder, len(blob) + 32, speech=invalid)

    def test_beam_crosses_a_nonimproving_first_frame_with_exact_integer_output(self):
        for profile in (4, 6):
            blob = seed(profile)
            first, second, target = altered(blob, [0]), altered(blob, [1]), altered(blob, [0, 1])
            waveforms = [(compact.decode_model(b), value) for b, value in
                         ((blob, 10), (first, 11), (second, 11), (target, 0))]
            reference = compact.decode_model(target)
            def objective(pcm):
                self.assertEqual(len(pcm), len(reference))
                return next((value for wave, value in waveforms if np.array_equal(wave, pcm)), 100)
            def neighbours(fields, frame, profile):
                changed = fields.copy()
                changed.spectra[frame, 4] += 1
                yield changed, ('lsf', frame, 4, 1)
            with patch.object(trajectory, '_spectral_neighbours', neighbours), patch.object(trajectory, 'frame_order', return_value=[0]):
                result, pcm, report, raw = trajectory.refine(reference, blob, self.decoder,
                    max(map(len, (blob, first, second, target))), frame_limit=1,
                    beam_width=2, spectral_candidates=1, excitation_candidates=0,
                    objective=objective, objective_name='synthetic delayed-choice proof', selection='objective')
                greedy = trajectory.refine(reference, blob, self.decoder,
                    max(map(len, (blob, first, second, target))), frame_limit=1,
                    beam_width=1, spectral_candidates=1, excitation_candidates=0,
                    objective=objective, selection='objective')[0]
            self.assertEqual(result, target)
            self.assertEqual(raw, target)
            self.assertEqual(greedy, blob)
            self.assertEqual(report['checkpoints'][0]['frames'], 2)
            self.assertGreater(report['completed_parent_expansions'], 1)
            np.testing.assert_array_equal(pcm, reference)
            np.testing.assert_array_equal(self.decoder.decode_one(result, len(reference)), pwm_duties(reference))

    def test_unpatched_joint_lpc_pitch_and_pulse_search_improves_known_target(self):
        for profile in (4, 6):
            blob = seed(profile)
            parts = list(compact.unpack(altered(blob, [0])))
            parts[3] = list(parts[3])
            scale, lag, gain = parts[3][0]
            parts[3][0] = (scale-1, lag, gain)
            target = compact.pack(*parts[:7], extras=parts[7])[0]
            reference = compact.decode_model(target)
            result, pcm, report, _ = trajectory.refine(reference, blob, self.decoder,
                max(len(blob), len(target))+30, frame_limit=1, beam_width=2,
                spectral_candidates=4, excitation_candidates=1, max_evaluations=256,
                selection='objective')
            self.assertLess(report['selected']['pcm16']['error_energy'], report['baseline']['pcm16']['error_energy'])
            self.assertGreater(report['changed_spectral_indices'], 0)
            self.assertGreater(report['changed_excitation_fields'], 0)
            self.assertGreater(report['excitation_trials'], 0)
            self.assertLessEqual(report['full_synthesis_evaluations'], 256)
            np.testing.assert_array_equal(pcm, compact.decode_model(result))

    def test_branch_state_and_interpolation_are_independent_across_frames_and_partial_tail(self):
        for profile in (4, 6):
            blob = seed(profile, 641)
            n, _, spectra, params, pulses, pre, bright, extras = compact.unpack(blob)
            fields = trajectory.Fields(*(np.asarray(x, np.int64) for x in (spectra, params, pulses, extras)))
            shift = 5 if profile == 4 else 4
            vectors = [[(int(v) << shift)+(1 << (shift-1)) for v in row] for row in spectra for _ in range(2)]
            co = coefficient_trace(pack_frames(vectors[:(n+159)//160]), n)
            pcm = compact.decode_model(blob)
            search = trajectory.Search(pcm.astype(np.int64), n, profile, pre, bright, len(blob)+100,
                lambda out: int(sse(pcm, out)), 100, 'none', 0, 0.0)
            parent = trajectory.PathState(fields, co, pcm, blob, 0.0, trajectory.State.zero(), 0, ())
            changed = fields.copy();changed.spectra[0, 4] += 1;changed.params[0, 1] += 1
            coefficients = co.copy();coefficients[:480] = coefficient_patch(changed.spectra, profile, 0, n)
            child = search.candidate(parent, changed, coefficients, ('joint-proof', 0))
            sibling = search.candidate(parent, fields.copy(), co.copy(), ('keep', 0))
            self.assertFalse(np.shares_memory(child.state.history, sibling.state.history))
            self.assertFalse(np.shares_memory(child.state.pitch, sibling.state.pitch))
            self.assertFalse(np.shares_memory(child.fields.params, sibling.fields.params))
            self.assertFalse(np.shares_memory(child.coefficients, sibling.coefficients))
            np.testing.assert_array_equal(parent.state.history, np.zeros(10))
            changed2 = child.fields.copy();changed2.spectra[1, 4] += 1
            co2 = child.coefficients.copy();patch2 = coefficient_patch(changed2.spectra, profile, 1, n)
            co2[320:320+len(patch2)] = patch2
            grandchild = search.candidate(child, changed2, co2, ('lsf', 1, 4, 1))
            np.testing.assert_array_equal(grandchild.pcm, compact.decode_model(grandchild.stream))
            np.testing.assert_array_equal(grandchild.pcm, self.decoder.decode_one_s16(grandchild.stream, n))
            st = trajectory.State.zero()
            _, h, dd, cc, ring = advance(co2, changed2.params, changed2.pulses, changed2.extras,
                table('scale_table.inc'), pre, bright, 0, 640, st.history, 0, 0, st.pitch)
            np.testing.assert_array_equal(grandchild.state.history, h)
            np.testing.assert_array_equal(grandchild.state.pitch, ring)
            self.assertEqual((grandchild.state.deemphasis, grandchild.state.brightness), (dd, cc))

    def test_oversized_seed_is_searched_and_feasible_tradeoff_is_explicit(self):
        for profile in (4, 6):
            blob = seed(profile)
            reference = compact.decode_model(blob)
            result, pcm, report, raw = trajectory.refine(reference, blob, self.decoder, len(blob)-2,
                frame_limit=1, beam_width=2, spectral_candidates=1, excitation_candidates=0,
                max_evaluations=64, selection='objective')
            self.assertIsNotNone(result)
            self.assertLessEqual(len(result), len(blob)-2)
            self.assertEqual(report['fit_status'], 'selected_feasible')
            self.assertTrue(report['feasible_found'])
            np.testing.assert_array_equal(pcm, compact.decode_model(result))
            conservative = trajectory.refine(reference, blob, self.decoder, len(blob)-2,
                frame_limit=1, spectral_candidates=0, excitation_candidates=0, max_evaluations=16)
            self.assertIsNone(conservative[0])
            self.assertEqual(conservative[2]['fit_status'], 'feasible_tradeoff_only')
            self.assertIsNotNone(conservative[3])
            self.assertFalse(conservative[2]['conservative_floors_passed'])

    def test_feasible_frontier_is_exported_without_segment_floor_filtering(self):
        blob = seed()
        reference = compact.decode_model(blob)
        alternatives = []
        result, _, report, _ = trajectory.refine(reference, blob, self.decoder, len(blob)-2,
            frame_limit=1, spectral_candidates=0, excitation_candidates=0,
            max_evaluations=32, frontier=alternatives)
        self.assertIsNone(result)
        self.assertTrue(alternatives)
        self.assertEqual(len(alternatives), len(report['retained_frontier']))
        for entry in alternatives:
            self.assertLessEqual(entry['file_bytes'], len(blob)-2)
            self.assertEqual(entry['file_bytes'], len(entry['stream']))
            self.assertFalse(entry['conservative_floors_passed'])
            np.testing.assert_array_equal(entry['pcm'], compact.decode_model(entry['stream']))
            self.assertNotIn('stream', report['retained_frontier'][0])
            self.assertNotIn('pcm', report['retained_frontier'][0])

    def test_frontier_arrays_and_nested_metrics_do_not_alias_returned_evidence(self):
        blob = seed();reference = compact.decode_model(blob);alternatives = []
        _, pcm, report, _ = trajectory.refine(reference, blob, self.decoder, len(blob), frontier=alternatives)
        self.assertEqual(len(alternatives), 1)
        alternatives[0]['metrics']['pcm16']['error_energy'] = -1
        alternatives[0]['pcm'][:] = 123
        self.assertEqual(report['selected']['pcm16']['error_energy'], 0)
        self.assertEqual(report['retained_frontier'][0]['metrics']['pcm16']['error_energy'], 0)
        np.testing.assert_array_equal(pcm, reference)
        report['retained_frontier'][0]['metrics']['pcm16']['error_energy'] = -2
        self.assertEqual(alternatives[0]['metrics']['pcm16']['error_energy'], -1)

    def test_exact_marginal_policy_integrates_with_the_shared_synthesis_budget(self):
        blob = seed()
        reference = compact.decode_model(blob)
        result, pcm, report, _ = trajectory.refine(reference, blob, self.decoder, len(blob)-2,
            frame_limit=1, spectral_candidates=0, excitation_candidates=0,
            max_evaluations=96, capacity_policy='marginal', allocation_evaluations=64,
            selection='objective')
        self.assertIsNotNone(result)
        self.assertLessEqual(len(result), len(blob)-2)
        self.assertGreater(report['allocation_evaluations'], 1)
        self.assertLessEqual(report['full_synthesis_evaluations'], 96)
        self.assertLessEqual(report['allocation_evaluations'], 64)
        with BatchSession('batch', speech=True, speech_compact=True) as common:
            np.testing.assert_array_equal(pcm, common.decode_one_s16(result, len(reference)))
        np.testing.assert_array_equal(pcm, compact.decode_model(result))

    def test_finite_no_fit_is_reported_without_rejecting_the_input_cap(self):
        blob = seed()
        result, pcm, report, raw = trajectory.refine(compact.decode_model(blob), blob,
            self.decoder, 22, frame_limit=1, spectral_candidates=1, excitation_candidates=0,
            max_evaluations=16, selection='objective')
        self.assertIsNone(result);self.assertIsNone(pcm);self.assertIsNone(raw)
        self.assertEqual(report['fit_status'], 'no_feasible_candidate')
        self.assertGreater(report['best_encountered_oversize_bytes'], 22)
        self.assertLessEqual(report['full_synthesis_evaluations'], 16)

    def test_original_remains_eligible_and_rejected_floor_cannot_overwrite_it(self):
        blob = seed()
        target = altered(blob, [0])
        reference = compact.decode_model(target)
        with patch.object(trajectory, 'no_regression', return_value=False):
            result, pcm, report, raw = trajectory.refine(reference, blob, self.decoder,
                max(len(blob), len(target))+10, frame_limit=1, spectral_candidates=2,
                excitation_candidates=0, max_evaluations=64)
        # The original is always an eligible rollback, even if a custom gate rejects every proposal.
        self.assertEqual(result, blob)
        self.assertTrue(report['native_model_pwm_exact'])
        self.assertIsNotNone(raw)
        np.testing.assert_array_equal(pcm, compact.decode_model(blob))

    def test_objective_and_capacity_hooks_receive_full_waveform_and_frozen_prefix(self):
        blob = seed()
        n, profile, spectra, params, pulses, pre, bright, extras = compact.unpack(blob)
        fields = trajectory.Fields(*(np.asarray(x, np.int64) for x in (spectra, params, pulses, extras)))
        shift = 5 if profile == 4 else 4
        co = coefficient_trace(pack_frames([[(int(v) << shift)+(1 << (shift-1)) for v in row]
                                           for row in spectra for _ in range(2)]), n)
        pcm = compact.decode_model(blob)
        calls = []
        def bad_policy(sp, p, ee, cap, **kwargs):
            self.assertEqual(kwargs['start'], 320)
            calls.append(kwargs['render'](ee))
            self.assertTrue(kwargs['serialize'](ee))
            ee[0] = (-1, 0)
            return SimpleNamespace(extras=ee)
        search = trajectory.Search(pcm.astype(np.int64), n, profile, pre, bright, len(blob)-1,
            lambda out: float(sse(pcm, out)), 32, bad_policy, 8, 0.0)
        root = trajectory.PathState(fields, co, pcm, blob, 0.0, trajectory.State.zero(), 0, ())
        parent = search.at_position(root, 320)
        with self.assertRaises(ValueError):
            search.candidate(parent, fields.copy(), co.copy(), ('bad-policy',))
        self.assertEqual(len(calls[0]), n)
        np.testing.assert_array_equal(fields.extras, np.asarray(extras))

    def test_bound_perceptual_objective_and_perfect_baseline(self):
        blob = seed(6, 321)
        reference = compact.decode_model(blob)
        objective = SpeechObjective.from_v5(reference, blob, mode='perceptual')
        result, pcm, report, raw = trajectory.refine(reference, blob, self.decoder, len(blob),
            frame_limit=1, spectral_candidates=0, excitation_candidates=0,
            max_evaluations=8, objective=objective, objective_name=objective.name)
        self.assertEqual(result, blob)
        self.assertEqual(raw, blob)
        self.assertEqual(report['raw_objective'], 0.0)
        self.assertTrue(report['conservative_floors_passed'])
        np.testing.assert_array_equal(pcm, reference)

    def test_local_screen_matches_independent_suffix_context_and_serializes_only_finalists(self):
        blob = altered(seed(6, 1280), [0])
        target = altered(blob, [1]);reference = compact.decode_model(target)
        n, profile, spectra, params, pulses, pre, bright, extras = compact.unpack(blob)
        fields = trajectory.Fields(*(np.asarray(x, np.int64) for x in (spectra, params, pulses, extras)))
        vectors = [[(int(v) << 4)+8 for v in row] for row in spectra for _ in range(2)]
        co = coefficient_trace(pack_frames(vectors), n);pcm = compact.decode_model(blob)
        search = trajectory.Search(reference.astype(np.int64), n, profile, pre, bright, len(blob)+30,
            lambda out: float(sse(reference, out)), 64, 'none', 0, 0.0, 'local', 640)
        root = trajectory.PathState(fields, co, pcm, blob, 0.0, trajectory.State.zero(), 0, ())
        parent = search.at_position(root, 320)
        expected = []
        for changed, move in trajectory._spectral_neighbours(fields, 1, profile):
            packed = compact.pack(n, profile, changed.spectra.tolist(), changed.params.tolist(),
                changed.pulses.tolist(), pre, bright, extras=changed.extras.tolist())[0]
            independent = compact.decode_model(packed)
            expected.append((int(sse(reference[320:960], independent[320:960])), len(packed), move))
        children = trajectory._expand(search, parent, 1, 2, 0, 80)
        selected = {child.moves[-1] for child in children if child.moves[-1][0] == 'lsf'}
        self.assertEqual(selected, {item[2] for item in sorted(expected)[:2]})
        self.assertEqual(search.local_evaluations, len(expected))
        self.assertEqual(search.local_samples, 640*len(expected))
        self.assertEqual(search.serializations, 3)
        self.assertEqual(search.evaluations, 3)
        for child in children:
            np.testing.assert_array_equal(child.pcm, compact.decode_model(child.stream))
        full = trajectory.Search(reference.astype(np.int64), n, profile, pre, bright, len(blob)+30,
            lambda out: float(sse(reference, out)), 64, 'none', 0, 0.0, 'full', 640)
        trajectory._expand(full, full.at_position(root, 320), 1, 2, 0, 80)
        self.assertEqual(full.local_evaluations, 0)
        self.assertEqual(full.serializations, 1+len(expected))

    def test_interrupted_adjacent_window_reports_completed_frames_explicitly(self):
        blob = seed();reference = compact.decode_model(altered(blob, [0]))
        with patch.object(trajectory, 'frame_order', return_value=[0]):
            _, _, report, _ = trajectory.refine(reference, blob, self.decoder, len(blob)+30,
                frame_limit=1, beam_width=1, spectral_candidates=1,
                excitation_candidates=0, max_evaluations=2)
        self.assertTrue(report['search_limit_reached'])
        self.assertEqual(report['completed_windows'], 0)
        self.assertEqual(report['incomplete_windows'], 1)
        window = report['checkpoints'][0]
        self.assertEqual(window['status'], 'evaluation_limit')
        self.assertEqual(window['frames'], 1)
        self.assertEqual(window['planned_frames'], 2)
        self.assertEqual(window['interrupted_frame'], 1)

    def test_beam_and_allocator_use_the_same_lambda_per_serialized_bit(self):
        search = trajectory.Search(np.zeros(1, np.int64), 1, 4, 0, 0, 100,
            lambda out: 0.0, 1, 'none', 0, 1.0)
        short = trajectory.OutputCandidate(b'x'*30, np.zeros(1, np.int16), 100.0, ())
        long = trajectory.OutputCandidate(b'x'*31, np.zeros(1, np.int16), 96.0, ())
        self.assertEqual(search.rank(short)[1], trajectory.distortion_rate(100.0, 30, 1.0))
        self.assertEqual(search.rank(long)[1], trajectory.distortion_rate(96.0, 31, 1.0))
        # Per-byte lambda would incorrectly prefer the longer alternative here.
        self.assertLess(search.rank(short), search.rank(long))

    def test_validation_and_hard_evaluation_bound(self):
        blob = seed();reference = compact.decode_model(blob)
        for kwargs in ({'beam_width':True},{'window_frames':1},{'max_evaluations':0},
                       {'capacity_policy':'unknown'},{'selection':'unknown'}, {'rate_lambda':np.inf}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                trajectory.refine(reference, blob, self.decoder, len(blob), **kwargs)
        with self.assertRaises(ValueError):
            trajectory.refine(reference.astype(float), blob, self.decoder, len(blob))
        with self.assertRaises(ValueError):
            trajectory.refine(reference, blob, self.decoder, len(blob), objective=lambda pcm: np.nan)
        result, _, report, _ = trajectory.refine(reference, blob, self.decoder, len(blob),
            objective=lambda pcm: float(sse(reference, pcm)), max_evaluations=3)
        self.assertEqual(result, blob)
        self.assertLessEqual(report['full_synthesis_evaluations'], 3)
        self.assertTrue(report['search_limit_reached'])


if __name__ == '__main__':
    unittest.main()

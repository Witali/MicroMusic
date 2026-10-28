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
from standard_metrics import pwm_duties
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
        self.assertTrue(report['search_limit_reached'])

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

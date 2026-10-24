"""Focused tests for encoder-only weighted lookahead proposal semantics."""
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('perceptual_fit_tested',ROOT/'tools/probe-q3-perceptual-fit.py')
fit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fit
spec.loader.exec_module(fit)


@dataclass
class State:
    frames: np.ndarray
    durations: np.ndarray
    book: np.ndarray
    nearest: bool = False
    tilt: int = 1


def state(n=3):
    return State(np.tile(np.array([35,18,0x99,0x99,0x99,0x99],np.uint8),(n,1)),
        np.full(n,64,np.uint16),np.zeros((4,16),np.int8))


class PerceptualFitTests(unittest.TestCase):
    def test_original_only_weights_finite_on_silence_and_periodicity(self):
        t = np.arange(512)
        frames = np.array([np.zeros(512),np.cos(2*np.pi*t/37)])
        weights,lpc = fit.perceptual_weights(frames)
        self.assertEqual(weights.shape,(2,257))
        self.assertTrue(np.all(np.isfinite(weights)))
        self.assertTrue(np.all(weights > 0))
        np.testing.assert_array_equal(weights[0],np.ones(257))
        self.assertGreater(float(np.std(weights[1])),.1)
        self.assertEqual(lpc.shape,(2,9))

    def test_guide_identity_full_duration_and_no_input_mutation(self):
        x = .2*np.sin(2*np.pi*np.arange(1024)/37)
        guide = fit.PerceptualGuide(x)
        before = guide.reference_fft.copy()
        self.assertEqual(guide.evaluate(x,128,768),(0.,0.))
        residual,spectrum = guide.evaluate(x*.5,128,768)
        self.assertGreater(residual,0)
        self.assertGreater(spectrum,0)
        np.testing.assert_array_equal(guide.reference_fft,before)
        with self.assertRaises(ValueError):
            guide.evaluate(x[:768],128,768)

    def test_exact_frame_bounds_keep_final_frame0_reload_explicit(self):
        starts,stops = fit.frame_bounds([64,128,256])
        np.testing.assert_array_equal(starts,[0,63,191])
        np.testing.assert_array_equal(stops,[63,191,447])
        self.assertEqual(int(stops[-1]),64+128+256-1)

    def test_dual_rankings_preserve_both_extremes(self):
        states = [state(1) for _ in range(3)]
        for i,s in enumerate(states):
            s.frames[0,0] += i
        scored = [((0.,100.),states[0]),((1.,1.),states[1]),((100.,0.),states[2])]
        selected = fit.diverse_best(scored,2)
        self.assertEqual([int(s.frames[0,0]) for _,s in selected],[35,37])

    def test_beam_crosses_bad_single_prefix_without_committing_it(self):
        seed = state(2)
        frozen = seed.frames.copy()
        def variants(anchor,index):
            yield anchor
            trial = State(anchor.frames.copy(),anchor.durations.copy(),anchor.book.copy())
            trial.frames[index,0] += 1
            yield trial
        def guide(candidate):
            edits = int(np.sum(candidate.frames[:,0] != seed.frames[:,0]))
            return {0:(1.,1.),1:(2.,2.),2:(0.,0.)}[edits]
        result = fit.trajectory_beam([seed],[0,1],guide,width=2,variants=variants)
        best = min(result,key=lambda pair:pair[0])[1]
        np.testing.assert_array_equal(best.frames[:,0],[36,36])
        np.testing.assert_array_equal(seed.frames,frozen)

    def test_correlated_coefficients_preserve_reuse_and_sample_count(self):
        seed = state(4)
        old_size = len(fit.pack_stream(seed.frames,seed.durations))
        alternatives = list(fit.coefficient_block_seeds(seed,[1,2],False))
        self.assertGreater(len(alternatives),5)
        joint = [s for s in alternatives if int(s.frames[0,2]) == 0xaa]
        self.assertTrue(joint)
        for candidate in alternatives:
            np.testing.assert_array_equal(candidate.durations,seed.durations)
            self.assertEqual(len(fit.pack_stream(candidate.frames,candidate.durations)),old_size)
            self.assertTrue(np.all(candidate.frames[:,2:] & 15))
            self.assertTrue(np.all(candidate.frames[:,2:] >> 4))
            np.testing.assert_array_equal(candidate.frames[0,2:],candidate.frames[-1,2:])

    def test_source_variant_joint_pitch_gain_preserves_modes_and_book(self):
        seed = state(2)
        variants = list(fit.source_variants(seed,1))
        matching = [s for s in variants if int(s.frames[1,0]) == 36 and int(s.frames[1,1]) == 19]
        self.assertTrue(matching)
        for candidate in variants:
            np.testing.assert_array_equal(candidate.frames[0],seed.frames[0])
            np.testing.assert_array_equal(candidate.book,seed.book)
            self.assertTrue(np.all(candidate.frames[:,2:] == seed.frames[:,2:]))

    def test_unused_pole_feature_selection_is_byte_exact_and_rejects_active_pole(self):
        seed = state(3)
        model = dict(schema='hq4-q3-pulsebook-pole-v1',frames=seed.frames.tolist(),
            durations=seed.durations.tolist(),pulsebook=seed.book.tolist(),nearest=False,tilt_shift=1)
        converted,proof = fit.unused_pole_conversion(model)
        self.assertEqual(converted['schema'],'hq4-q3-pulsebook-v1')
        self.assertEqual(model['schema'],'hq4-q3-pulsebook-pole-v1')
        self.assertEqual(converted['frames'],model['frames'])
        self.assertTrue(proof['exact_pcm_equal'])
        self.assertTrue(proof['exact_internal_counts_equal'])
        self.assertFalse(proof['actual_converted_firmware_verified'])
        model['frames'][0][2] = 0x90
        with self.assertRaisesRegex(ValueError,'active'):
            fit.unused_pole_conversion(model)

    def test_zero_tail_conversion_is_exact_and_rejects_nonzero_tail(self):
        seed = state(3)
        book = np.zeros((4,32),np.int8)
        book[:,:4] = [2,3,2,-1]
        model = dict(schema='hq4-q3-pulsebook32-v1',frames=seed.frames.tolist(),
            durations=seed.durations.tolist(),pulsebook=book.tolist(),nearest=False,tilt_shift=1)
        converted,proof = fit.zero_tail_conversion(model)
        self.assertEqual(converted['schema'],'hq4-q3-pulsebook-v1')
        self.assertEqual(np.asarray(converted['pulsebook']).shape,(4,16))
        self.assertTrue(proof['exact_pcm_equal'])
        self.assertTrue(proof['exact_internal_counts_equal'])
        self.assertTrue(proof['exact_packed_stream_equal'])
        self.assertEqual(np.asarray(model['pulsebook']).shape,(4,32))
        model['pulsebook'][3][31] = 1
        with self.assertRaisesRegex(ValueError,'Active'):
            fit.zero_tail_conversion(model)


if __name__ == '__main__':
    unittest.main()

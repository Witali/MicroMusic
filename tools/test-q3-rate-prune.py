"""Rate pruning must use decoded loss, real bytes and full-size intermediates."""
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tested_q3_rate_prune',ROOT/'tools/probe-q3-rate-prune.py')
prune = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = prune
spec.loader.exec_module(prune)


def seed():
    # Three independent final-frame coefficient halves can be replaced; the
    # unchanged first half on frame1 means replacement at frame2 saves bytes.
    f = np.array([[35,2,0x99,0x99,0x99,0x99],
                  [35,2,0x99,0x99,0xaa,0x99],
                  [35,2,0xab,0x99,0xbb,0x99]],np.uint8)
    return prune.search.State(f,np.full(3,64,np.uint16),prune.codec.legacy_tables(),False,1)


class RatePruneTests(unittest.TestCase):
    def test_real_packer_rejects_nominal_saving_cancelled_by_retransmission(self):
        state = seed()
        proposals = list(prune.half_reuse_proposals(state))
        self.assertTrue(proposals)
        for p in proposals:
            self.assertEqual(p.saved,len(prune.pack_stream(state.frames,state.durations))-len(prune.pack_stream(p.state.frames,p.state.durations)))
            self.assertGreater(p.saved,0)
            np.testing.assert_array_equal(p.state.durations,state.durations)
            np.testing.assert_array_equal(p.state.book,state.book)
            np.testing.assert_array_equal(p.state.frames[:,:2],state.frames[:,:2])

    def test_decoded_quality_beats_nearest_nibble_choice(self):
        state = seed()
        proposals = list(prune.half_reuse_proposals(state))
        legacy = min(proposals,key=lambda p:(p.legacy_distance/p.saved,p.frame,p.half))
        preferred = max(proposals,key=lambda p:(p.legacy_distance/p.saved,p.frame,p.half))
        self.assertNotEqual(legacy.state.frames.tobytes(),preferred.state.frames.tobytes())
        target = len(prune.pack_stream(preferred.state.frames,preferred.state.durations))
        def evaluate(candidate):
            cost = 0. if np.array_equal(candidate.frames,preferred.state.frames) else 10.
            return dict(stoi=1-cost*.01,spectrogram_loss=cost,loss=cost)
        final,report = prune.quality_prune(state,target,evaluate,lambda score:score['loss'],shortlist=0)
        np.testing.assert_array_equal(final.frames,preferred.state.frames)
        self.assertTrue(report['final_fits_requested_capacity'])

    def test_original_capacity_intermediates_can_reach_smaller_final_cap(self):
        state = seed()
        original = len(prune.pack_stream(state.frames,state.durations))
        target = original-4
        seen_sizes = []
        def evaluate(candidate):
            size = len(prune.pack_stream(candidate.frames,candidate.durations))
            seen_sizes.append(size)
            self.assertLessEqual(size,original)
            return dict(stoi=.8,spectrogram_loss=.5,loss=float(original-size))
        final,report = prune.quality_prune(state,target,evaluate,lambda score:score['loss'],shortlist=0)
        self.assertTrue(any(target < size < original for size in seen_sizes))
        self.assertTrue(report['final_fits_requested_capacity'])
        self.assertLessEqual(len(prune.pack_stream(final.frames,final.durations)),target)

    def test_budget_exhaustion_is_explicit_and_does_not_claim_final_capacity(self):
        state = seed()
        original = len(prune.pack_stream(state.frames,state.durations))
        def evaluate(candidate):
            return dict(stoi=.8,spectrogram_loss=.5,loss=1.)
        final,report = prune.quality_prune(state,original-4,evaluate,lambda score:score['loss'],max_evaluations=0)
        self.assertFalse(report['final_fits_requested_capacity'])
        self.assertEqual(report['stop_reason'],'evaluation_budget_exhausted')
        self.assertEqual(report['exact_evaluations'],0)
        np.testing.assert_array_equal(final.frames,state.frames)

    def test_guard_invalid_best_candidate_is_never_selected(self):
        state = seed()
        proposals = list(prune.half_reuse_proposals(state))
        forbidden = proposals[0].state.frames.tobytes()
        def evaluate(candidate):
            if candidate.frames.tobytes() == forbidden:
                return None
            return dict(stoi=.8,spectrogram_loss=.5,loss=1.)
        target = len(prune.pack_stream(state.frames,state.durations))-2
        final,report = prune.quality_prune(state,target,evaluate,lambda score:score['loss'],shortlist=0)
        self.assertNotEqual(final.frames.tobytes(),forbidden)
        self.assertTrue(report['final_fits_requested_capacity'])
        self.assertGreater(report['counts']['exact_guard_rejections'],0)

    def test_q7_map_distance_uses_values_and_resonance_not_index_spacing(self):
        state = seed()
        state.book[4,9],state.book[4,10] = -126,0
        a = prune.reflection_vector(np.array([35,2,0x99,0x99,0x99,0x99]),state.book)
        b = prune.reflection_vector(np.array([35,2,0x9a,0x99,0x99,0x99]),state.book)
        self.assertAlmostEqual(a[0],-126/128)
        self.assertEqual(b[0],0)
        self.assertGreater(float(abs(np.arctanh(a[0])-np.arctanh(b[0]))),2.)


if __name__ == '__main__':
    unittest.main()

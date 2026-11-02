"""Small proposal contracts; no excitation search or corpus job is launched."""
import unittest
from unittest.mock import patch

import numpy as np

import spectral_round as spectral


def fixture(kbps):
    n = 9600
    vector = [2 + 3 * index for index in range(10)]
    if kbps == 2:
        vector = [4 + 5 * index for index in range(10)]
    other = vector.copy()
    other[5] += 1
    spectra = [vector.copy() for _ in range(15)] + [other.copy() for _ in range(15)]
    params = [(1, 18, 0)] * (30 if kbps == 2 else 60)
    pulses = [(0, -8)] * (120 if kbps == 2 else 480)
    blob = (spectral.sparse.pack(n, spectra, params, pulses) if kbps == 2 else
            spectral.compact.pack(n, 4, spectra, params, pulses)[0])
    target = np.rint(800 * np.sin(2 * np.pi * 200 * np.arange(n) / 8000)).astype(np.int16)
    return target, blob, np.asarray(spectra), params, pulses


class SpectralRoundContracts(unittest.TestCase):
    def test_both_families_have_exact_cap_legal_immutable_deterministic_proposals(self):
        for kbps in (2, 3):
            target, blob, spectra, params, pulses = fixture(kbps)
            original_target, original_spectra = target.copy(), spectra.copy()
            first, report = spectral.proposals(target, blob, kbps)
            second, repeated = spectral.proposals(target, blob, kbps)
            self.assertEqual(report, repeated)
            self.assertEqual([item.family for item in first], ['coordinate'] * 2 + ['boundary'] * 2)
            self.assertEqual(len(first), 4)
            self.assertEqual(report['runs'], 2)
            self.assertEqual(report['complete_byte_cap'], len(target) * kbps // 64)
            for proposal, repeated_proposal in zip(first, second):
                self.assertEqual(proposal.identity, repeated_proposal.identity)
                self.assertEqual(proposal.proxy_delta, repeated_proposal.proxy_delta)
                np.testing.assert_array_equal(proposal.spectra, repeated_proposal.spectra)
                self.assertFalse(proposal.spectra.flags.writeable)
                self.assertTrue(np.all(np.diff(proposal.spectra, axis=1) > 0))
                self.assertFalse(np.array_equal(proposal.spectra, spectra))
                serialized = (spectral.sparse.pack(len(target), proposal.spectra.tolist(), params, pulses)
                    if kbps == 2 else spectral.compact.pack(len(target), 4, proposal.spectra.tolist(), params, pulses)[0])
                self.assertEqual(len(serialized), proposal.exact_layout_bytes)
                self.assertLessEqual(len(serialized), report['complete_byte_cap'])
            np.testing.assert_array_equal(target, original_target)
            np.testing.assert_array_equal(spectra, original_spectra)

    def test_coordinate_changes_whole_runs_and_boundary_changes_one_actual_neighbor_frame(self):
        target, blob, spectra, _, _ = fixture(3)
        proposals, _ = spectral.proposals(target, blob, 3)
        for proposal in proposals:
            changed = np.argwhere(proposal.spectra != spectra)
            if proposal.family == 'coordinate':
                self.assertEqual(set(changed[:, 0]), set(range(proposal.first_frame, proposal.last_frame)))
                self.assertEqual(set(changed[:, 1]), {proposal.index})
                self.assertTrue(np.all((proposal.spectra - spectra)[changed[:, 0], changed[:, 1]] == proposal.direction))
            else:
                changed_frames = np.unique(changed[:, 0])
                self.assertEqual(len(changed_frames), 1)
                index = int(changed_frames[0])
                neighbor = index - 1 if proposal.direction == 1 else index + 1
                np.testing.assert_array_equal(proposal.spectra[index], spectra[neighbor])
                self.assertEqual(list(spectral._runs(proposal.spectra)),
                    [(0, 15 + proposal.direction), (15 + proposal.direction, 30)])

    def test_proposal_cannot_be_refit_against_a_different_same_length_source(self):
        target, blob, _, _, _ = fixture(3)
        proposals, _ = spectral.proposals(target, blob, 3)
        other = target.copy()
        other[0] += 1
        with patch.object(spectral, 'search_excitation') as search:
            with self.assertRaises(ValueError):
                spectral.refit(other, blob, 3, proposals[0], np.zeros(len(target) // 160, np.int64))
            search.assert_not_called()

    def test_round_rejects_unregistered_geometry_or_level_ambiguity_before_refitting(self):
        target, blob, _, _, _ = fixture(3)
        for reference, kbps in ((target[:-1], 3), (target.astype(float), 3), (target, 2), (target, True)):
            with self.assertRaises(ValueError):
                spectral.proposals(reference, blob, kbps)


if __name__ == '__main__':
    unittest.main()

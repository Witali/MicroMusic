"""Characterize beam state/rounding against greedy replay and the full model."""
import unittest

import numpy as np

from beam_innovations import search_beam
from encode_low_bitrate_speech import fit_block
import speech_compact as compact
import speech_sparse80 as sparse
from q0_model import coefficient_trace, table
from wav_lpc import pack_frames


class BeamContracts(unittest.TestCase):
    def test_width_one_matches_greedy_and_every_cost_matches_independent_model(self):
        n = 640
        target = np.rint(3000*np.sin(2*np.pi*173*np.arange(n)/8000)).astype(np.int64)
        for sparse80 in (False, True):
            group, block = (80, 320) if sparse80 else (20, 160)
            shift = 4 if sparse80 else 5
            spectra = ([3+5*i for i in range(10)] if sparse80 else [1+3*i for i in range(10)])
            spectra = [spectra, spectra]
            vectors = [[(value<<shift)+(1<<(shift-1)) for value in row]
                       for row in spectra for _ in range(2)]
            co = coefficient_trace(pack_frames(vectors), n)
            parameters = np.asarray([(12, 37, 10)]*(n//block), np.int64)
            for guard in (False, True):
                history, ring = np.zeros(10, np.int64), np.zeros(256, np.int64)
                dd = cc = 0
                greedy = []
                for start in range(0, n, block):
                    _, history, dd, cc, ring, pulses, _ = fit_block(target, co, history,
                        dd, cc, ring, start, group, block, table('scale_table.inc')[12*8],
                        37, 10, 8192, sparse80, guard)
                    greedy.extend(pulses.tolist())
                for width in (1, 2, 4):
                    pulses, evaluations, cost = search_beam(target, co, parameters,
                        table('scale_table.inc'), 8192, sparse80, width, guard)
                    if width == 1:
                        np.testing.assert_array_equal(pulses, greedy)
                    expected_trials = (128 if sparse80 else 32)*(1+(n//group-1)*width)
                    self.assertEqual(evaluations, expected_trials)
                    blob = (sparse.pack(n, spectra, parameters.tolist(), pulses.tolist(), 8192) if sparse80 else
                            compact.pack(n, 4, spectra, parameters.tolist(), pulses.tolist(), 8192)[0])
                    pcm = (sparse.decode_model if sparse80 else compact.decode_model)(blob)
                    error = pcm.astype(np.int64)-target
                    expected_cost = int(np.dot(error, error))
                    if guard:
                        expected_cost += int(np.count_nonzero((pcm <= -32768) | (pcm >= 32767)))*(1<<42)
                    self.assertEqual(int(cost), expected_cost)


if __name__ == '__main__':
    unittest.main()

"""Exact-byte source behavior, continuous phase and offline inverse fitting."""
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_q3 import render as legacy
from q3_phasebook import render, inverse_residual, learn_waves


class PhaseBookTests(unittest.TestCase):
    def waves(self):
        return np.tile(np.array([0, 1, 2, 1, 0, -1, -2, -1], np.int8), (4, 1))

    def test_unvoiced_path_remains_exact_original_q3(self):
        f = np.array([[0, 1, 0x89, 0x88, 0x88, 0x88]], np.uint8)
        d = np.array([256], np.uint16)
        np.testing.assert_array_equal(render(f, d, self.waves())[0], legacy(f, d, 1)[0])

    def test_frame_boundaries_do_not_reset_source_phase(self):
        row = np.array([57, 8, 0x88, 0x88, 0x88, 0x88], np.uint8)
        a, count = render(row[None, :], np.array([256]), self.waves())
        b, other = render(np.tile(row, (4, 1)), np.full(4, 64), self.waves())
        np.testing.assert_array_equal(a, b)
        self.assertEqual(int(count.sum()+other.sum()), 0)

    def test_float_inverse_recovers_known_excitation_through_lattice_and_t1(self):
        f = np.array([[40, 1, 0x97, 0x89, 0x78, 0x99]], np.uint8)
        k = np.ravel(np.column_stack(((f[0, 2:] & 15).astype(float)-8,
                                     (f[0, 2:] >> 4).astype(float)-8)))/8
        source = np.random.default_rng(26).normal(0, .05, 256)
        state = np.zeros(8)
        target = []
        previous = 0.
        for sample in source:
            value = sample
            for j in range(7, -1, -1):
                old = state[j]
                value -= old*k[j]
                if j < 7:
                    state[j+1] = old+k[j]*value
            state[0] = value
            previous = value+.5*previous
            target.append(previous)
        np.testing.assert_allclose(inverse_residual(np.asarray(target), f, np.array([256])), source, atol=1e-12)

    def test_learned_book_uses_original_cycles_and_has_exact_zero_dc(self):
        n = 1024
        t = np.arange(n)
        reference = .2*np.sin(2*np.pi*t/40)+.06*np.sin(4*np.pi*t/40)
        f = np.tile(np.array([40, 1, 0x88, 0x88, 0x88, 0x88], np.uint8), (4, 1))
        d = np.full(4, 256)
        a, groups = learn_waves(reference, f, d)
        b, _ = learn_waves(reference, f, d)
        np.testing.assert_array_equal(a, b)
        np.testing.assert_array_equal(a.sum(axis=1), np.zeros(4))
        self.assertLessEqual(int(np.max(abs(a))), 31)
        self.assertEqual(groups.shape, (4,))


if __name__ == '__main__':
    unittest.main()

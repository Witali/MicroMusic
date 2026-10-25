"""Ordered LSFs can still produce an unstable saturated Q12 LPC filter."""
from pathlib import Path
import struct
import sys
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from batch_decoder import BatchSession
from lpx4 import encode, decode
from q0_model import coefficient_trace
from refine_lsf_pcm16 import optimize, patch_bits, read_scanned_fields
from wav_lpc import pack_frames


class SpectralStabilityTests(unittest.TestCase):
    def test_refinement_rejects_an_exact_but_unstable_target(self):
        # A single legal LSF change crosses the fixed-point stability boundary.
        vector = [47, 74, 126, 180, 436, 640, 754, 886, 924, 943]
        count = 4800
        q = np.resize(np.array([0, 1, -1, 2, 0, -2]), count)
        doc = {'raw': struct.pack('<4sBBHIHHHH', b'L3AV', 1, 3, 8000, count, 0, 0, 160, 80),
               'frames': pack_frames([vector] * (count // 160)),
               'blocks': [{'bits': 3, 'scale': 160, 'q': q[i:i + 80].tolist()} for i in range(0, count, 80)]}
        baseline = encode(doc, fast=True)[0]
        field = read_scanned_fields(baseline)[0][0]
        target = patch_bits(baseline, field.bit_offset, field.width, 15)

        def radius(blob):
            co = coefficient_trace(decode(blob)[0], count)[0]
            return float(max(abs(np.roots(np.r_[1., co / 4096]))))

        self.assertLess(radius(baseline), 1.)
        self.assertGreater(radius(target), 1.)
        with BatchSession('batch') as decoder:
            ref = decoder.decode_one_s16(target, count)
            result, pcm, report = optimize(baseline, ref, decoder, step_sizes=(32,),
                max_trials=1, min_stoi_delta=0.)
        self.assertLess(radius(result), 1.)
        self.assertEqual(result, baseline)


if __name__ == '__main__':
    unittest.main()

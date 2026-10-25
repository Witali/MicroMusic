from pathlib import Path
import itertools
import struct
import sys
import unittest
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT/'tools'))
from lpx4 import encode, decode
from q0_model import table
from wav_lpc import pack_frames
from batch_decoder import BatchSession
from lossless_repack import optimal_scales, optimize_scales, scale_cost, layout


def fixture(blocks):
    n = sum(len(b['q']) for b in blocks)
    raw = struct.pack('<4sBBHIHHHH', b'L3AV', 1, 3, 8000, n, 13926, 1000, 160, 80)
    frames = pack_frames([[round(1023*i/11) for i in range(1,11)]]*((n+159)//160))
    return encode({'raw':raw, 'frames':frames, 'blocks':blocks}, fast=True)[0]


class ScaleRepackTests(unittest.TestCase):
    def test_global_dp_matches_brute_force_with_zero_bridge(self):
        steps = table('scale_table.inc')
        # Two distant singleton steps separated by a free zero-q scale.
        blocks = [{'bits':3,'scale':s,'q':[0 if i == 1 else 1]}
                  for i,s in enumerate((90,255,128))]
        path, bits = optimal_scales(blocks)
        allowed = [np.flatnonzero(steps == steps[90]), range(256), np.flatnonzero(steps == steps[128])]
        expected = min(sum(int(scale_cost(a,b)) for a,b in zip((0,)+p,p))
                       for p in itertools.product(*allowed))
        self.assertEqual(bits,expected)
        self.assertEqual(sum(int(scale_cost(a,b)) for a,b in zip([0]+path,path)),expected)

    def test_aliases_and_zero_excitation_preserve_native_partial_tail(self):
        blocks = [{'bits':3,'scale':s,'q':([1,-1,0,1]*20)[:n] if s != 255 else [0]*n}
                  for s,n in ((0,80),(90,80),(255,80),(128,7))]
        blob = fixture(blocks)
        with BatchSession('batch') as dec:
            result, report = optimize_scales(blob,dec)
            np.testing.assert_array_equal(dec.decode_one(blob,247),dec.decode_one(result,247))
        self.assertLessEqual(len(result),len(blob));self.assertTrue(report['native_pcm16_verified'])
        self.assertEqual(decode(blob)[2],decode(result)[2])
        self.assertEqual(optimize_scales(result)[0],result)
        self.assertEqual(len(layout(result)[3]),4)


if __name__ == '__main__': unittest.main()

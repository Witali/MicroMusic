from pathlib import Path
import sys
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from wav_to_lpx4 import segment_ranges


class SegmentBoundaryTests(unittest.TestCase):
    def test_quiet_cuts_preserve_every_sample_and_segment_limits(self):
        pcm=np.full(8001,10000,np.int16);pcm[2840:2920]=0
        ranges=segment_ranges(pcm,3200,640)
        self.assertEqual(ranges[0],(0,2880))
        self.assertEqual(ranges[-1][1],len(pcm))
        self.assertTrue(all(0<b-a<=3200 for a,b in ranges))
        self.assertTrue(all(b==c for (_,b),(c,_) in zip(ranges,ranges[1:])))
        np.testing.assert_array_equal(np.concatenate([pcm[a:b] for a,b in ranges]),pcm)
        self.assertEqual(segment_ranges(pcm,3200),[(0,3200),(3200,6400),(6400,8001)])
        for span in (-160,1,3200):
            with self.assertRaises(ValueError):segment_ranges(pcm,3200,span)


if __name__=='__main__':unittest.main()

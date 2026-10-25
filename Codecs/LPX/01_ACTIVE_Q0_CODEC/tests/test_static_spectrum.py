"""Cached anchors must survive static/changed spectra and partial final frames."""
from pathlib import Path
import struct
import sys
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from batch_decoder import BatchSession
from lpx4 import encode
from wav_lpc import pack_frames
from q0_model import decode_pcm16
from optimize_q0 import cost_probe,probe


class StaticSpectrumTests(unittest.TestCase):
    def test_static_changed_static_and_restart_match_uncached_model(self):
        a=[round(1023*i/11) for i in range(1,11)]
        b=[v+3 for v in a]
        with BatchSession('batch') as decoder:
            for count in (1,159,160,161,800,817):
                vectors=([a,a,b,b,a,a]*2)[:(count+159)//160]
                q=np.resize(np.array([0,1,-1,2,-2]),count)
                doc={'raw':struct.pack('<4sBBHIHHHH',b'L3AV',1,3,8000,count,13926,3000,160,80),
                     'sampleCount':count,'frames':pack_frames(vectors),
                     'blocks':[{'bits':3,'scale':180,'q':q[i:i+80].tolist()} for i in range(0,count,80)]}
                blob=encode(doc,fast=True)[0]
                np.testing.assert_array_equal(decoder.decode_one_s16(blob,count),decode_pcm16(blob))
                if count==800:self.assertEqual(probe(blob,cost_probe())['lsf_converts'],5)


if __name__=='__main__':unittest.main()

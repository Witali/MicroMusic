import sys
from pathlib import Path
import unittest

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import probe
import speech_compact as compact
from batch_decoder import BatchSession
from refine_speech_trajectory import refine


class ProbeAdapterTests(unittest.TestCase):
    def test_dictionary_export_deduplicates_without_losing_rollback(self):
        self.assertEqual(probe.endpoint_streams(b'control',b'selected',None,
            [dict(stream=b'control'),dict(stream=bytearray(b'other'))]),
            [b'control',b'selected',b'other'])
        with self.assertRaises(ValueError):
            probe.endpoint_streams(b'control',None,None,[dict(pcm=[])])

    def test_actual_refiner_exports_supported_dictionary_frontier(self):
        spectra=[[2,5,8,11,14,17,20,23,26,29]]*3
        stream=compact.pack(641,4,spectra,[(0,40,0)]*6,[(0,8)]*48)[0]
        target=compact.decode_model(stream)
        np.testing.assert_array_equal(target,np.zeros(641,np.int16))
        frontier=[]
        with BatchSession('batch',speech=True,speech_compact=True) as receiver:
            selected,pcm,report,raw=refine(target,stream,receiver,len(stream),
                frame_limit=1,window_frames=2,beam_width=1,spectral_candidates=0,
                excitation_candidates=0,max_evaluations=1,capacity_policy='none',
                allocation_evaluations=0,frontier=frontier)
        self.assertTrue(frontier)
        self.assertTrue(all(isinstance(point,dict) for point in frontier))
        self.assertEqual(probe.endpoint_streams(stream,selected,raw,frontier),[stream])
        np.testing.assert_array_equal(pcm,target)
        self.assertLessEqual(report['full_synthesis_evaluations'],1)


if __name__=='__main__':
    unittest.main()

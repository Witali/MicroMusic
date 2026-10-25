from pathlib import Path
import sys
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from batch_decoder import BatchSession
from test_beam_excitation import raw_fixture
from optimize_q0 import optimize
from beam_excitation_pcm16 import optimize as beam


class UnifiedOptimizerTests(unittest.TestCase):
    def test_global_phase_can_save_bytes_without_changing_perfect_pcm(self):
        blob=raw_fixture(samples=4800)
        with BatchSession('batch') as decoder:
            ref=decoder.decode_one_s16(blob,4800)
            out,pcm,report=optimize(blob,ref,decoder,rounds=1,lsf_trials=0,beam_trials=0,
                header_trials=0,global_candidates=8,global_states=32)
        self.assertLess(len(out),len(blob));np.testing.assert_array_equal(pcm,ref)
        self.assertTrue(report['stages'][0]['accepted'])

    def test_timing_rejection_rolls_back_global_phase(self):
        blob=raw_fixture(samples=4800);calls=[]
        def reject(data):calls.append(data);return {'accepted':False}
        with BatchSession('batch') as decoder:
            ref=decoder.decode_one_s16(blob,4800)
            out,pcm,r=optimize(blob,ref,decoder,rounds=1,lsf_trials=0,beam_trials=0,
                header_trials=0,global_candidates=5,timing_gate=reject)
        self.assertEqual(out,blob);self.assertTrue(calls)

    def test_beam_layout_cache_preserves_search_and_budget(self):
        blob=raw_fixture(samples=160)
        ref=np.resize(np.array([0,200,-100,70,-30],np.int16),160)
        with BatchSession('batch') as decoder:
            a,p,r=beam(blob,ref,decoder,kind='music',max_trials=200,cache_layout=False)
            b,q,s=beam(blob,ref,decoder,kind='music',max_trials=200,cache_layout=True)
        self.assertEqual(a,b);np.testing.assert_array_equal(p,q)
        self.assertEqual(r['trials'],s['trials']);self.assertEqual(s['token_scans'],2);self.assertGreater(r['token_scans'],2)


if __name__=='__main__':unittest.main()

"""Contracts specific to the larger automatic excitation dictionary."""
import importlib.util
from pathlib import Path
import random
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pulsebook8_search_tests_subject',ROOT/'tools/probe-q3-pulsebook8.py')
probe=importlib.util.module_from_spec(spec);sys.modules[spec.name]=probe;spec.loader.exec_module(probe)


class Pulsebook8SearchTests(unittest.TestCase):
    def state(self):
        f=np.array([[40,m*16+3,0x88,0x88,0x88,0x88] for m in range(8)],np.uint8)
        book=np.zeros((8,16),np.int8);book[:,0]=np.arange(8)
        return probe.search.State(f,np.full(8,128,np.uint16),book,False,1)

    def test_gain_changes_keep_the_upper_selector_bit(self):
        class GainOnly:
            values=iter((70,7))
            def randrange(self,*args):return next(self.values)
            def random(self):return 0.
            def choice(self,values):return 1
        original=self.state();after=probe.mutate(original,GainOnly(),4)
        self.assertEqual(int(after.frames[7,1]),7*16+4)
        np.testing.assert_array_equal(original.frames[:,1],np.arange(8)*16+3)

    def test_random_joint_edits_preserve_integer_fields_duration_and_zero_tails(self):
        rng=random.Random(24108);state=self.state();duration=int(state.durations.sum())
        for _ in range(500):
            candidate=probe.mutate(state,rng,4)
            payload=probe.codec.validate(candidate.frames,candidate.durations,candidate.book,samples=duration)
            frames,durations=probe.codec.unpack_stream(payload)
            np.testing.assert_array_equal(frames,candidate.frames)
            np.testing.assert_array_equal(durations,candidate.durations)
            self.assertFalse(np.any(candidate.book[:,4:]));state=candidate

    def test_forced_extended_selector_bytes_are_counted_before_quality_fitting(self):
        f=np.array([[40,1,0x88,0x88,0x88,0x88]]*16,np.uint8)
        d=np.full(16,256,np.uint16);book=np.zeros((8,16),np.int8)
        budget=len(probe.codec.pack_stream(f,d));f[0,1]|=64
        self.assertEqual(len(probe.codec.pack_stream(f,d)),budget+1)
        reference=.1*np.sin(2*np.pi*220*np.arange(4096)/7500)
        objective=probe.search.Objective(reference,floor_budget=budget,rounded_budget=budget)
        result=objective.evaluate(probe.search.State(f,d,book,False,1))
        self.assertIsNone(result);self.assertEqual(objective.invalid['layout'],1)


if __name__=='__main__':unittest.main()

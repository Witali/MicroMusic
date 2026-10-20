"""Compiler regressions: grid units, explicit ties and repeated-note attacks."""
import importlib.util
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('score',Path(__file__).with_name('score-format.py'))
score=importlib.util.module_from_spec(spec);spec.loader.exec_module(score)

class ScoreFormatTests(unittest.TestCase):
    def pack(self,bar,previous=None):
        return score.pack_bar(bar,['C','C'],{'C4':0,'R':1},{'C':0},2,previous)

    def test_repeated_notes_are_distinct_attacks(self):
        events,_,holds=self.pack('C4:0.5 C4:0.5 C4:1 C4:2')
        self.assertEqual([t>>3 for t in events if t<224],[0,0,0,0])
        self.assertEqual(holds,[])

    def test_crossing_chord_boundary_is_a_hold(self):
        events,_,holds=self.pack('C4:4')
        self.assertEqual([t>>3 for t in events if t<224],[0,2])
        self.assertEqual(len(holds),1)

    def test_only_explicit_ties_continue_across_bars(self):
        _,tie,_=self.pack('C4:4~')
        events,_,_=self.pack('C4:2 R:2',tie)
        self.assertEqual([t>>3 for t in events if t<224],[2,1])
        _,tie,_=self.pack('C4:4')
        events,_,_=self.pack('C4:2 R:2',tie)
        self.assertEqual([t>>3 for t in events if t<224],[0,1])

    def test_rest_never_becomes_a_tie(self):
        events,_,_=self.pack('R:4~')
        self.assertEqual([t>>3 for t in events if t<224],[1,1])

    def test_off_grid_durations_are_rejected(self):
        with self.assertRaises(ValueError):self.pack('C4:0.3 R:3.7')

if __name__=='__main__':unittest.main()

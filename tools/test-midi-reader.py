"""MIDI reduction keeps repeated attacks and explicit cross-bar ties."""
from pathlib import Path
import importlib.util
import unittest

spec=importlib.util.spec_from_file_location('midi',Path(__file__).with_name('midi-reader.py'))
midi=importlib.util.module_from_spec(spec);spec.loader.exec_module(midi)

class MidiTests(unittest.TestCase):
    def test_turkish_march_recognizable_opening_is_retained_from_source_start(self):
        source=Path(__file__).resolve().parents[1]/'ATtiny13A/Music/reference/turkish-march/source-events.json'
        notes,ppqn,bpm=midi.read_midi(source)
        s=midi.create_score(notes,ppqn,bpm,1,1,1,2)
        self.assertEqual(s['patterns']['intro'][0],
            'R:1 F4:0.25 D#4:0.25 D4:0.25 D#4:0.25 F#4:0.25 R:0.75 G#4:0.25 F#4:0.25 F4:0.25 F#4:0.25')

    def test_repeated_same_pitch_note_on_events_remain_distinct(self):
        notes=[(1,0,60,0,480,100),(1,0,60,480,960,100)]
        s=midi.create_score(notes,480,120,1,1,1,None)
        self.assertEqual(s['patterns']['intro'],['C4:1 C4:1 R:2'])

    def test_a_single_held_note_is_tied_across_bar_boundary(self):
        notes=[(1,0,60,0,2400,100)]
        s=midi.create_score(notes,480,120,2,2,1,None)
        self.assertEqual(s['patterns']['intro'],['C4:4~','C4:1 R:3'])

    def test_requested_section_boundary_does_not_break_a_tie(self):
        notes=[(1,0,60,0,2400,100)]
        s=midi.create_score(notes,480,120,2,1,1,None)
        self.assertEqual(s['playlist'],['intro'])
        self.assertEqual(s['patterns']['intro'],['C4:4~','C4:1 R:3'])

    def test_melody_chooses_highest_simultaneous_pitch(self):
        notes=[(1,0,60,0,960,100),(1,0,64,0,960,100)]
        s=midi.create_score(notes,480,120,1,1,1,None)
        self.assertEqual(s['patterns']['intro'],['E4:2 R:2'])

if __name__=='__main__':unittest.main()

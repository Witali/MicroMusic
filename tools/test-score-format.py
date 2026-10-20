"""Compiler regressions: grid units, explicit ties and repeated-note attacks."""
import importlib.util
import re
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

    @staticmethod
    def table(assembly,label,next_label=None):
        section=assembly.split(label+':',1)[1]
        if next_label is not None:section=section.split(next_label+':',1)[0]
        values=[]
        for line in section.splitlines():
            match=re.match(r'\s*\.byte\s+(.*)',line.split('/*',1)[0])
            if match:values.extend(int(n.strip(),0) for n in match[1].split(','))
        return values

    @staticmethod
    def fixture(pairs,notes):
        return dict(title='Independent accompaniment fixture',tempo_bpm=120,
                    patterns={'A':['C4:4']*len(pairs)},playlist=['A'],
                    chord_pairs=pairs,chord_notes=notes)

    def test_explicit_midi_note_and_off_emit_exact_dds_and_zero(self):
        # A4=440 Hz and A5=880 Hz are independent reference pitches. At
        # 18750 Hz, nearest 16-bit DDS steps are 1538 and 3076 respectively.
        data=self.fixture([['keys_only','pluck_only'],['silent','keys_rest_alias']],
                          {'keys_only':[69,None],'pluck_only':[None,'A5'],
                           'silent':[None,None],'keys_rest_alias':['A4','R']})
        assembly,meta=score.to_inc(data)
        self.assertEqual(self.table(assembly,'chord_steps','melody_data'),
                         [0x02,0x06,0x00,0x00,
                          0x00,0x00,0x04,0x0c,
                          0x00,0x00,0x00,0x00])
        self.assertEqual(meta['chords'],['keys_only','pluck_only','silent'])
        self.assertEqual(meta['chord_notes']['keys_only'],(69,None))
        self.assertEqual(meta['chord_notes']['pluck_only'],(None,81))

    def test_pair_dedup_normalizes_names_but_preserves_both_independent_parts(self):
        data=self.fixture([['original','alias'],['same_keys','swapped']],
                          {'original':[69,57],'alias':['A4','A3'],
                           'same_keys':[69,81],'swapped':[57,69]})
        assembly,meta=score.to_inc(data)
        self.assertEqual(meta['chords'],['original','same_keys','swapped'])
        self.assertEqual(meta['chord_table_bytes'],12)
        # A3=220 Hz ->769. Neither the second voice nor its octave/register
        # may be replaced with the legacy root-minus-fifth accompaniment.
        self.assertEqual(self.table(assembly,'chord_steps','melody_data'),
                         [0x02,0x06,0x01,0x03,
                          0x02,0x06,0x04,0x0c,
                          0x01,0x03,0x02,0x06])
        storage=self.table(assembly,'melody_data')
        unpacked=[]
        for offset in self.table(assembly,'playlist','durations'):
            while storage[offset]!=255:
                unpacked.append(storage[offset]);offset+=1
        # Both spelling variants select pair0, while changing only the pluck
        # note selects pair1 and swapping parts selects pair2.
        self.assertEqual(unpacked,[0xe0,5,0xe0,21,0xe1,5,0xe2,21])

if __name__=='__main__':unittest.main()

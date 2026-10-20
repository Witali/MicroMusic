"""Packing is lossless across repeated notes, controls, ties and suffix aliases."""
from pathlib import Path
import importlib.util
import unittest
import random

spec=importlib.util.spec_from_file_location('packer',Path(__file__).with_name('pack-score.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

def expand(result):
    storage=result['storage']
    return b''.join(storage[result['offsets'][name]:storage.index(255,result['offsets'][name])] for name in result['playlist'])

class PackTests(unittest.TestCase):
    def test_small_example_matches_exhaustive_minimum_over_all_partitions(self):
        stream=bytes([0,1])*4
        exhaustive=[]
        for mask in range(1<<(len(stream)-1)):
            cuts=[0]+[i+1 for i in range(len(stream)-1) if mask>>i&1]+[len(stream)]
            chunks=[stream[a:b] for a,b in zip(cuts,cuts[1:])]
            exhaustive.append(p.layout(chunks)['cost'])
        self.assertEqual(p.pack(stream,[stream])['report']['packedBytes'],min(exhaustive))

    def test_discovers_repeated_phrases_without_user_sections(self):
        phrase=bytes([224,0,1,2,225,3,4,5]);source=phrase*12
        packed=p.pack(source,[source])
        self.assertEqual(expand(packed),source)
        self.assertLess(packed['report']['packedBytes'],len(source)//2)

    def test_suffixes_share_one_terminator_and_keep_entry_offsets(self):
        result=p.layout([bytes([224,1,2,3]),bytes([2,3])])
        self.assertEqual(result['storage'],bytes([224,1,2,3,255]))
        self.assertEqual(result['playlist'],[0,2])

    def test_a_first_phrase_can_start_inside_a_later_storage_section(self):
        a=bytes([2,3]);b=bytes([1,2,3]);source=a+b+a+b
        result=p.pack(source,[a,b,a,b]);self.assertEqual(expand(result),source)

    def test_does_not_merge_repeated_attacks_or_change_hold_and_note_off(self):
        source=bytes([0,0,112,242,13,248,224,1])*6
        result=p.pack(source,[source]);self.assertEqual(expand(result),source)

    def test_seeded_random_streams_are_lossless_and_never_larger_than_source(self):
        rng=random.Random(13)
        for _ in range(12):
            phrases=[bytes(rng.choice([0,1,2,3,4,5,6,8,9]) for _ in range(rng.randrange(1,8))) for _ in range(4)]
            chunks=[rng.choice(phrases) for _ in range(16)]
            result=p.pack(b''.join(chunks),chunks)
            self.assertEqual(expand(result),b''.join(chunks))
            self.assertLessEqual(result['report']['packedBytes'],p.layout(chunks)['cost'])

if __name__=='__main__':unittest.main()

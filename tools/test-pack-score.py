"""Packing is lossless across repeated notes, controls, ties and suffix aliases."""
from pathlib import Path
import importlib.util
import unittest
import random
from itertools import permutations

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

    def test_event_storage_may_cross_256_when_all_playlist_starts_fit(self):
        suffix=bytes([1,2]);long=bytes([3])*200+suffix;short=bytes([4])*81
        result=p.layout([short,long,suffix])
        self.assertGreater(len(result['storage']),256)
        self.assertLessEqual(max(result['offsets'].values()),255)
        self.assertEqual(result['storage'],long+bytes([255])+short+bytes([255]))
        self.assertEqual(result['playlist'],[203,0,200])
        self.assertEqual(b''.join(result['storage'][i:result['storage'].index(255,i)]
                                  for i in result['playlist']),short+long+suffix)

    def test_already_addressable_large_storage_is_byte_identical(self):
        suffix=bytes([1,2]);long=bytes([3])*200+suffix;short=bytes([4])*81
        result=p.layout([long,short,suffix])
        self.assertGreater(len(result['storage']),256)
        self.assertEqual(result['storage'],long+bytes([255])+short+bytes([255]))
        self.assertEqual(result['playlist'],[0,203,200])

    def test_entry_at_255_remains_valid_even_when_terminator_is_beyond_255(self):
        long=bytes([1])*254;short=bytes([2]);suffix=bytes([1])
        result=p.layout([long,short,suffix])
        self.assertEqual(result['storage'],long+bytes([255])+short+bytes([255]))
        self.assertEqual(result['playlist'],[0,255,253])
        self.assertEqual(len(result['storage']),257)

    def test_shared_suffix_is_not_an_exclusive_constraint_on_last_root(self):
        suffix=bytes([10,11]);a=bytes([1])*178+suffix;b=bytes([2])*98+suffix;c=bytes([3])*150
        result=p.layout([a,b,c,suffix])
        # The common suffix is assigned inside b before the long a goes last.
        # Treating it as exclusive to a would incorrectly prefer c last and
        # leave an entry at282, though a last brings every start within255.
        self.assertEqual(result['storage'],b+bytes([255])+c+bytes([255])+a+bytes([255]))
        self.assertEqual(result['playlist'],[252,0,101,98])
        self.assertEqual(max(result['offsets'].values()),252)

    def test_overflow_reordering_minimizes_largest_entry_over_all_small_permutations(self):
        shared=bytes([10,11]);exclusive=bytes([12,13,14])
        fixtures=[
            ([bytes([1])*178+shared,bytes([2])*98+shared,bytes([3])*150],[shared]),
            ([bytes([1])*190+exclusive,bytes([2])*95,bytes([3])*70,bytes([4])*61],[exclusive]),
            ([bytes([1])*128+shared,bytes([2])*128+shared,bytes([3])*128+shared],[shared]),
        ]
        for roots,suffixes in fixtures:
            pieces=roots+suffixes
            def largest_entry(order):
                # Independent exhaustive placement oracle, including suffixes
                # that may live inside more than one physical root.
                starts={};position=0
                for root in order:
                    for word in pieces:
                        if word not in starts and root.endswith(word):
                            starts[word]=position+len(root)-len(word)
                    position+=len(root)+1
                return max(starts.values())
            self.assertGreater(largest_entry(roots),255)
            result=p.layout(pieces)
            self.assertEqual(max(result['offsets'].values()),
                             min(largest_entry(order) for order in permutations(roots)))
            self.assertEqual(b''.join(result['storage'][i:result['storage'].index(255,i)]
                                      for i in result['playlist']),b''.join(pieces))

    def test_unavoidable_large_suffix_offset_is_not_truncated_to_one_byte(self):
        suffix=bytes([1,2]);root=bytes([3])*300+suffix
        result=p.layout([root,suffix])
        self.assertEqual(result['offsets'][suffix],300)
        self.assertEqual(result['storage'],root+bytes([255]))

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

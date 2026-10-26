"""Decoder compatibility, bounds and actual Flash cost of UM88 packing."""
from pathlib import Path
import importlib.util
import json
import copy
import random
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('codec_test',ROOT/'tools/universal-music.py')
codec=importlib.util.module_from_spec(spec);spec.loader.exec_module(codec)


def expand(stream,rules):
    out=[]
    for symbol in stream:
        stack=[symbol]
        while stack:
            value=stack.pop()
            if value<256:out.append(value)
            else:
                a,b=rules[value-256];stack.extend((b,a))
    return out


class Codec(unittest.TestCase):
    def test_both_serialized_layouts_preserve_every_retained_score(self):
        for path in (ROOT/'ATtiny88/Music/universal/songs').glob('*/score.json'):
            raw=json.loads(path.read_text(encoding='utf-8'))['commands']
            for encode,format_ in [(codec.pack_fast_grammar,0),(codec.pack_grammar,9)]:
              with self.subTest(score=path.parent.name,format=format_):
                original=raw[:];packed=encode(raw)
                self.assertEqual(raw,original)
                self.assertEqual(codec.unpack_grammar(packed),raw)
                self.assertEqual(packed['format'],format_)
                self.assertLessEqual(packed['depth'],12)
                self.assertEqual(packed['grammarBytes'],len(packed['alphabet'])+len(packed['ruleData'])+len(packed['streamData']))
                if format_==0:
                    self.assertEqual(packed['alphabet'],b'')
                    self.assertEqual(packed['grammarBytes'],codec._cost(packed['stream'],packed['rules']))
                    self.assertLessEqual(len(packed['rules']),512)

    def test_fast_serialization_uses_little_endian_rules_and_short_stream_codes(self):
        packed=codec.pack_fast_grammar([0,1,127,128,255])
        self.assertEqual(packed['ruleData'],b'')
        self.assertEqual(packed['streamData'],bytes([0,1,127,128,128,128,255]))
        fixture=dict(format=0,alphabet=b'',rules=[(0,255),(256,128)],stream=[257,1],
                     ruleData=bytes([0,0,255,0,0,1,128,0]),streamData=bytes([129,1,1]))
        self.assertEqual(codec.unpack_grammar(fixture),[0,255,128,1])

    def test_fast_decoder_rejects_truncation_noncanonical_codes_and_bad_references(self):
        valid=dict(format=0,alphabet=b'',rules=[],stream=[0],ruleData=b'',streamData=b'\0')
        for changes,message in [({'streamData':bytes([128])},'Truncated'),
                                ({'streamData':bytes([128,1])},'Noncanonical'),
                                ({'streamData':bytes([129,0])},'range'),
                                ({'streamData':b'\0\0'},'stream length'),
                                ({'rules':[(0,0)],'ruleData':b'\0\0'},'rule length'),
                                ({'rules':[(256,0)],'ruleData':bytes([0,1,0,0])},'earlier'),
                                ({'alphabet':b'\0'},'dictionary')]:
            bad=copy.deepcopy(valid);bad.update(changes)
            with self.subTest(changes=changes),self.assertRaisesRegex(ValueError,message):codec.unpack_grammar(bad)

    def test_both_decoders_reject_excessive_right_branch_depth(self):
        # A right-heavy tree barely uses pending stack space, so depth must be
        # validated from the dictionary graph rather than that stack alone.
        for format_,count in [(0,256),(9,1)]:
            rules=[(0,0)]+[(0,count+i-1) for i in range(1,13)]
            stream=[count+12]
            fixture=dict(format=format_,alphabet=b'' if format_==0 else b'\0',rules=rules,stream=stream)
            if format_==0:
                fixture.update(ruleData=bytes(byte for pair in rules for symbol in pair for byte in (symbol&255,symbol>>8)),
                               streamData=bytes([128|(stream[0]>>8),stream[0]&255]))
            else:fixture.update(ruleData=codec._pack9(v for pair in rules for v in pair),streamData=codec._pack9(stream))
            with self.subTest(format=format_),self.assertRaisesRegex(ValueError,'depth'):codec.unpack_grammar(fixture)

    def test_retained_songs_never_exceed_the_previous_grammar_cost(self):
        for path in (ROOT/'ATtiny88/Music/universal/songs').glob('*/score.json'):
            raw=json.loads(path.read_text(encoding='utf-8'))['commands']
            old=codec._candidate(raw,512,0);stream,rules,depth=codec.grammar(raw)
            self.assertEqual(expand(stream,rules),raw)
            self.assertLessEqual(codec._cost(stream,rules),codec._cost(old[0],old[1]))
            self.assertLessEqual(depth,12);self.assertLessEqual(len(rules),512)
            for i,pair in enumerate(rules):self.assertTrue(all(x<256+i for x in pair))

    def test_incompressible_high_literals_do_not_grow_due_to_rules(self):
        rng=random.Random(83120)
        for _ in range(40):
            raw=[rng.randrange(256) for _ in range(rng.randrange(1,400))]
            stream,rules,depth=codec.grammar(raw)
            self.assertEqual(expand(stream,rules),raw)
            self.assertLessEqual(codec._cost(stream,rules),sum(1 if x<128 else 2 for x in raw))

    def test_overlap_runs_and_deep_repeats_are_lossless(self):
        for raw in ([143]*3000,[64,0,143,1]*1000,[1,2,3,4,250,251]*400,[]):
            stream,rules,depth=codec.grammar(raw)
            self.assertEqual(expand(stream,rules),raw);self.assertLessEqual(depth,12)

    def test_invalid_symbols_and_rule_limits_fail(self):
        for values,limit in [([256],512),([-1],512),([True],512),([1],513),([1],-1)]:
            with self.assertRaises(ValueError):codec.grammar(values,limit)


if __name__=='__main__':unittest.main()

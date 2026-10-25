"""Decoder compatibility, bounds and actual Flash cost of UM88 packing."""
from pathlib import Path
import importlib.util
import json
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

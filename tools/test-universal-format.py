"""Meaningful UM88 format, clock and lossless grammar checks; no MIDI fixtures."""
import copy
import importlib.util
import json
import random
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('um_builder',ROOT/'tools/build-universal-music.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
codec=builder.codec

class Format(unittest.TestCase):
    def setUp(self):
        self.score=json.loads((ROOT/'ATtiny88/Music/universal/songs/greensleeves/score.json').read_text(encoding='utf-8'))

    def test_every_retained_score_round_trips_and_fits(self):
        for name in builder.NAMES:
            with self.subTest(song=name):
                score=json.loads((ROOT/'ATtiny88/Music/universal/songs'/name/'score.json').read_text(encoding='utf-8'))
                data,report=builder.encode_score(score,8000000)
                self.assertLessEqual(len(data)+3000,8192)
                self.assertEqual(data[:4],b'UM88')
                self.assertLessEqual(report['grammarDepth'],12)
                self.assertEqual(report['controlTicks'],score['controlTicks'])
                self.assertTrue(report['allControlFramesVerified'])

    def test_compact_dictionary_preserves_every_retained_command_byte(self):
        for name in builder.NAMES:
            with self.subTest(song=name):
                score=json.loads((ROOT/'ATtiny88/Music/universal/songs'/name/'score.json').read_text(encoding='utf-8'))
                raw=score['commands'];packed=codec.pack_grammar(raw)
                self.assertEqual(codec.unpack_grammar(packed),raw)
                self.assertEqual(packed['format'],9)
                self.assertLessEqual(packed['depth'],12)
                self.assertLessEqual(len(packed['alphabet'])+len(packed['rules']),512)
                self.assertEqual(packed['grammarBytes'],len(packed['alphabet'])+len(packed['ruleData'])+len(packed['streamData']))
                if name in ('alicia','children'):
                    self.assertLess(packed['grammarBytes'],2400)

    def test_repeated_polyphonic_chord_phrases_use_shared_dictionary_calls(self):
        # Three voices change context, pitch, level and phase together. WAITs
        # preserve the chord rhythm; the next chord and the whole phrase repeat.
        phrase=[64,0,65,1,66,2,72,0,73,4,74,7,143,156,172,80,81,82,12,
                72,2,73,5,74,9,143,156,172,80,81,82,6,88,1,89,2,6]
        raw=phrase*48+[0];packed=codec.pack_grammar(raw);count=len(packed['alphabet'])
        self.assertTrue(packed['rules'])
        self.assertTrue(any(symbol>=count for symbol in packed['stream']))
        self.assertLess(packed['grammarBytes'],len(raw)//2)
        self.assertEqual(codec.unpack_grammar(packed),raw)
        self.assertLessEqual(packed['depth'],12)
        expanded=[bytes([value]) for value in packed['alphabet']]
        for a,b in packed['rules']:expanded.append(expanded[a]+expanded[b])
        self.assertTrue(any(bytes(phrase) in value for value in expanded[count:]),
                        'A dictionary entry must reuse a complete multi-voice phrase, not just individual notes')

    def test_nine_bit_serialization_has_a_fixed_independent_vector(self):
        self.assertEqual(codec._pack9([0,1,255,256,511]),bytes([0,2,252,3,248,31]))

    def test_dense_alphabet_handles_all_bytes_and_deterministic_random_streams(self):
        rng=random.Random(0x554d3838)
        for raw in [list(range(256)),[0],[255]*31,[1,2,1,2]*137,
                    [rng.randrange(256) for _ in range(2048)]]:
            with self.subTest(length=len(raw)):
                first=codec.pack_grammar(raw);second=codec.pack_grammar(raw)
                self.assertEqual(first,second)
                self.assertEqual(codec.unpack_grammar(first),raw)

    def test_serialized_dictionary_rejects_forward_references_and_padding(self):
        packed=codec.pack_grammar([1,2]*32+[0])
        bad=copy.deepcopy(packed)
        bad['ruleData']=codec._pack9([511,511]+[value for pair in packed['rules'][1:] for value in pair])
        with self.assertRaisesRegex(ValueError,'earlier'):codec.unpack_grammar(bad)
        bad=copy.deepcopy(codec.pack_grammar([0]))
        bad['streamData']=bad['streamData'][:-1]+bytes([bad['streamData'][-1]|128])
        with self.assertRaisesRegex(ValueError,'padding'):codec.unpack_grammar(bad)

    def test_frequency_retargets_only_pitch_palette(self):
        a,report=builder.encode_score(self.score,8000000)
        b,_=builder.encode_score(self.score,12000000)
        pointer=int.from_bytes(a[24:26],'little')-builder.BASE
        length=len(self.score['pitches'])*2
        self.assertEqual(a[:pointer],b[:pointer]);self.assertEqual(a[pointer+length:],b[pointer+length:])
        for i,note in enumerate(self.score['pitches']):
            if note is None:continue
            frequency=440*2**((note-69)/12)
            for raw,cpu in [(a,8000000),(b,12000000)]:
                step=int.from_bytes(raw[pointer+i*2:pointer+i*2+2],'little')
                self.assertLessEqual(abs(step*(cpu/1024)/65536-frequency),(cpu/1024)/131072+1e-9)

    def test_bad_commands_and_references_rejected(self):
        for mutation in [lambda s:s.update(voices=9),lambda s:s.update(commands=[64,255,1,0]),
                         lambda s:s.update(commands=[72,255,1,0]),lambda s:s.update(commands=[99,1,0]),
                         lambda s:s.update(commands=[1,0,1]),lambda s:s.update(controlTicks=0)]:
            with self.subTest(mutation=mutation):
                bad=copy.deepcopy(self.score);mutation(bad)
                with self.assertRaises(ValueError):builder.encode_score(bad,8000000)

    def test_nyquist_rejected(self):
        with self.assertRaisesRegex(ValueError,'Nyquist'):builder.encode_score(self.score,100000)

    def test_group_boundaries_are_enforced(self):
        bad=copy.deepcopy(self.score)
        bad.update(voices=2,contexts=[[0,0,32,0],[0,0,0,128]],commands=[65,1,1,0],controlTicks=1)
        with self.assertRaisesRegex(ValueError,'raw group'):builder.encode_score(bad,8000000)
        bad['contexts']=[[0,0,32,0],[0,0,32,160]]
        builder.encode_score(bad,8000000)

    def test_group_gain_decomposition_exhaustive(self):
        for q in range(-64,64):
            for level in range(16):
                self.assertEqual((q>>3)*level+((q&7)*level>>3),q*level//8)

    def test_legacy_stereo_piano_balance_exhaustive(self):
        for flags in (0,1,2,5,8,9,10,13):
            _,gain,_=builder.context_settings({'name':'lumiere-stereo','poly':False,'frames':[{'voices':[{}]*5}]},(1,flags,0,0))
            for level in range(16):
                effective=level
                if gain&128:effective>>=1
                if gain&16:effective>>=1
                for q in range(-8,8):
                    expected=q*(level//(4 if flags&1 else 2))//2
                    self.assertEqual(q*effective//2,expected)

if __name__=='__main__':unittest.main()

"""Meaningful UM88 format, clock and lossless grammar checks; no MIDI fixtures."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('um_builder',ROOT/'tools/build-universal-music.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

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

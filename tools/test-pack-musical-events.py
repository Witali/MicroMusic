"""Independently verify every original note, then exercise the bounded codec."""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import hashlib
import importlib.util
import json
import random
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'ATtiny13A/Music/reference/cancion-del-mariachi/source-events.json'
spec = importlib.util.spec_from_file_location('note_packer',Path(__file__).with_name('pack-musical-events.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def original_notes(document, first=0, last=None):
    # Separate implementation: find the matching later Off by occurrence number,
    # never call the packer's chord extraction or note-record normalization.
    result = []
    for track in document['tracks']:
        starts, ends = defaultdict(list), defaultdict(list)
        for order,e in enumerate(track['events']):
            if e['type'] not in ('noteOn','noteOff'):
                continue
            key = (e['channel'],e['note'])
            target = starts if e['type']=='noteOn' and e['velocity'] else ends
            target[key].append((order,e))
        ordered = []
        for (channel,pitch),ons in starts.items():
            assert len(ons)==len(ends[channel,pitch])
            for (on_order,on),(off_order,off) in zip(ons,ends[channel,pitch]):
                assert off_order>on_order
                if on['tick']>=first and (last is None or on['tick']<last):
                    ordered.append((on_order,(track['index'],channel,on['tick']-first,
                                              off['tick']-first,pitch,on['velocity'],off['velocity'])))
        result.extend(note for _,note in sorted(ordered))
    return result


class NotePackingTests(unittest.TestCase):
    def test_all_retained_artifacts_match_every_original_note_and_part(self):
        document = json.loads(SOURCE.read_text(encoding='utf-8'))
        for file,first,last,count,size,peak in [
                ('excerpt',58,121,1027,349,7),
                ('full-no-intro',58,None,4166,890,8),
                ('whole-source',0,None,4237,1030,8)]:
            with self.subTest(file=file):
                result = p.build(SOURCE,first,last)
                saved = json.loads((SOURCE.parent/'lossless'/f'{file}.json').read_text(encoding='utf-8'))
                self.assertEqual(result,saved,'Retained packet is reproducible')
                decoded,ppqn = p.unpack(result['packedData'])
                expected = original_notes(document,first*480,None if last is None else last*480)
                self.assertEqual(p.records(decoded),expected)
                self.assertEqual((ppqn,len(expected),result['packedBytes'],result['peakPolyphony']),
                                 (480,count,size,peak))
                self.assertEqual([part['program'] for part in decoded],[24,24])
                self.assertEqual([part['channel'] for part in decoded],[2,0])
                normalized = json.dumps(expected,separators=(',',':')).encode()
                self.assertEqual(result['decodedNotesSha256'],hashlib.sha256(normalized).hexdigest())
                self.assertTrue(all(s['grammarDepth']<=8 for s in result['parts']))

    def test_repetition_rests_velocities_and_pitch_order_round_trip(self):
        rng = random.Random(20261024)
        for case in range(35):
            parts = []
            for index in range(rng.randrange(1,5)):
                groups,end = [],rng.randrange(30)
                shapes = [rng.sample(range(36,85),rng.randrange(1,8)) for _ in range(5)]
                for _ in range(120):
                    on = end+rng.choice([0,0,0,8,16])
                    end = on+rng.choice([8,16,24,48])
                    groups.append(dict(on=on,off=end,velocity=rng.choice([80,96]),pitches=rng.choice(shapes)))
                parts.append(dict(index=index*3,channel=index,program=24,offVelocity=64,groups=groups))
            raw,_ = p.pack(parts,480)
            decoded,ppqn = p.unpack(raw)
            self.assertEqual((decoded,ppqn),(parts,480),case)
        # Explicit repeated same-pitch attacks remain separate; no tied-note merge.
        part = dict(index=0,channel=2,program=24,offVelocity=64,
                    groups=[dict(on=i*8,off=(i+1)*8,velocity=80,pitches=[64,59,55,52,47,40]) for i in range(600)])
        raw,stats = p.pack([part],480)
        self.assertLess(len(raw),100)
        self.assertGreater(stats[0]['rules'],0)
        self.assertEqual(p.unpack(raw)[0],[part])

    def test_unsupported_overlaps_and_velocities_fail_instead_of_dropping_notes(self):
        document = dict(tracks=[dict(index=0,events=[
            dict(tick=0,type='noteOn',channel=0,note=60,velocity=80),
            dict(tick=5,type='noteOn',channel=0,note=64,velocity=80),
            dict(tick=10,type='noteOff',channel=0,note=60,velocity=64),
            dict(tick=15,type='noteOff',channel=0,note=64,velocity=64)])])
        with self.assertRaisesRegex(ValueError,'non-overlapping'):
            p.extract(document)
        changed = deepcopy(document)
        changed['tracks'][0]['events'][1]['tick']=0
        changed['tracks'][0]['events'][3]['tick']=10
        self.assertEqual(len(p.records(p.extract(changed))),2)
        selected = p.extract(changed,0,5)
        self.assertEqual([n[3] for n in p.records(selected)],[10,10],
                         'Keep complete original Note Offs beyond the selection end')
        changed['tracks'][0]['events'][3]['velocity']=0
        with self.assertRaisesRegex(ValueError,'Note Off velocities'):
            p.extract(changed)
        with self.assertRaisesRegex(ValueError,'Selection'):
            p.extract(document,10,10)

    def test_pack_rejects_timing_loss_and_invalid_notes(self):
        part = dict(index=0,channel=0,program=24,offVelocity=64,
                    groups=[dict(on=0,off=8,velocity=80,pitches=[60])])
        for field,value in [('on',.5),('off',0),('pitches',[128]),('velocity',0)]:
            changed = deepcopy(part)
            changed['groups'][0][field]=value
            with self.assertRaises(ValueError):
                p.pack([changed],480)
        with self.assertRaises(ValueError):
            p.pack([part,part],480)

    def test_truncated_invalid_palette_and_cyclic_grammar_fail(self):
        # One-pitch fixture makes all offsets explicit; these aren't test MIDIs.
        prefix = p.MAGIC+p.vlq(480)+p.vlq(1)+p.vlq(8)+p.vlq(1)
        packet = prefix+bytes([0,2,24,64,1,1,60,1,0,8,1,80,1,0,0,0,1,0])
        self.assertEqual(p.records(p.unpack(packet)[0]),[(0,2,0,8,60,80,64)])
        for end in range(len(packet)):
            with self.assertRaises(ValueError):
                p.unpack(packet[:end])
        for offset,value in [(1,16),(2,128),(3,128),(6,128),(9,0),(11,0),(13,1),(14,128),(17,255)]:
            damaged = bytearray(packet)
            damaged[len(prefix)+offset]=value
            with self.assertRaises(ValueError,msg=str(offset)):
                p.unpack(damaged)
        # Rule 1 refers to itself; even an unused cycle must be rejected.
        with self.assertRaisesRegex(ValueError,'cyclic'):
            p.unpack(packet[:-3]+bytes([1,1,0,1,0]))
        with self.assertRaisesRegex(ValueError,'Trailing'):
            p.unpack(packet+b'\0')


if __name__=='__main__':
    unittest.main()

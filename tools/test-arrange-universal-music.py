"""Musical semantics of the generic mono arranger; fixtures are structured JSON."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('arranger_under_test', ROOT/'tools/arrange-universal-music.py')
arranger = importlib.util.module_from_spec(spec);spec.loader.exec_module(arranger)
builder = arranger.module('arranger_test_builder', 'build-universal-music.py')


def event(tick, kind, **fields):return dict(tick=tick, type=kind, **fields)
def on(tick, note=60, ch=0, velocity=127):return event(tick, 'noteOn', channel=ch, note=note, velocity=velocity)
def off(tick, note=60, ch=0):return event(tick, 'noteOff', channel=ch, note=note, velocity=0)
def cc(tick, number, value, ch=0):return event(tick, 'controlChange', channel=ch, controller=number, value=value)
def document(*tracks):
    return dict(schema='micromusic-midi-events', version=1, ppqn=480,
                source=dict(kind='original test events'),
                tracks=[dict(index=i, events=sorted(rows, key=lambda e:e['tick'])) for i, rows in enumerate(tracks)])
def config(**options):
    return dict(schema='micromusic-um88-arrangement', version=1, name='test-study',
                **dict(dict(instruments={'0':'flute'}), **options))


def commands(score):
    """Read observable control requests, without reproducing arranger decisions."""
    result=[];tick=0;at=0;raw=score['commands']
    while at<len(raw):
        op=raw[at];at+=1
        if op==0:break
        if op<64:tick+=op;continue
        args=[]
        if 64<=op<80 or 88<=op<99:args=[raw[at]];at+=1
        result.append((tick,op,args))
    return result


def rendered_levels(score):
    """Execute the documented control format to observe the generated envelope."""
    level=0;context=0;at=0;waiting=0;result=[]
    for tick in range(score['controlTicks']):
        if tick:
            row=score['envelopes'][score['contexts'][context][0]][level*3:level*3+3]
            if (row[1]|row[2]<<8)&(1<<(tick&15)):level=row[0]
            waiting-=1
        if waiting==0:
            while True:
                op=score['commands'][at];at+=1
                if 0<op<64:waiting=op;break
                if 64<=op<80 or 88<=op<99:
                    value=score['commands'][at];at+=1
                    if op==64:context=value
                elif (op&240)==128:level=op&15
        result.append(level)
    return result


class Arrangement(unittest.TestCase):
    def compile(self, source, settings=None):
        score,report=arranger.arrange(source,settings or config())
        builder.validate_score(score)
        builder.encode_score(score,8000000)
        return score,report

    def test_exact_tempo_map_and_leading_silence(self):
        source=document([event(0,'tempo',microsecondsPerQuarter=500000),
                         event(480,'tempo',microsecondsPerQuarter=1000000),on(960),off(1440)])
        score,report=self.compile(source)
        pitch_tick=next(t for t,op,args in commands(score) if op==72)
        self.assertEqual(pitch_tick,110)  # 0.5 + 1.0 seconds, not constant BPM.
        self.assertAlmostEqual(report['sourceSeconds'],2.5)
        self.assertLessEqual(report['quantization']['maximumErrorSeconds'],256/18750/2)
        self.assertEqual(score['channels'],1)

    def test_pedal_defers_release_but_does_not_drop_noteoff(self):
        score,report=self.compile(document([cc(0,64,127),on(0),off(240),cc(960,64,0)]))
        changes=[t for t,op,args in commands(score) if op==64 and t]
        self.assertEqual(changes,[73])
        self.assertEqual(report['forcedReleases'],[])
        self.assertGreater(report['playbackSeconds'],1)

    def test_zero_volume_mutes_and_expression_recovers_held_voice(self):
        score,_=self.compile(document([on(0),cc(240,7,0),cc(480,7,127),cc(720,11,64),off(960)]))
        levels=[(t,op&15) for t,op,args in commands(score) if op>=128]
        self.assertIn((18,0),levels)
        self.assertIn((37,15),levels)
        self.assertIn((55,8),levels)

    def test_volume_scales_decay_without_restarting_a_muted_piano(self):
        settings=config(instruments={'0':{'instrument':'acoustic-grand-piano','envelope':{'decayMask':0}}})
        baseline,_=self.compile(document([on(0),off(960)]),settings)
        muted,_=self.compile(document([on(0),cc(30,7,0),cc(480,7,127),off(960)]),settings)
        full=rendered_levels(baseline);actual=rendered_levels(muted)
        self.assertEqual(actual[37:],full[37:])
        self.assertTrue(all(x==0 for x in actual[37:]),'Restoring volume cannot reattack an exhausted note')
        quiet,_=self.compile(document([cc(0,7,64),on(0),off(960)]),settings)
        self.assertEqual(rendered_levels(quiet),[arranger.nearest(arranger.Fraction(x*64,127)) for x in full])

    def test_channel_wide_programs_from_other_track_and_program_changes(self):
        source=document([event(0,'programChange',channel=2,program=40),event(480,'programChange',channel=2,program=73)],
                        [on(0,ch=2),off(240,ch=2),on(480,64,ch=2),off(720,64,ch=2)])
        _,report=self.compile(source,config(instruments={}))
        self.assertEqual([a['instrument'] for a in report['instrumentAssignments']],['violin','flute'])

    def test_same_pitch_noteoffs_pair_fifo(self):
        score,_=self.compile(document([on(0),on(100),off(200),off(400)]))
        releases=[(t,op&7) for t,op,args in commands(score) if 64<=op<72 and t in (15,31)]
        self.assertEqual(releases,[(15,0),(31,1)])

    def test_polyphony_overflow_requires_explicit_policy_and_reports_victim(self):
        source=document([on(0,60),on(0,64),off(480,60),off(480,64)])
        with self.assertRaisesRegex(ValueError,'Polyphony'):self.compile(source,config(voices=1))
        score,report=self.compile(source,config(voices=1,overflow='steal-quietest'))
        self.assertEqual(score['voices'],1)
        self.assertEqual(report['voiceSteals'][0]['note'],60)
        self.assertFalse(report['voiceSteals'][0]['releaseTail'])

    def test_release_tail_steal_is_reported(self):
        _,report=self.compile(document([on(0),off(100),on(120,64),off(480,64)]),
                              config(voices=1,overflow='steal-quietest'))
        self.assertTrue(report['voiceSteals'][0]['releaseTail'])

    def test_unknown_program_requires_an_explicit_approximation(self):
        source=document([event(0,'programChange',channel=0,program=41),on(0),off(480)])
        with self.assertRaisesRegex(ValueError,'assign track'):self.compile(source,config(instruments={}))
        _,report=self.compile(source,config(programs={'41':'cello'},instruments={}))
        self.assertEqual(report['instrumentAssignments'][0]['instrument'],'cello')

    def test_pitch_bend_changes_palette_without_retriggering(self):
        score,_=self.compile(document([on(0),event(480,'pitchBend',channel=0,value=12288),off(960)]))
        self.assertEqual(score['pitches'],[None,60,61])
        self.assertEqual([t for t,op,args in commands(score) if op==80],[0])

    def test_track_filter_preserves_silence_and_reports_omitted_notes(self):
        score,report=self.compile(document([on(0),off(480)],[on(960,72),off(1440,72)]),
                                  config(tracks=[1],instruments={'1':'flute'}))
        self.assertEqual(next(t for t,op,args in commands(score) if op==72),73)
        self.assertEqual(report['omittedNotes'][0]['reason'],'unselected track')

    def test_mono_pan_and_pressure_are_reported_as_unsupported(self):
        _,report=self.compile(document([on(0),cc(10,10,0),event(20,'channelPressure',channel=0,pressure=50),off(480)]))
        self.assertEqual(report['ignoredEvents'],{'CC10':1,'channelPressure':1})

    def test_sub_tick_note_collapse_is_visible(self):
        _,report=self.compile(document([on(0),off(1),event(480,'endOfTrack')]))
        self.assertEqual(len(report['collapsedNotes']),1)

    def test_percussion_only_and_replacements(self):
        score,report=self.compile(document([on(0,35,9),on(10,42,9),off(480,42,9)]),config(percussion=True))
        self.assertEqual(score['voices'],1)
        self.assertEqual(report['drumAttacks'],2)
        self.assertEqual(report['percussionReplacements'][0]['oldNote'],35)
        self.assertEqual(score['pitches'],[None])

    def test_all_sound_off_is_immediate_even_with_pedal(self):
        score,_=self.compile(document([cc(0,64,127),on(0),cc(240,120,0),off(480)]))
        self.assertIn((18,128,[]),commands(score))

    def test_wave_bank_limit_and_transient_assignment(self):
        source=document([on(0),off(480)],[on(0,64,1),off(480,64,1)],[on(0,48,2),off(480,48,2)])
        _,report=self.compile(source,config(instruments={'0':'acoustic-grand-piano','1':'flute','2':'fretless-bass'}))
        self.assertEqual(report['wavePairs'],3)
        extra=copy.deepcopy(source);extra['tracks'].append(dict(index=3,events=[on(0,60,3),off(480,60,3)]))
        with self.assertRaisesRegex(ValueError,'64-byte'):
            self.compile(extra,config(instruments={'0':'acoustic-grand-piano','1':'flute','2':'fretless-bass','3':'violin'}))

    def test_inputs_are_not_modified(self):
        source=document([on(0),off(480)]);settings=config();saved=copy.deepcopy((source,settings))
        self.compile(source,settings)
        self.assertEqual((source,settings),saved)

    def test_unknown_settings_and_out_of_range_messages_fail(self):
        source=document([on(0),off(480)])
        for settings in (config(stereo=True),config(voices=9),config(gainShift=8)):
            with self.assertRaises(ValueError):self.compile(source,settings)
        source['tracks'][0]['events'][0]['velocity']=128
        with self.assertRaisesRegex(ValueError,'velocity'):self.compile(source)


if __name__=='__main__':unittest.main()

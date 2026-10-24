"""Q4 fixed-point equivalence, packet boundaries and selective precision."""
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q4_voice_patterns as codec
from q3_pulsebook import multiply as old_multiply


class VoicePatternTests(unittest.TestCase):
    def test_pattern_records_preserve_every_coefficient_and_all_waveforms(self):
        patterns=np.asarray([[((row*8+column)%31)-15 for column in range(8)]
            for row in range(32)],np.int8)
        modes=np.arange(32,dtype=np.uint8)%8
        raw=codec.pack_patterns(patterns,modes)
        self.assertEqual(len(raw),256)
        got,gm=codec.unpack_patterns(raw)
        np.testing.assert_array_equal(got,patterns);np.testing.assert_array_equal(gm,modes)
        for invalid in (np.full((1,8),-16,np.int8),np.full((1,8),16,np.uint64),
                np.full((1,8),np.iinfo(np.int64).min,np.int64),np.zeros((1,8),float)):
            with self.assertRaises(ValueError):codec.pack_patterns(invalid,np.array([0]))
        with self.assertRaises(ValueError):codec.unpack_patterns(bytes(8)) # K1 = -1 is forbidden
        with self.assertRaises(ValueError):codec.unpack_patterns(bytes(9))

    def frames(self):
        values=[(p,i%16,i,d,h) for i,p,d,h in itertools.product(range(32),
            (0,1,63,64,126),(64,128,192,256),(0,1)) if p or not h]
        return tuple(np.asarray(a,np.uint16 if n==3 else np.uint8)
            for n,a in enumerate(zip(*values)))

    def test_stream_boundaries_keep_all_32_indices_and_half_periods(self):
        values=self.frames();payload=codec.pack_stream(*values)
        for before,after in zip(values,codec.unpack_stream(payload)):
            np.testing.assert_array_equal(before,after)
        for invalid in (b'\xff',b'\xc8\x01\x01',b'\xc0',b'\xc0\x01',
                b'\xc0\x7f\x00',b'\xc0\x80\x00',b''):
            with self.assertRaises(ValueError):codec.unpack_stream(invalid)

    def test_doubled_q3_is_exact_for_every_signed_sample_and_coefficient(self):
        for sample,coefficient in itertools.product(range(-128,128),range(-7,8)):
            self.assertEqual(codec.multiply(sample,coefficient*2),old_multiply(sample,coefficient,False))

    def test_whole_selected_phrase_keeps_phase_states_and_frozen_pcm(self):
        model=json.loads((ROOT/'ATtiny13A/Sound/research/q3-adaptive/half-pitch/model.json').read_text())
        f=np.asarray(model['frames'],np.uint8);d=np.asarray(model['durations'],np.uint16)
        h=np.asarray(model['fractions'],np.uint8);waves=np.asarray(model['pulsebook'],np.int8)
        patterns=np.empty((len(f),8),np.int8)
        patterns[:,::2]=((f[:,2:]&15).astype(np.int16)-8)*2
        patterns[:,1::2]=((f[:,2:]>>4).astype(np.int16)-8)*2
        spec=importlib.util.spec_from_file_location('voice_pattern_phase_reference',ROOT/'tools/build-q3-half-pitch-probe.py')
        phase=importlib.util.module_from_spec(spec);spec.loader.exec_module(phase)
        out=ROOT/'build/q4-voice-pattern-tests';out.mkdir(parents=True,exist_ok=True)
        expected,counts=phase.oracle(out)(f,d,waves,h)
        actual,got=codec.render(f[:,0],f[:,1]&15,np.arange(len(f),dtype=np.uint16),
            d,h,patterns,f[:,1]>>4,waves)
        np.testing.assert_array_equal(actual,expected);np.testing.assert_array_equal(got,counts)
        self.assertEqual(hashlib.sha256(actual.tobytes()).hexdigest(),
            '6e7460448faded3cb63371b9c4729b4c81ad69c6560eef40cef7973179efa836')

    def selective(self):
        p=np.resize(np.array([0,1,63,64,126],np.uint8),17)
        h=(np.arange(17)%2).astype(np.uint8);h[p==0]=0
        controls=(p,(np.arange(17)%16).astype(np.uint8),(np.arange(17)%16).astype(np.uint8),
            np.resize(np.array([64,128,192,256],np.uint16),17),h)
        heads=np.asarray([[-15+n%4,15-n%4] for n in range(17)],np.int8)
        tails=np.asarray([[2*((r+c)%15-7) for c in range(6)] for r in range(16)],np.int8)
        modes=np.arange(16,dtype=np.uint8)%8;waves=np.zeros((8,16),np.int8)
        return (*controls,heads,tails,modes,waves)

    def test_selective_plane_preserves_signed_odd_coefficients_and_padding(self):
        values=self.selective();table,plane,stream=codec.pack_selective(*values)
        self.assertEqual((len(table),len(plane)),(64,5))
        decoded=codec.unpack_selective(table,plane,stream)
        for before,after in zip(values[:-1],decoded):np.testing.assert_array_equal(before,after)
        for bad_plane in (plane[:-1],plane+b'\0',plane[:-1]+bytes([plane[-1]|0x80])):
            with self.assertRaises(ValueError):codec.unpack_selective(table,bad_plane,stream)
        for bad_stream in (b'',stream[:-1]):
            with self.assertRaises(ValueError):codec.unpack_selective(table,plane,bad_stream)
        for bad_table in (b'',table[:-1],table[:3]+b'\x08'+table[4:]):
            with self.assertRaises(ValueError):codec.unpack_selective(bad_table,plane,stream)
        changed=list(values);changed[6]=values[6].copy();changed[6][0,0]=-16
        with self.assertRaises(ValueError):codec.pack_selective(*changed)

    def test_retained_studies_reproduce_exact_pcm_sizes_and_quality(self):
        import soundfile as sf
        from pystoi import stoi
        from spectrogram_objective import SpectrogramObjective
        from hq4_speech_search import deterministic_estoi
        research=ROOT/'ATtiny13A/Sound/research/q4-voice-patterns'
        load=lambda name:json.loads((research/name).read_text(encoding='utf-8'))
        reference_path=ROOT/'web-player/audio/originals/vinni.wav'
        reference,sr=sf.read(reference_path,dtype='float64');self.assertEqual(sr,7500)
        full=load('full/report.json')
        self.assertEqual(hashlib.sha256(reference_path.read_bytes()).hexdigest(),full['reference_sha256'])
        variants=[('full/per-frame-control.json',full['q4_per_frame_control']),
            ('full/16/model.json',full['results']['16']['final']),
            ('full/32/model.json',full['results']['32']['final']),
            ('selective/model.json',load('selective/report.json')['final'])]
        for name,score in variants:
            model=load(name);array=lambda key:np.asarray(model[key],np.int16)
            p,g,d,h=map(array,('pitches','gains','durations','fractions'))
            waves=array('pulsebook');modes=array('modes')
            if model['schema']=='q4-per-frame-control-v1':
                patterns=array('coefficients');indices=np.arange(len(p),dtype=np.uint16)
                self.assertFalse(model['serialized_format'])
            elif model['schema']==codec.SCHEMA:
                patterns=array('patterns');indices=array('indices')
                table=codec.pack_patterns(patterns,modes);stream=codec.pack_stream(p,g,indices,d,h)
                result=full['results'][str(len(patterns))]
                self.assertEqual(len(table)+len(stream),result['data_bytes'])
            else:
                indices=array('indices');heads=array('heads');tails=array('tails')
                parts=codec.pack_selective(p,g,indices,d,h,heads,tails,modes,waves)
                result=load('selective/report.json')
                self.assertEqual(tuple(map(len,parts)),tuple(result[k] for k in ('table_bytes','precision_bytes','stream_bytes')))
                patterns=np.column_stack((heads,tails[indices]));modes=modes[indices]
                indices=np.arange(len(p),dtype=np.uint16)
            pcm,counts=codec.render(p,g,indices,d,h,patterns,modes,waves)
            signed=pcm.astype(np.int16)-128
            valid=not np.any(counts) and abs(signed).max()<=115 and not np.any(abs(np.diff(signed))>=48)
            self.assertEqual(bool(valid),score['guards_pass'],name)
            if not valid:continue
            self.assertEqual(hashlib.sha256(pcm.tobytes()).hexdigest(),score['pcm_sha256'],name)
            audio=signed.astype(float)/128
            self.assertAlmostEqual(float(stoi(reference,audio,7500)),score['stoi'],places=11)
            self.assertAlmostEqual(deterministic_estoi(reference,audio,7500),score['estoi'],places=11)
            self.assertAlmostEqual(SpectrogramObjective(reference).evaluate(audio)['spectrogram_loss'],
                score['spectrogram_loss'],places=11)


if __name__=='__main__':unittest.main()

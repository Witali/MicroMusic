"""Reproduce retained voice-form, pitch and precision measurements."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pattern_results_audit',ROOT/'tools/analyze-q4-stoi-bands.py')
audit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=audit;spec.loader.exec_module(audit)
from spectrogram_objective import SpectrogramObjective
from hq4_speech_search import deterministic_estoi
from pystoi import stoi


class PatternResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=ROOT/'ATtiny13A/Sound/research/q4-pattern-precision'
        cls.manifest=cls.read(cls.base/'manifest.json')
        cls.x,cls.sr=sf.read(ROOT/cls.manifest['reference'],dtype='float64')
        cls.spectral=SpectrogramObjective(cls.x)

    @staticmethod
    def read(path):return json.loads(path.read_text(encoding='utf-8'))

    def assert_output(self,path,score):
        pcm,counts,_,_=audit.teacher_pcm(path);raw=pcm.astype(np.int16)-128
        self.assertEqual(len(pcm),22272);self.assertFalse(np.any(counts))
        self.assertLessEqual(int(abs(raw).max()),115);self.assertLess(int(abs(np.diff(raw)).max()),48)
        self.assertEqual(hashlib.sha256(pcm.tobytes()).hexdigest(),score['pcm_sha256'])
        y=raw.astype(float)/128
        self.assertAlmostEqual(float(stoi(self.x,y,self.sr)),score['stoi'],places=11)
        self.assertAlmostEqual(self.spectral.evaluate(y)['spectrogram_loss'],score['spectrogram_loss'],places=11)
        self.assertAlmostEqual(float(y.mean()),score['raw_mean'],places=13)
        if 'estoi' in score:self.assertAlmostEqual(deterministic_estoi(self.x,y,self.sr),score['estoi'],places=11)

    def test_complete_endpoints_and_best_intelligibility_reproduce_their_metrics(self):
        for name,run in self.manifest['runs'].items():
            with self.subTest(name=name):
                self.assert_output(self.base/run['model'],run['final'])
                if 'best_model' in run:
                    report=self.read(self.base/run['report'])
                    self.assert_output(self.base/run['best_model'],report['best_intelligibility'])
                if 'band_audit' in run:
                    from stoi_diagnostics import band_scores
                    pcm,_,_,_=audit.teacher_pcm(self.base/run['model'])
                    result=band_scores(self.x,(pcm.astype(float)-128)/128,self.sr)
                    saved=self.read(self.base/run['band_audit'])['teacher']
                    for a,b in zip(result['bands'],saved['bands']):
                        self.assertAlmostEqual(a['correlation'],b['correlation'],places=11)
        spec=importlib.util.spec_from_file_location('pattern_ablation_render',ROOT/'tools/fit-q4-product233.py')
        renderer=importlib.util.module_from_spec(spec);sys.modules[spec.name]=renderer;spec.loader.exec_module(renderer)
        for run in self.read(self.base/'phase-ablation.json').values():
            model=self.read(self.base/run['model'])
            self.assertEqual(hashlib.sha256((self.base/run['model']).read_bytes()).hexdigest(),run['model_sha256'])
            for case in run['cases']:
                state=renderer.from_model(dict(model,attack_flags=case['attack_flags'],hold_flags=case['hold_flags']))
                pcm,counts=renderer.render(state,model['state_bits'],model['nearest'])
                self.assertFalse(np.any(counts));self.assertEqual(hashlib.sha256(pcm.tobytes()).hexdigest(),case['score']['pcm_sha256'])
                y=(pcm.astype(float)-128)/128
                self.assertAlmostEqual(float(stoi(self.x,y,self.sr)),case['score']['stoi'],places=11)
                self.assertAlmostEqual(self.spectral.evaluate(y)['spectrogram_loss'],case['score']['spectrogram_loss'],places=11)

    def test_pruning_reports_lossy_merges_and_exact_physical_compaction(self):
        root=self.base/'product/form-prune';report=self.read(root/'report.json')
        for count in (1,4,6):
            record=next(r for r in report['records'] if r['forms']==count)
            self.assert_output(root/str(count)/'model.json',record['score'])
            model=self.read(root/str(count)/'model.json');self.assertEqual(model['maximum_forms'],count)
            self.assertLessEqual(max(row[2] for row in model['root']),count-1)
        full=next(r for r in report['records'] if r['forms']==6)
        self.assertEqual(full['score']['pcm_sha256'],self.manifest['runs']['product/phase-fit']['final']['pcm_sha256'])
        self.assertEqual(next(r for r in report['records'] if r['forms']==4)['waveform_bytes'],32)
        self.assertFalse(report['avr_implemented'])

    def test_serialized_counts_and_artifact_hashes_exclude_decoder_claims(self):
        import q4_product233 as product
        import q4_sparse_stream as sparse
        for path,expected in self.manifest['artifact_sha256'].items():
            self.assertEqual(hashlib.sha256((self.base/path).read_bytes()).hexdigest(),expected,path)
        self.assertFalse(self.manifest['achieved']);self.assertFalse(self.manifest['avr_implemented'])
        self.assertEqual(hashlib.sha256((ROOT/self.manifest['reference']).read_bytes()).hexdigest(),self.manifest['reference_sha256'])
        for name,run in self.manifest['runs'].items():
            model=self.read(self.base/run['model'])
            if name.startswith('mixed/'):
                self.assertFalse(model['serialized_format']);continue
            n=lambda key:np.asarray(model[key],np.int16)
            if name.startswith('product/'):
                phase=model['schema']==product.PHASE_SCHEMA
                args=tuple(n(key) for key in ('root','middle','tail'))
                if phase:args+=tuple(n(key) for key in ('attack_flags','hold_flags'))
                table=product.pack_tables(*args)
                values=tuple(n(key) for key in ('pitches','local_gains','durations','indices','halves'))
                payload=product.pack_frames(*values)
                for a,b in zip(values,product.unpack_frames(payload)):np.testing.assert_array_equal(a,b)
                self.assertEqual(len(table),run['serialized_data']['table_bytes']);data=table+payload
            else:
                values=tuple(n(key) for key in ('pitches','gains_q1','durations','coefficients','modes','quarters'))
                payload=sparse.pack(*values,pitch_bits=2)
                for a,b in zip(values,sparse.unpack(payload,pitch_bits=2)):np.testing.assert_array_equal(a,b)
                data=payload
            self.assertEqual(len(payload),run['serialized_data']['stream_bytes'])
            self.assertEqual(hashlib.sha256(data).hexdigest(),run['serialized_data']['sha256'])


if __name__=='__main__':unittest.main()

"""Reproduce complete pulse/phase studies without claiming a firmware fit."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pulse_result_fit',ROOT/'tools/fit-mixed-lattice.py')
fit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fit;spec.loader.exec_module(fit)


class PulseResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=ROOT/'ATtiny13A/Sound/research/q4-pulse-shapes'
        cls.manifest=json.loads((cls.base/'manifest.json').read_text(encoding='utf-8'))
        cls.x,cls.sr=sf.read(ROOT/cls.manifest['reference'],dtype='float64');cls.spectral=fit.base.SpectrogramObjective(cls.x)

    def assert_score(self,state,bits,state_bits,mode,score,limit):
        pcm,counts=fit.render(state,bits,state_bits,mode);raw=pcm.astype(np.int16)-128;y=raw.astype(float)/128
        self.assertEqual(len(pcm),22272);self.assertFalse(np.any(counts));self.assertLessEqual(int(abs(raw).max()),115)
        self.assertLessEqual(int(abs(np.diff(raw)).max()),limit)
        self.assertEqual(hashlib.sha256(pcm.tobytes()).hexdigest(),score['pcm_sha256'])
        self.assertAlmostEqual(float(fit.base.stoi(self.x,y,self.sr)),score['stoi'],places=11)
        self.assertAlmostEqual(fit.base.deterministic_estoi(self.x,y,self.sr),score['estoi'],places=11)
        self.assertAlmostEqual(self.spectral.evaluate(y)['spectrogram_loss'],score['spectrogram_loss'],places=11)
        self.assertAlmostEqual(float(y.mean()),score['raw_mean'],places=13)

    def test_final_and_best_models_match_all_retained_audio_measurements(self):
        for name,entry in self.manifest['runs'].items():
            with self.subTest(name=name):
                state,bits,state_bits,mode,_,_,meta=fit.load(self.base/entry['model'])
                self.assert_score(state,bits,state_bits,mode,entry['final'],meta.get('step_limit',47))
                if 'best_model' in entry:
                    report=json.loads((self.base/entry['report']).read_text())
                    state,bits,state_bits,mode,_,_,meta=fit.load(self.base/entry['best_model'])
                    self.assert_score(state,bits,state_bits,mode,report['best_intelligibility'],meta.get('step_limit',47))
        for name,entry in self.manifest['forward_proposals'].items():
            with self.subTest(forward=name):
                report=json.loads((self.base/entry['report']).read_text())
                if 'model' in entry:loaded=fit.load(self.base/entry['model'])
                else:loaded=fit.load(self.base/entry['seed_model'],pulse_length=entry['pulse_length'],wave_fraction_bits=entry['wave_fraction_bits'])
                self.assert_score(*loaded[:4],entry['final'],report.get('step_limit',47))

    def test_source_hashes_and_waveform_capacity_do_not_imply_a_total_flash_fit(self):
        for path,expected in self.manifest['artifact_sha256'].items():
            self.assertEqual(hashlib.sha256((self.base/path).read_bytes()).hexdigest(),expected,path)
        self.assertFalse(self.manifest['achieved']);self.assertFalse(self.manifest['full_player_implemented'])
        self.assertEqual(hashlib.sha256((ROOT/self.manifest['reference']).read_bytes()).hexdigest(),self.manifest['reference_sha256'])
        self.assertEqual(self.manifest['runs']['control16']['final']['pcm_sha256'],self.manifest['runs']['wide32']['final']['pcm_sha256'])
        self.assertGreater(self.manifest['runs']['wide32-zero']['nonzero_tail_taps'],0)
        for name,entry in self.manifest['runs'].items():
            state,*_=fit.load(self.base/entry['model']);active=np.unique(state.modes[(state.pitches>0)&(state.gains_q1>0)])
            expected=(len(active)*state.waves_q1.shape[1]*(state.wave_fraction_bits+3)+7)//8
            self.assertEqual(entry['packed_waveform_bytes'],expected)
            self.assertFalse(entry['serialized_format']);self.assertEqual(entry['waveforms_fit_eeprom'],expected<=64)


if __name__=='__main__':unittest.main()

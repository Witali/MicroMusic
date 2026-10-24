"""Re-render retained studies and verify their data counts and measured scores."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import numpy as np
import soundfile as sf
from pystoi import stoi

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q4_phase_wave as codec
import q4_sparse_stream as stream
from spectrogram_objective import SpectrogramObjective
from hq4_speech_search import deterministic_estoi
from stoi_diagnostics import band_scores

spec=importlib.util.spec_from_file_location('q4_lattice_results_api',ROOT/'tools/refine-q4-lattice.py')
fit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fit;spec.loader.exec_module(fit)


class LatticeResultTests(unittest.TestCase):
    def setUp(self):
        self.base=ROOT/'ATtiny13A/Sound/research/q4-lattice'
        self.x,self.sr=sf.read(ROOT/'web-player/audio/originals/vinni.wav',dtype='float64')

    def read(self,name):return json.loads((self.base/name).read_text(encoding='utf-8'))

    def assert_score(self,pcm,counts,score):
        self.assertFalse(np.any(counts));self.assertEqual(len(pcm),len(self.x))
        self.assertEqual(hashlib.sha256(pcm.tobytes()).hexdigest(),score['pcm_sha256'])
        y=(pcm.astype(float)-128)/128
        self.assertAlmostEqual(float(stoi(self.x,y,self.sr)),score['stoi'],places=11)
        self.assertAlmostEqual(deterministic_estoi(self.x,y,self.sr),score['estoi'],places=11)
        self.assertAlmostEqual(SpectrogramObjective(self.x).evaluate(y)['spectrogram_loss'],score['spectrogram_loss'],places=11)

    def test_retained_byte_word_and_warm_start_have_exact_metrics_and_sizes(self):
        sizes=self.read('sizes.json')
        for name in ('byte','word'):
            meta=self.read(name+'/model.json');state=fit.load(self.base/name/'model.json');fit.validate(state)
            pcm,counts=fit.render(state,meta['state_bits'],meta['nearest'])
            self.assert_score(pcm,counts,self.read(name+'/report.json')['final'])
            values=(state.pitches,state.gains_q1,state.durations,state.coefficients,state.modes,state.halves)
            payload=stream.pack(*values)
            self.assertEqual(len(payload),sizes[name]['stream_bytes'])
            self.assertEqual(hashlib.sha256(payload).hexdigest(),sizes[name]['serialized_sha256'])
            for expected,actual in zip(values,stream.unpack(payload)):np.testing.assert_array_equal(expected,actual)
            if name=='word':
                result=band_scores(self.x,(pcm.astype(float)-128)/128,self.sr)
                for expected,actual in zip(self.read('band-audit.json')['teacher']['bands'],result['bands']):
                    self.assertAlmostEqual(expected['correlation'],actual['correlation'],places=11)
        state=fit.load(self.base/'byte/best-intelligibility-model.json')
        pcm,counts=fit.render(state,0,False)
        self.assert_score(pcm,counts,self.read('byte/report.json')['best_intelligibility'])

    def test_periodic_wave_and_tilt_controls_match_the_saved_integer_outputs(self):
        m=self.read('phase-wave/model.json');names=('steps','gains','durations','coefficients','modes','waves','offsets','resets')
        values=tuple(np.asarray(m[k],np.int16 if k not in ('steps','offsets') else np.uint16) for k in names)
        pcm,counts=codec.render(*values,state_bits=m['state_bits'],nearest=m['nearest'])
        self.assert_score(pcm,counts,self.read('phase-wave/summary.json')['best'])
        state=fit.load(self.base/'word/model.json');m=self.read('word/model.json')
        rows,excitation=codec.legacy_excitation(state.pitches,state.gains_q1,state.durations,state.modes,state.waves_q1,state.halves)
        excitation[state.pitches[rows]==0]*=2
        for control in self.read('tilt-probe.json')['results']:
            fraction={2.:1,1.:2,.5:3}[control['excitation_scale']]
            pcm,counts=codec.filter_signal(excitation,rows,state.coefficients,tilt_shift=control['tilt_shift'],
                state_bits=m['state_bits'],nearest=m['nearest'],fraction_bits=fraction)
            self.assertEqual(hashlib.sha256(pcm.tobytes()).hexdigest(),control['pcm_sha256'])
            np.testing.assert_array_equal(counts,control['wrap_counts'])


if __name__=='__main__':unittest.main()

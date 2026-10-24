"""Half-pitch stream, exact pulse timing, validation and actual AVR probes."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('half_pitch_contracts',ROOT/'tools/build-q3-half-pitch-probe.py')
phase=importlib.util.module_from_spec(spec);sys.modules[spec.name]=phase;spec.loader.exec_module(phase)


class HalfPitchTests(unittest.TestCase):
    def fixture(self):
        f=np.array([[1,3,0x88,0x88,0x88,0x88]],np.uint8)
        d=np.array([256],np.uint16);b=np.zeros((8,16),np.int8);b[0,0]=1
        return f,d,b

    def test_zero_flags_keep_the_legacy_packet_bytes(self):
        f,d,b,_=phase.base.load_model(ROOT/'ATtiny13A/Sound/research/q3-pulsebook8/ablation/model.json')
        self.assertEqual(phase.pack(f,d,b,np.zeros(len(f),np.uint8)),phase.base.validate(f,d,b))
        self.assertNotEqual(phase.pack(*self.fixture(),np.ones(1,np.uint8)),phase.pack(*self.fixture(),np.zeros(1,np.uint8)))

    def test_half_pitch_alternates_one_and_two_samples_without_flag_overflow(self):
        f,d,b=self.fixture();out=ROOT/'build/q3-half-validation/oracle';out.mkdir(parents=True,exist_ok=True)
        render=phase.oracle(out)
        pcm,counts=render(f,d,b,np.ones(1,np.uint8),0,False)
        peaks=np.flatnonzero(pcm!=128)
        np.testing.assert_array_equal(np.diff(peaks)[:160],np.tile([2,1],80))
        self.assertFalse(np.any(counts))
        old,oc=phase.base.render(f,d,b,0,False)
        got,c=render(f,d,b,np.zeros(1,np.uint8),0,False)
        np.testing.assert_array_equal(got,old);np.testing.assert_array_equal(c,oc)

    def test_fraction_flags_cannot_be_truncated_or_enabled_on_noise(self):
        f,d,b=self.fixture()
        for flags in ([2],[.5],[],[1,0]):
            with self.assertRaises(ValueError):phase.pack(f,d,b,np.asarray(flags))
        f[0,0]=0
        with self.assertRaises(ValueError):phase.pack(f,d,b,np.ones(1,np.uint8))

    def test_actual_machine_code_matches_whole_phrase_and_fast_alternation(self):
        avr=Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node=Path(os.environ.get('NODE',ROOT.parents[1]/'build/toolchains/node-22.22.3/node.exe'))
        if not (avr/'avr-gcc.exe').exists() or not node.exists():self.skipTest('Set AVR_BIN and NODE')
        f,d,b=self.fixture();out=ROOT/'build/q3-half-validation';out.mkdir(parents=True,exist_ok=True)
        path=out/'rapid-model.json';path.write_text(json.dumps(dict(schema='q3-half-pitch-probe-v1',frames=f.tolist(),durations=d.tolist(),pulsebook=b.tolist(),fractions=[1])))
        for name,model,zero in [('rapid',path,False),
                ('vinni',ROOT/'ATtiny13A/Sound/research/q3-adaptive/half-pitch/model.json',False),
                ('vinni-zero',ROOT/'ATtiny13A/Sound/research/q3-adaptive/half-pitch/model.json',True)]:
            report=phase.build(model,out/name,avr,node,zero_flags=zero)
            v=report['verification'];self.assertTrue(v['pass'])
            self.assertEqual(v['engines'],['reference','wasm','wasm-unoptimized'])
            self.assertEqual((v['mismatches'],v['missedSamples'],v['lostOverflows']),(0,0,0))
            self.assertGreater(v['foregroundTiming']['minimumSlackCycles'],0)


if __name__=='__main__':unittest.main()

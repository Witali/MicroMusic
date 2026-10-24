"""Actual word filter on whole phrases, including state and IRQ preservation."""
import importlib.util
import os
from pathlib import Path
import unittest
import tempfile
import hashlib

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('word_q4_filter_contracts',ROOT/'tools/probe-word-q4-filter.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class WordQ4FilterTests(unittest.TestCase):
    def test_uniform_q5_exactly_transports_mixed_precision_without_growing_the_kernel(self):
        avr=Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node=Path(os.environ.get('NODE',ROOT.parents[1]/'build/toolchains/node-22.22.3/node.exe'))
        if not (avr/'avr-gcc.exe').exists() or not node.exists():self.skipTest('Set AVR_BIN and NODE')
        import importlib.util
        import sys
        import numpy as np
        s=importlib.util.spec_from_file_location('uniform_q5_mixed',ROOT/'tools/fit-mixed-lattice.py')
        mixed=importlib.util.module_from_spec(s);sys.modules[s.name]=mixed;s.loader.exec_module(mixed)
        path=ROOT/'ATtiny13A/Sound/research/q4-pulse-shapes/joint-blocks/best-intelligibility-model.json'
        state,bits,state_bits,mode,_,_,meta=mixed.load(path,profile='head5')
        state.coefficients[50,0]+=1  # An odd Q5 value cannot be represented by Q4.
        expected,counts=mixed.render(state,bits,state_bits,mode);self.assertFalse(np.any(counts))
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            model=Path(folder)/'model.json'
            mixed.base.save(model,dict(meta,**state.fields(),coefficient_bits=bits.tolist(),precision_profile='head5'))
            report=probe.run(avr,node,ROOT/'build/word-q4/q5-contracts',6,'unrolled','ram',model,5)
            self.assertEqual(report['coefficientBits'],5);self.assertEqual(report['arithmeticBytes'],228)
            self.assertEqual(report['samples'],66816);self.assertEqual(report['stateChecks'],601344)
            for result in report['results']:
                self.assertEqual(result['pcm_sha256'],hashlib.sha256(expected.tobytes()).hexdigest())
            with self.assertRaises(ValueError):probe.run(avr,node,ROOT/'build/word-q4/q5-rejected',6,'unrolled','ram',model,4)

    def test_predecoded_ram_coefficients_preserve_the_extended_pulse_model(self):
        avr=Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node=Path(os.environ.get('NODE',ROOT.parents[1]/'build/toolchains/node-22.22.3/node.exe'))
        if not (avr/'avr-gcc.exe').exists() or not node.exists():self.skipTest('Set AVR_BIN and NODE')
        model=ROOT/'ATtiny13A/Sound/research/q4-pulse-shapes/q2-continuation-legacy/model.json'
        results=[]
        for memory in ('flash','ram'):
            report=probe.run(avr,node,ROOT/f'build/word-q4/pulse-{memory}-contracts',6,'unrolled',memory,model)
            self.assertEqual(report['arithmeticBytes'],228);self.assertEqual(report['coefficientBytes'],8 if memory=='ram' else 0)
            self.assertEqual(report['samples'],66816);self.assertEqual(report['stateChecks'],601344)
            self.assertEqual(report['irqChecked'],261)
            for r in report['results']:
                self.assertEqual(r['pcm_sha256'],'e1ccb96d96be67a4dcde2cbfb1ebd676d5ba57c99609055fcdad96d2e3b5d748')
                self.assertEqual(r['maximumCycles'],1070 if memory=='ram' else 1078)
            results.append(report)
            if memory=='ram':
                image=ROOT/'build/word-q4/pulse-ram-contracts/fixture.bin'
                self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(),
                    'e733c2b9139c9ccc17ff58888283699b1846021f3a8c0861539906a789ce35e9')
        self.assertEqual(results[0]['results'][0]['maximumCycles']-results[1]['results'][0]['maximumCycles'],8)

    def test_factored_profile_reduces_full_teacher_time_without_changing_states(self):
        avr=Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node=Path(os.environ.get('NODE',ROOT.parents[1]/'build/toolchains/node-22.22.3/node.exe'))
        if not (avr/'avr-gcc.exe').exists() or not node.exists():self.skipTest('Set AVR_BIN and NODE')
        for profile,size,maximum in (('factored',214,1178),('adaptive',216,1182),('unrolled',228,1098)):
            report=probe.run(avr,node,ROOT/f'build/word-q4/{profile}-filter-contracts',6,profile)
            self.assertEqual(report['arithmeticBytes'],size);self.assertEqual(report['samples'],66816)
            self.assertEqual(report['stateChecks'],601344);self.assertEqual(report['irqChecked'],261)
            for r in report['results']:
                self.assertLessEqual(r['maximumCycles'],maximum)
                self.assertEqual(r['pcm_sha256'],'d131729dda4d34f7dc83ee3adb7541abfaf09e18646f5f32cf26d7d11002e695')

    def test_assembled_chain_matches_pcm_and_all_fractional_states(self):
        avr=Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node=Path(os.environ.get('NODE',ROOT.parents[1]/'build/toolchains/node-22.22.3/node.exe'))
        if not (avr/'avr-gcc.exe').exists() or not node.exists():self.skipTest('Set AVR_BIN and NODE')
        for bits,cases in ((4,2),(6,1)):
            report=probe.run(avr,node,ROOT/f'build/word-q4/filter-contracts-{bits}',bits)
            self.assertTrue(report['pass']);self.assertEqual(report['arithmeticBytes'],172 if bits==4 else 180)
            self.assertEqual(report['samples'],66816*cases);self.assertEqual(report['stateChecks'],601344*cases)
            self.assertEqual(report['irqChecked'],261*cases);self.assertFalse(report['fullDecoderImplemented'])
            for r in report['results']:
                self.assertLessEqual(r['maximumCycles'],1212 if bits==4 else 1218)
                self.assertEqual(r['maximumStack'],8)
            self.assertEqual(len({r['maximumCycles'] for r in report['results'] if r['case']=='mixed-q8'}),1 if bits==6 else 0)


if __name__=='__main__':unittest.main()

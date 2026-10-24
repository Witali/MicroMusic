"""Actual word filter on whole phrases, including state and IRQ preservation."""
import importlib.util
import os
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('word_q4_filter_contracts',ROOT/'tools/probe-word-q4-filter.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class WordQ4FilterTests(unittest.TestCase):
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

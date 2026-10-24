"""Exhaustive assembled generated-tail arithmetic and interrupt contracts."""
import importlib.util
import os
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('balanced_tail_probe',ROOT/'tools/probe-balanced-tail.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class BalancedTailTests(unittest.TestCase):
    def test_all_areas_positions_and_comparison_interrupts_in_three_engines(self):
        avr=Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node=Path(os.environ.get('NODE',ROOT.parents[1]/'build/toolchains/node-22.22.3/node.exe'))
        if not (avr/'avr-gcc.exe').exists() or not node.exists():self.skipTest('Set AVR_BIN and NODE')
        report=probe.run(avr,node,ROOT/'build/balanced-tail/contracts')
        self.assertTrue(report['pass']);self.assertEqual(report['kernelBytes'],28)
        self.assertEqual(report['checked'],10800);self.assertEqual(report['irqChecked'],10800)
        for result in report['engines']:
            self.assertEqual((result['minimumCycles'],result['maximumCycles']),(17,17))
            self.assertEqual(result['maximumStack'],6)


if __name__=='__main__':unittest.main()

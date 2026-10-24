"""Real compact word multiplication, register ABI and carry across an IRQ."""
import importlib.util
import json
import os
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('word_q4_mul_contracts',ROOT/'tools/probe-word-q4-mul.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class WordQ4MultiplyTests(unittest.TestCase):
    def test_unrolled_and_adaptive_profiles_preserve_the_same_scalar_contract(self):
        avr=Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node=Path(os.environ.get('NODE',ROOT.parents[1]/'build/toolchains/node-22.22.3/node.exe'))
        if not (avr/'avr-gcc.exe').exists() or not node.exists():self.skipTest('Set AVR_BIN and NODE')
        for profile,size,q4,q5 in (('unrolled',120,58,61),('adaptive',108,70,79)):
            result=probe.run(avr,node,ROOT/f'build/word-q4/{profile}-contracts',quick=True,profile=profile)
            self.assertEqual(result['kernelBytes'],size);self.assertGreaterEqual(result['checked'],76000)
            self.assertEqual(result['irqChecked'],192)
            for engine in result['engines']:
                self.assertLessEqual(engine['q4']['maximum'],q4);self.assertLessEqual(engine['q5']['maximum'],q5)

    def test_factored_profile_keeps_the_same_word_and_irq_contracts(self):
        avr=Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node=Path(os.environ.get('NODE',ROOT.parents[1]/'build/toolchains/node-22.22.3/node.exe'))
        if not (avr/'avr-gcc.exe').exists() or not node.exists():self.skipTest('Set AVR_BIN and NODE')
        result=probe.run(avr,node,ROOT/'build/word-q4/factored-contracts',quick=True,profile='factored')
        self.assertTrue(result['pass']);self.assertEqual(result['kernelBytes'],106)
        original=json.loads((ROOT/'ATtiny13A/Sound/research/word-q4/multiplier-factored.json').read_text())
        self.assertEqual(result['fixture_sha256'],original['fixture_sha256'])
        self.assertGreaterEqual(result['checked'],76000);self.assertEqual(result['irqChecked'],192)
        for engine in result['engines']:
            self.assertLessEqual(engine['q4']['maximum'],65);self.assertLessEqual(engine['q5']['maximum'],72)

    def test_assembled_compact_kernel_matches_three_engines_and_preserves_the_abi(self):
        avr=Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node=Path(os.environ.get('NODE',ROOT.parents[1]/'build/toolchains/node-22.22.3/node.exe'))
        if not (avr/'avr-gcc.exe').exists() or not node.exists():self.skipTest('Set AVR_BIN and NODE')
        result=probe.run(avr,node,ROOT/'build/word-q4/contracts',quick=True)
        self.assertTrue(result['pass']);self.assertLessEqual(result['kernelBytes'],72)
        original=json.loads((ROOT/'ATtiny13A/Sound/research/word-q4/multiplier.json').read_text())
        self.assertEqual(result['fixture_sha256'],original['fixture_sha256'])
        self.assertGreaterEqual(result['checked'],76000);self.assertEqual(result['irqChecked'],192)
        self.assertEqual([e['engine'] for e in result['engines']],['reference','wasm','wasm-unoptimized'])
        for engine in result['engines']:
            self.assertLessEqual(engine['q4']['maximum'],66);self.assertLessEqual(engine['q5']['maximum'],73)


if __name__=='__main__':unittest.main()

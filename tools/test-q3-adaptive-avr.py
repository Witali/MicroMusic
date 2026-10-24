"""Qualify reduced physical dictionaries and both selected decoder variants."""
import importlib.util
from pathlib import Path
import os
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('adaptive_actual_builder',ROOT/'tools/build-q3-pulsebook8.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class AdaptiveAvrTests(unittest.TestCase):
    def test_every_form_count_runs_the_paired_image_in_three_engines(self):
        avr=Path(os.environ.get('AVR_BIN',ROOT.parents[1]/'build/toolchains/avr-7.3.0/bin'))
        node=Path(os.environ.get('NODE',ROOT.parents[1]/'build/toolchains/node-22.22.3/node.exe'))
        if not (avr/'avr-gcc.exe').exists() or not node.exists():self.skipTest('Set AVR_BIN and NODE')
        for count in range(9):
            book=np.zeros((8,16),np.int8);book[:,0]=np.arange(8)-7
            frames=np.array([[40,(i%max(1,count))*16+(1 if count else 0),0x88,0x88,0x88,0x88] for i in range(32)],np.uint8)
            durations=np.tile(np.array([64,128,192,256],np.uint16),8)
            expected=builder.render(frames,durations,book)[0]
            report=builder.build(frames,durations,book,ROOT/f'build/q3-adaptive-validation/forms-{count}',avr,node,adaptive=True)
            self.assertEqual(report['active_forms'],count)
            self.assertEqual(report['phrase_pcm_sha256'],builder.sha(expected.tobytes()))
            v=report['verification']
            self.assertTrue(v['pass']);self.assertEqual(v['engines'],['reference','wasm','wasm-unoptimized'])
            self.assertEqual((v['mismatches'],v['missedSamples'],v['lostOverflows']),(0,0,0))
            self.assertGreater(v['foregroundTiming']['minimumSlackCycles'],0)


if __name__=='__main__':unittest.main()

"""Deterministic coordinates, real capacity expansion and verified-core gates."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('q3_core_data_cycles',ROOT/'tools/probe-q3-pulsebook-cycles.py')
cycles = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cycles
spec.loader.exec_module(cycles)


def state():
    return cycles.search.State(np.array([[40,2,0x88,0x88,0x88,0x88]]*2,np.uint8),
        np.array([128,128],np.uint16),np.zeros((4,16),np.int8),False,1)


class AnalyticObjective:
    def __init__(self,coefficient=False):
        self.coefficient = coefficient

    def evaluate(self,value):
        if self.coefficient:
            error = ((int(value.frames[0,2]) & 15)-8)**2+((int(value.frames[1,2]) & 15)-9)**2
        else:
            error = (int(value.book[0,0])-1)**2+(int(value.book[0,1])+1)**2
        return dict(stoi=.8,spectrogram_loss=.5+.01*error,
            stream_bytes=len(cycles.search.pack_stream(value.frames,value.durations)),target_met=False)

    def energy(self,score):
        return score['spectrogram_loss']+6*(.9-score['stoi'])


class CoreDataCycleTests(unittest.TestCase):
    def test_paired_shape_move_preserves_sum_and_rejects_out_of_range(self):
        original = state()
        changed = cycles.apply_coordinate(original,('table_pair',0,15,1))
        self.assertEqual(int(changed.book[0].sum()),0)
        self.assertEqual(int(changed.book[0,15]),1)
        self.assertEqual(int(changed.book[0,0]),-1)
        self.assertTrue(np.all(original.book == 0))
        original.book[0,0] = 7
        self.assertIsNone(cycles.apply_coordinate(original,('table',0,0,1)))

    def test_coefficient_half_run_and_duration_transfer_preserve_structure(self):
        original = state()
        changed = cycles.apply_coordinate(original,('coefficient_run',1,0,1))
        np.testing.assert_array_equal(changed.frames[:,2],np.array([0x89,0x89]))
        self.assertEqual(len(cycles.search.pack_stream(changed.frames,changed.durations)),
            len(cycles.search.pack_stream(original.frames,original.durations)))
        shifted = cycles.apply_coordinate(original,('boundary',0,0,64))
        np.testing.assert_array_equal(shifted.durations,np.array([192,64]))
        self.assertEqual(int(shifted.durations.sum()),int(original.durations.sum()))
        np.testing.assert_array_equal(shifted.frames,original.frames)

    def test_coordinate_pass_deterministic_bounded_and_improves_known_surface(self):
        one,archive,first = cycles.coordinate_sweep(AnalyticObjective(),state(),20,200)
        two,_,second = cycles.coordinate_sweep(AnalyticObjective(),state(),20,200)
        np.testing.assert_array_equal(one.book,two.book)
        self.assertEqual(first,second)
        self.assertLess(first['final']['spectrogram_loss'],first['initial']['spectrogram_loss'])
        self.assertLessEqual(first['evaluations'],200)
        self.assertGreater(first['accepted'],0)
        self.assertTrue(archive)
        self.assertFalse(first['target_met'])

    def test_new_real_bytes_enable_previously_infeasible_individual_frame_edit(self):
        original = state()
        size = len(cycles.search.pack_stream(original.frames,original.durations))
        old,_,old_report = cycles.coordinate_sweep(AnalyticObjective(True),state(),size,300)
        new,_,new_report = cycles.coordinate_sweep(AnalyticObjective(True),state(),size+2,300)
        self.assertEqual(int(old.frames[1,2]),0x88)
        self.assertEqual(int(new.frames[1,2]),0x89)
        self.assertGreater(old_report['budget_rejections'],0)
        self.assertLess(new_report['final']['spectrogram_loss'],old_report['final']['spectrogram_loss'])
        self.assertEqual(len(cycles.search.pack_stream(new.frames,new.durations)),size+2)

    def test_core_evidence_requires_capacity_consistency_three_engines_and_image_hash(self):
        (ROOT/'build').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
            root = Path(directory)
            image = root/'firmware.bin'
            image.write_bytes(bytes(1024))
            report = dict(schema='micromusic-q3-pulsebook-compact-build-v1',status='verified',
                verification=dict(pass_=True),codeBytes=392,maximumStreamBytes=631,eofBytes=1,
                flashLimitBytes=1024,flashBytes=1024,eepromBytes=64,imageSha256=cycles.search.sha(image),
                productRounding='floor',reflectionZeroMapping='ordinary')
            report['verification'] = {'pass':True,'engines':['reference','wasm','wasm-unoptimized']}
            path = root/'build.json'
            path.write_text(json.dumps(report),encoding='utf-8')
            self.assertEqual(cycles.load_core_profile(path)['stream_budget'],631)
            report['maximumStreamBytes'] = 632
            path.write_text(json.dumps(report),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'inconsistent'):
                cycles.load_core_profile(path)
            report['maximumStreamBytes'] = 631
            report['verification']['engines'] = ['reference']
            path.write_text(json.dumps(report),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'three-engine'):
                cycles.load_core_profile(path)
            report['verification']['engines'] = ['reference','wasm','wasm-unoptimized']
            path.write_text(json.dumps(report),encoding='utf-8')
            image.write_bytes(bytes(1023)+b'\x01')
            with self.assertRaisesRegex(ValueError,'image/hash'):
                cycles.load_core_profile(path)


if __name__ == '__main__':
    unittest.main()

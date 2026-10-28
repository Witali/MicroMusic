import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from batch_decoder import BatchSession
from test_speech_v4 import fixture
from speech_compact import repack, decode_model
from standard_metrics import pwm_duties
import select_speech_budget as budget


class BudgetSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = budget.decoder_source_fingerprint()
        cls.quality_source = budget.quality_source_fingerprint()

    def row(self, identifier, *, flash=1000, size=200, pcm=10000, pwm=12000,
            stoi=.5, pwm_stoi=None, cost=True):
        hashes = ['1' * 64]
        result = {'id': identifier, 'reference_pcm16_sha256': '2' * 64,
            'samples': 320, 'segment_samples': [320], 'profiles': [4],
            'quality_kind': 'speech', 'stream_sha256': hashes, 'stream_bytes': size,
            'output_pcm16_sha256': '3' * 64, 'output_pwm_sha256': '4' * 64,
            'metrics': {'pcm16': {'samples': 320, 'error_energy': pcm, 'stoi': stoi},
                        'pwm8': {'samples': 320, 'error_energy': pwm,
                                 'stoi': stoi if pwm_stoi is None else pwm_stoi}},
            'quality_source_fingerprint': self.quality_source,
            'decoder_source_fingerprint': self.source,
            'firmware': None}
        if cost:
            result['firmware'] = {'schema': budget.COST_SCHEMA,
                'stream_sha256': hashes[:], 'stream_bytes': size,
                'flash_bytes': flash, 'program_flash_bytes': flash-size,
                'image_sha256': '5' * 64, 'source_fingerprint': self.source,
                'build_fingerprint': '6' * 64, 'embedded_streams_exact': True,
                'complete_image': True, 'measurement': 'linked-elf-text-plus-data'}
        result['evaluation_fingerprint'] = budget.evaluation_fingerprint(result)
        return result

    def choose(self, rows, **kwargs):
        return budget.select(rows, 'baseline', 32768, **kwargs)

    def test_transitive_parser_dependency_invalidates_cached_metrics(self):
        baseline = self.row('baseline')
        original = Path.read_bytes
        visited = set()
        def changed(path):
            visited.add(path.name)
            data = original(path)
            return data+b'\n# changed parser dependency\n' if path.name=='compact_format.py' else data
        with patch.object(Path,'read_bytes',changed):
            self.assertNotEqual(budget.quality_source_fingerprint(),self.quality_source)
            with self.assertRaises(ValueError): self.choose([baseline])
        self.assertTrue({'speech_v4.py','wav_lpc.py','lpx4.py','compact_format.py'} <= visited)
        with patch.object(budget,'version',return_value='changed runtime'):
            with self.assertRaises(ValueError): self.choose([baseline])

    def test_exact_integer_caps_and_round_down_full_flash_limit(self):
        self.assertEqual(budget.exact_budget_cap(100, 10), 110)
        self.assertEqual(budget.exact_budget_cap(101, 5), 107)
        self.assertEqual(budget.exact_budget_cap(10**20+1, 10), 110000000000000000002)
        for args in ((True, 10), (0, 10), (10, -.1), (10, True), (10., 10)):
            with self.assertRaises(ValueError): budget.exact_budget_cap(*args)
        result = self.choose([self.row('baseline', flash=1001),
                             self.row('outside', flash=1102, pcm=100, pwm=100)])
        self.assertEqual(result['full_image_growth_limit'], 1101)
        self.assertFalse(result['alternatives'][1]['within_full_image_growth_limit'])

    def test_default_uses_actual_full_flash_and_keeps_growth_for_listening(self):
        rows = [self.row('baseline'),
                self.row('same', size=250, pcm=9000, pwm=11000, stoi=.51),
                self.row('growth', flash=1050, size=180, pcm=7000, pwm=8000, stoi=.53),
                self.row('unknown', size=150, pcm=1, pwm=1, stoi=.9, cost=False)]
        result = self.choose(rows)
        self.assertEqual(result['selected_id'], 'same')
        self.assertEqual(result['growth_listening_ids'], ['growth'])
        self.assertEqual(result['unknown_firmware_ids'], ['unknown'])
        self.assertEqual(result['selected_stream_bytes'], 250)
        self.assertFalse(result['human_listening_confirmation_collected'])
        self.assertFalse(result['timing_admission_inferred_from_flash'])

    def test_four_floors_domination_ties_and_baseline_rollback(self):
        rows = [self.row('baseline'), self.row('pcm-only', pcm=8000, pwm=13000),
                self.row('lower-stoi', pcm=8000, pwm=9000, stoi=.49),
                self.row('same-b', pcm=9000, pwm=10000, stoi=.51),
                self.row('same-a', pcm=9000, pwm=10000, stoi=.51),
                self.row('dominated', flash=1010, pcm=9500, pwm=11000)]
        result = self.choose(rows)
        self.assertEqual(result['selected_id'], 'same-a')
        self.assertIn('same-a', result['alternatives'][-1]['dominated_by'])
        self.assertEqual(self.choose(rows[:3])['selected_id'], 'baseline')
        # Unavailable STOI cannot replace a baseline with a measured score.
        row = self.row('unavailable', pcm=1, pwm=1, stoi=None)
        self.assertEqual(self.choose([rows[0], row])['selected_id'], 'baseline')
        # A no-score baseline still admits numerical improvement.
        self.assertEqual(self.choose([self.row('baseline', stoi=None), row])['selected_id'], 'unavailable')

    def test_explicit_proxy_requires_both_domains_and_preserves_anchor(self):
        rows = [self.row('baseline'), self.row('anchor', pcm=9500, pwm=11500, stoi=.51),
                self.row('growth', flash=1050, pcm=9000, pwm=11000, stoi=.52)]
        self.assertEqual(self.choose(rows)['selected_id'], 'anchor')
        result = self.choose(rows, growth_policy='metric-proxy', min_ser_gain_db=None)
        self.assertEqual(result['selected_id'], 'growth')
        weak = self.row('weak', flash=1060, pcm=8500, pwm=10000, stoi=.5201, pwm_stoi=.5101)
        result = self.choose([*rows[:2], weak], growth_policy='metric-proxy', min_ser_gain_db=None)
        self.assertEqual(result['selected_id'], 'anchor')
        # Perfect output counts as a finite-policy pass, serializes without infinity.
        perfect = self.row('perfect', flash=1050, pcm=0, pwm=0, stoi=.51)
        result = self.choose([*rows[:2], perfect], growth_policy='metric-proxy', min_stoi_gain=None)
        self.assertEqual(result['selected_id'], 'perfect')
        self.assertEqual(result['alternatives'][-1]['metric_proxy_vs_no_growth']['ser_perfect_output'], [True, True])
        for kwargs in ({'growth_policy': 'automatic'}, {'min_stoi_gain': 0},
                       {'min_ser_gain_db': float('nan')}, {'max_flash_growth_percent': True},
                       {'growth_policy': 'metric-proxy', 'min_stoi_gain': None, 'min_ser_gain_db': None}):
            with self.assertRaises(ValueError): self.choose(rows, **kwargs)

    def test_hard_cap_no_feasible_image_and_baseline_cost_required(self):
        rows = [self.row('baseline'), self.row('smaller', flash=950, pcm=9000, pwm=10000)]
        self.assertEqual(budget.select(rows, 'baseline', 960)['selected_id'], 'smaller')
        result = budget.select(rows, 'baseline', 900)
        self.assertIsNone(result['selected_id'])
        self.assertEqual(result['selection_status'], 'no-feasible-candidate')
        with self.assertRaises(ValueError): self.choose([self.row('baseline', cost=False)])

    def test_stale_or_mismatched_cost_evaluation_reference_and_geometry_rejected(self):
        baseline = self.row('baseline')
        patches = [('firmware', 'source_fingerprint', '0'*64),
                   ('firmware', 'build_fingerprint', '0'*64),
                   ('firmware', 'stream_sha256', ['0'*64]),
                   ('firmware', 'program_flash_bytes', 799),
                   ('firmware', 'complete_image', False),
                   ('firmware', 'embedded_streams_exact', False),
                   ('firmware', 'measurement', 'estimated'),
                   ('firmware', 'flash_bytes', True),
                   ('firmware', 'image_sha256', 'invalid')]
        for parent, key, value in patches:
            row = self.row('candidate'); row[parent][key] = value
            with self.subTest(key=key):
                with self.assertRaises(ValueError): self.choose([baseline, row])
        for key, value in (('reference_pcm16_sha256','0'*64), ('segment_samples',[160,160]),
                           ('profiles',[6,6]), ('quality_kind','non-speech-numerical'),
                           ('quality_source_fingerprint','0'*64),
                           ('decoder_source_fingerprint','0'*64)):
            row = self.row('candidate'); row[key] = value
            row['evaluation_fingerprint'] = budget.evaluation_fingerprint(row)
            with self.subTest(key=key):
                with self.assertRaises(ValueError): self.choose([baseline, row])
        for edit in (lambda r: r['metrics']['pcm16'].update(stoi=float('nan')),
                     lambda r: r['metrics']['pwm8'].update(error_energy=-1),
                     lambda r: r['metrics']['pwm8'].pop('stoi'),
                     lambda r: r.update(metrics=[]),
                     lambda r: r.update(evaluation_fingerprint='0'*64)):
            row = self.row('candidate'); edit(row)
            with self.assertRaises(ValueError): self.choose([baseline, row])
        with self.assertRaises(ValueError): self.choose([baseline, copy.deepcopy(baseline)])


class NativeBudgetEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = BatchSession('batch', speech=True, speech_compact=True, compact_only=True)
        cls.decoder = cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.session.__exit__()

    def test_whole_original_reference_chain_metrics_and_firmware_binding(self):
        streams = [repack(fixture(4, 321))[0], repack(fixture(6, 641))[0]]
        ref = np.concatenate([decode_model(blob) for blob in streams])
        with patch.object(budget,'quality_source_fingerprint',wraps=budget.quality_source_fingerprint) as fingerprint:
            rows = budget.evaluate(ref,[{'id':'whole','streams':streams},
                                        {'id':'duplicate','streams':streams}],self.decoder)
            self.assertEqual(fingerprint.call_count,1)
        row = rows[0]
        self.assertEqual(row['segment_samples'], [321, 641])
        self.assertEqual(row['profiles'], [4,6])
        self.assertEqual(row['metrics']['pcm16']['error_energy'], 0)
        self.assertEqual(row['stream_bytes'], sum(map(len, streams)))
        self.assertEqual(row['reference_pcm16_sha256'], row['output_pcm16_sha256'])
        self.assertEqual(row['output_pwm_sha256'], budget._sha(pwm_duties(ref).tobytes()))
        self.assertIsNone(row['metrics']['pcm16']['stoi'])  # clip too short for STOI
        self.assertIsNone(row['firmware'])
        altered = ref.copy(); altered[0] = 100
        second = budget.evaluate(altered, [{'id':'whole', 'streams':streams}], self.decoder)[0]
        self.assertEqual(second['metrics']['pcm16']['error_energy'], (100-int(ref[0]))**2)
        cost = {'schema':budget.COST_SCHEMA, 'stream_sha256':row['stream_sha256'],
            'stream_bytes':row['stream_bytes'], 'flash_bytes':row['stream_bytes']+1000,
            'program_flash_bytes':1000, 'image_sha256':'5'*64,
            'source_fingerprint':row['decoder_source_fingerprint'], 'build_fingerprint':'6'*64,
            'complete_image':True, 'embedded_streams_exact':True,
            'measurement':'linked-elf-text-plus-data'}
        measured = budget.evaluate(ref, [{'id':'whole','streams':streams,'firmware':cost}], self.decoder)[0]
        self.assertEqual(budget.select([measured], 'whole', 32768)['selected_id'], 'whole')
        with self.assertRaises(ValueError):
            budget.evaluate(ref, [{'id':'whole','streams':streams[::-1],'firmware':cost}], self.decoder)

    def test_cli_writes_selected_streams_and_protects_existing_outputs(self):
        import soundfile as sf
        streams = [repack(fixture(4, 321))[0], repack(fixture(6, 641))[0]]
        ref = np.concatenate([decode_model(blob) for blob in streams])
        row = budget.evaluate(ref, [{'id': 'baseline', 'streams': streams}], self.decoder)[0]
        cost = {'schema':budget.COST_SCHEMA, 'stream_sha256':row['stream_sha256'],
            'stream_bytes':row['stream_bytes'], 'flash_bytes':row['stream_bytes']+1000,
            'program_flash_bytes':1000, 'image_sha256':'5'*64,
            'source_fingerprint':row['decoder_source_fingerprint'], 'build_fingerprint':'6'*64,
            'complete_image':True, 'embedded_streams_exact':True,
            'measurement':'linked-elf-text-plus-data'}
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td); reference = folder/'reference.wav'; sf.write(reference,ref,8000,subtype='PCM_16')
            segments = []
            for i, blob in enumerate(streams):
                path = folder/f'input-{i}.l4hy'; path.write_bytes(blob)
                segments.append({'path':path.name,'sha256':budget._sha(blob)})
            manifest = folder/'manifest.json'
            manifest.write_text(json.dumps({'schema':'lpx-v5-budget-input-v1','baseline_id':'baseline',
                'candidates':[{'id':'baseline','segments':segments,'firmware':cost}]}),encoding='utf-8')
            output = folder/'selected'
            args = ['select_speech_budget.py',str(reference),str(manifest),str(output),'--max-flash-bytes','32768']
            with patch('sys.argv',args): budget.main()
            report = json.loads((output/'selection.json').read_text())
            self.assertEqual(report['selected_id'],'baseline')
            self.assertEqual(report['selected_flash_bytes'],sum(map(len,streams))+1000)
            for i,blob in enumerate(streams): self.assertEqual((output/f'segment-{i:03d}.l4hy').read_bytes(),blob)
            np.testing.assert_array_equal(sf.read(output/'decoded.wav',dtype='int16')[0],ref)
            before = (output/'selection.json').read_bytes()
            with patch('sys.argv',args):
                with self.assertRaises(ValueError): budget.main()
            self.assertEqual((output/'selection.json').read_bytes(),before)
            self.assertNotIn(str(folder),before.decode())

    def test_reference_stream_candidate_and_native_validation(self):
        stream = repack(fixture(4, 320))[0]; ref = decode_model(stream)
        for bad in (ref.astype(float), ref[:,None], ref[:-1], ref.astype(np.int64)+65536):
            with self.assertRaises(ValueError): budget.evaluate(bad,[{'id':'one','streams':[stream]}],self.decoder)
        for candidates in ([], [{'id':'one','streams':[]}], [{'id':'one','streams':[123]}],
                           [{'id':'one','streams':[stream[:-1]]}],
                           [{'id':'one','streams':[stream]},{'id':'one','streams':[stream]}]):
            with self.assertRaises(ValueError): budget.evaluate(ref,candidates,self.decoder)
        with patch.object(self.decoder, 'decode_one_s16', return_value=None):
            with self.assertRaises(AssertionError): budget.evaluate(ref,[{'id':'one','streams':[stream]}],self.decoder)
        with patch.object(self.decoder, 'decode_one', return_value=np.zeros(320,dtype=np.uint8)):
            with self.assertRaises(AssertionError): budget.evaluate(ref,[{'id':'one','streams':[stream]}],self.decoder)


if __name__ == '__main__': unittest.main()

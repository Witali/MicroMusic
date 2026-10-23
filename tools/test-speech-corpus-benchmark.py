#!/usr/bin/env python3
"""Corpus selection, raw levels, complete failure accounting and per-clip guards."""
import importlib.util
from pathlib import Path
from copy import deepcopy
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('speech_corpus_benchmark',ROOT/'tools/benchmark-speech-corpus.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def metric(stoi=.8):
    return dict(stoi=stoi,estoi=.7,fine_log_error=.5,envelope_error=.5,unsupported_energy=.1,missing_energy=.2)


def row(ident,language='en',status='complete',stoi=.8):
    return dict(metadata=dict(id=ident,language=language,split='evaluation',condition='natural',
                              reference_sha256='a'*64,samples=15360,sample_rate=7500),
                status=status,metrics=metric(stoi) if status == 'complete' else None)


def report(rows):
    return dict(clips=rows,manifest_sha256='b'*64,subset='short',signal_policy='unchanged level and timing')


class SpeechCorpusBenchmarkTests(unittest.TestCase):
    def test_short_full_selection_and_unknown_id_rejection(self):
        manifest = dict(schema='micromusic-speech-corpus-v1',sample_rate=7500,clips=[
            dict(id='a-full',source_clip_id='a',variant='full'),
            dict(id='a-center2048',source_clip_id='a',variant='center2048')])
        self.assertEqual(benchmark.select_entries(manifest,'short')[0]['id'],'a-center2048')
        self.assertEqual(benchmark.select_entries(manifest,'full',['a'])[0]['id'],'a-full')
        with self.assertRaises(ValueError):
            benchmark.select_entries(manifest,'short',['missing'])

    def test_stream_roundtrip_and_code_eof_alignment_estimate(self):
        frames = np.array([[10,1,136,136,136,136],[11,2,136,136,136,136]],np.uint8)
        durations = np.array([64,128],np.uint16)
        payload,pcm = benchmark.roundtrip(frames,durations)
        self.assertEqual(len(pcm),192)
        self.assertTrue(payload)
        self.assertEqual(benchmark.flash_estimate(617)['estimated_flash_bytes'],1024)
        self.assertEqual(benchmark.flash_estimate(616)['alignment_bytes'],1)
        self.assertFalse(benchmark.flash_estimate(618)['fits_estimated_1024'])
        self.assertFalse(benchmark.flash_estimate(617)['avr_verified'])

    def test_quiet_and_dc_statistics_are_not_normalized(self):
        original = np.array([-.2,.1,.3,-.1])
        quiet = original*10**(-24/20)
        first,second = benchmark.signal_stats(original),benchmark.signal_stats(quiet)
        self.assertAlmostEqual(second['rms']/first['rms'],10**(-24/20))
        self.assertAlmostEqual(second['mean']/first['mean'],10**(-24/20))
        self.assertLess(second['peak'],first['peak'])

    def test_missing_reference_returns_a_recorded_failure_without_absolute_paths(self):
        directory = ROOT/'build/speech-corpus-benchmark-tests'
        directory.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            root = Path(temporary)
            entry = dict(id='missing',reference='clips/missing/reference.wav',reference_sha256='0'*64)
            result = benchmark.benchmark_entry(entry,root,root/'out')
            self.assertEqual(result['status'],'failed')
            self.assertEqual(result['metadata']['id'],'missing')
            self.assertIsNone(result['metrics'])
            self.assertNotIn(str(root),result['error']['message'])
            with self.assertRaises(ValueError):
                benchmark.reference_path(dict(reference='../outside.wav'),root)

    def test_aggregates_retain_failures_and_cannot_pass_regressions(self):
        old = report([row('ru','ru'),row('en','en'),row('failed','en','infeasible')])
        summary = benchmark.aggregate(old['clips'])
        self.assertEqual(summary['language']['en']['recordings'],2)
        self.assertEqual(summary['language']['en']['status_counts']['infeasible'],1)
        new = report([row('ru','ru',stoi=.99),row('en','en',stoi=.79),row('failed','en','infeasible')])
        compared = benchmark.compare_reports(old,new)
        self.assertFalse(compared['candidate_passed'])
        self.assertFalse(compared['recordings']['en']['candidate_passed'])
        self.assertFalse(compared['recordings']['failed']['candidate_passed'])

    def test_changed_reference_cannot_pass_by_improving_metrics(self):
        old = report([row('same')])
        self.assertTrue(benchmark.compare_reports(old,deepcopy(old))['candidate_passed'])
        for field,value in (('reference_sha256','c'*64),('samples',16384),('sample_rate',8000)):
            changed = deepcopy(old)
            changed['clips'][0]['metadata'][field] = value
            changed['clips'][0]['metrics']['stoi'] = .99
            result = benchmark.compare_reports(old,changed)
            self.assertFalse(result['candidate_passed'])
            self.assertFalse(result['reference_invariants_passed'])
        changed = deepcopy(old)
        changed['signal_policy'] = 'normalized input'
        self.assertFalse(benchmark.compare_reports(old,changed)['candidate_passed'])


if __name__ == '__main__':
    unittest.main()

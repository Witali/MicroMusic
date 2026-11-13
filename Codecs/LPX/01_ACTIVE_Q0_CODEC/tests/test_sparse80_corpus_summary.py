"""Anonymous synthetic evidence tests; no codec/media dependencies."""
from __future__ import annotations

from array import array
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import wave

from summarize_sparse80_corpus import (
    StudyContract, StudyError, PRODUCTION, aggregate, ser, summarize,
)


PRIVATE_NAME = 'private-speaker-and-source-name'
PRIVATE_FINGERPRINT = '7abc' * 16


def wav(path, values):
    values = array('h', values)
    if sys.byteorder != 'little':
        values.byteswap()
    raw = values.tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(raw)
    return raw


class Fixture:
    def __init__(self, root, count=1):
        self.root = root
        self.manifest = root / 'corpus' / 'manifest.json'
        self.results = root / 'results'
        self.cases = [self.case(i) for i in range(count)]
        self.write_manifest()

    @staticmethod
    def case(index, *, samples=640, cohort='speech', kind='speech', split='evaluation', segments=None):
        return dict(cohort=cohort, kind=kind, split=split, id=PRIVATE_NAME + str(index),
                    samples=samples, reference_pcm16_sha256=('%064x' % (index + 1)),
                    input_file_sha256=PRIVATE_FINGERPRINT, language=PRIVATE_NAME,
                    reference=PRIVATE_NAME + str(index) + '.wav',
                    source_name=PRIVATE_NAME, private_path='/private/corpus/private-audio.wav',
                    segments=segments or [dict(index=0, start=0, samples=samples)])

    def contract(self):
        return StudyContract(len(self.cases), sum(c['samples'] for c in self.cases),
                             sum(len(c['segments']) for c in self.cases),
                             tuple(Counter(c['kind'] for c in self.cases).items()),
                             tuple(Counter(c['split'] for c in self.cases).items()),
                             tuple(Counter(c['cohort'] for c in self.cases).items()))

    def write_manifest(self):
        self.manifest.parent.mkdir(parents=True, exist_ok=True)
        self.manifest.write_text(json.dumps(dict(schema='lpx-shared-corpus-v1', sample_rate=8000,
            collection_index_sha256=PRIVATE_FINGERPRINT, private_comment=PRIVATE_NAME,
            cases=self.cases)), encoding='utf-8')

    @staticmethod
    def state(reference, output, *, score=1, stoi=.6):
        energy = sum(x*x for x in reference)
        error = sum((a-b)**2 for a, b in zip(reference, output))
        metric = dict(samples=len(reference), reference_energy=float(energy), error_energy=float(error),
                      stoi=stoi, **ser(energy, error))
        voice = dict(frames=1, active_reference_frames=1, reference_period_frames=0,
                     within_tolerance_frames=0, missing_decoded_period_frames=0,
                     decoded_collapsed_active_frames=0, fixed_source_period_error_mean=None,
                     fixed_decoded_period_error_mean=None, relative_spectral_shape_rms_db_mean=1)
        return dict(metrics={d: copy.deepcopy(metric) for d in ('pcm16', 'pwm8')},
                    voice=[copy.deepcopy(voice), copy.deepcopy(voice)],
                    clipped=[0, sum(v in (-32768, 32512) for v in output)], score=score,
                    private_name=PRIVATE_NAME, media_sha256=PRIVATE_FINGERPRINT)

    def complete(self, ordinal=0, *, baseline=0, selected=256, pcm_only=False,
                 before_stoi=.6, after_stoi=.61, before_score=1, after_score=.9, guarded=True):
        case = self.cases[ordinal]
        n = case['samples']
        source = [1024] * n
        old = [baseline] * n
        new = [selected] * n
        folder = self.results / ('%03d' % ordinal)
        folder.mkdir(parents=True, exist_ok=True)
        raw = wav(self.manifest.parent / case['reference'], source)
        case['reference_pcm16_sha256'] = hashlib.sha256(raw).hexdigest()
        # Distinct fixture source bindings for other completed records.
        if any(c is not case and c['reference_pcm16_sha256'] == case['reference_pcm16_sha256'] for c in self.cases):
            source[-1] += ordinal + 1
            raw = wav(self.manifest.parent / case['reference'], source)
            case['reference_pcm16_sha256'] = hashlib.sha256(raw).hexdigest()
        self.write_manifest()
        wav(folder / 'baseline.wav', old)
        wav(folder / 'selected.wav', new)
        a = self.state(source, old, score=before_score, stoi=before_stoi)
        b = self.state(source, new, score=after_score, stoi=after_stoi)
        changed = old != new or pcm_only
        if pcm_only:
            b['metrics']['pcm16']['error_energy'] = a['metrics']['pcm16']['error_energy'] * .999
        total = 0
        for segment in case['segments']:
            d = folder / ('segment-%03d' % segment['index'])
            d.mkdir()
            old_stream = struct.pack('<2sBHHHHH', b'L9', 15, 8000, segment['samples'], 8192, 0, 5) + b'\0' * 5
            new_stream = old_stream[:-1] + bytes([int(changed)])
            (d / 'baseline-v9.lpx').write_bytes(old_stream)
            (d / 'candidate-v9.lpx').write_bytes(new_stream)
            total += len(old_stream)
        result = dict(number=ordinal, cohort=case['cohort'], kind=case['kind'], samples=n,
                      segments=len(case['segments']), changed_segments=len(case['segments']) if changed else 0,
                      whole_record_gate_passed=guarded, bytes=total, selected_bytes=total,
                      changed=changed, baseline=a, selected=b, private=PRIVATE_NAME)
        self.save(ordinal, result)
        return result

    def save(self, ordinal, result):
        (self.results / ('%03d' % ordinal) / 'result-private.json').write_text(json.dumps(result), encoding='utf-8')

    def summary(self, **options):
        return summarize(self.manifest, self.results, _contract=self.contract(), **options)


class CorpusSummaryTests(unittest.TestCase):
    def setUp(self):
        repository = Path(__file__).resolve().parents[4]
        temporary_root = repository / 'build' / 'sparse80-summary-tests'
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temporary_root)
        def cleanup():
            self.assertTrue(Path(self.temp.name).resolve().is_relative_to(temporary_root.resolve()))
            self.temp.cleanup()
        self.addCleanup(cleanup)
        self.fixture = Fixture(Path(self.temp.name))

    def test_real_pwm_changes_and_material_proxy_are_separate_from_pcm_only(self):
        f = self.fixture
        f.complete(selected=0, pcm_only=True, before_stoi=.6, after_stoi=.6)
        report = f.summary()
        self.assertEqual(report['all']['reported_pcm_changed_records'], 1)
        self.assertEqual(report['all']['any_pwm_change_records'], 0)
        self.assertEqual(report['all']['material_pwm_proxy_records'], 0)
        self.assertEqual(report['all']['joint_proxy_one_percent_records'], 1)
        self.assertEqual(report['all']['pwm_changed_joint_proxy_one_percent_records'], 0)
        self.assertFalse(report['records'][0]['pwm_changed'])

    def test_an_actual_small_pwm_change_is_not_automatically_material(self):
        f = self.fixture
        r = f.complete(selected=0, pcm_only=True, before_stoi=.6, after_stoi=.6,
                       before_score=1, after_score=.9999)
        folder = f.results / '000'
        data = [0] * 640
        data[0] = 256
        wav(folder / 'selected.wav', data)
        source = [1024] * 640
        r['selected'] = f.state(source, data, score=.9999, stoi=.6)
        f.save(0, r)
        result = f.summary()
        self.assertEqual(result['all']['any_pwm_change_records'], 1)
        self.assertEqual(result['records'][0]['pwm_changed_samples'], 1)
        self.assertEqual(result['all']['material_pwm_proxy_records'], 0)
        self.assertEqual(result['all']['joint_proxy_one_percent_records'], 0)

    def test_sse_regression_and_false_reported_pwm_metrics_are_rejected(self):
        f = self.fixture
        r = f.complete(selected=-256, after_stoi=.6)
        with self.assertRaisesRegex(StudyError, 'SSE regressed'):
            f.summary()
        r['selected']['metrics']['pwm8']['error_energy'] = r['baseline']['metrics']['pwm8']['error_energy']
        f.save(0, r)
        with self.assertRaisesRegex(StudyError, 'does not match WAV'):
            f.summary()

    def test_stoi_membership_is_fixed_and_missing_assessed_values_fail(self):
        f = self.fixture
        r = f.complete(before_stoi=.6, after_stoi=None)
        with self.assertRaisesRegex(StudyError, 'STOI regressed or became unavailable'):
            f.summary()
        r['baseline']['metrics']['pcm16']['stoi'] = None
        r['baseline']['metrics']['pwm8']['stoi'] = None
        r['selected']['metrics']['pcm16']['stoi'] = .8
        r['selected']['metrics']['pwm8']['stoi'] = .8
        f.save(0, r)
        out = f.summary()['all']['domains']['pwm8']
        self.assertEqual(out['stoi_assessed_records'], 0)
        self.assertEqual(out['newly_available_stoi_records'], 1)
        self.assertIsNone(out['baseline_mean_stoi'])
        self.assertIsNone(out['selected_mean_stoi'])

    def test_period_and_clipping_floors_and_fallback_are_checked(self):
        f = self.fixture
        r = f.complete()
        for side in ('baseline', 'selected'):
            for domain in range(2):
                r[side]['voice'][domain].update(reference_period_frames=1, within_tolerance_frames=1,
                    fixed_source_period_error_mean=.1, fixed_decoded_period_error_mean=.2)
        r['selected']['voice'][0]['fixed_decoded_period_error_mean'] = .3
        f.save(0, r)
        with self.assertRaisesRegex(StudyError, 'Fixed-period error regressed'):
            f.summary()
        r['selected']['voice'][0]['fixed_decoded_period_error_mean'] = .2
        r['selected']['clipped'][0] = 1
        f.save(0, r)
        with self.assertRaisesRegex(StudyError, 'Clipping regressed'):
            f.summary()
        r['selected']['clipped'][0] = 0
        r['whole_record_gate_passed'] = False
        f.save(0, r)
        with self.assertRaisesRegex(StudyError, 'fallback is inconsistent'):
            f.summary()

    def test_actual_stream_bytes_and_exact_pwm_mapping_are_checked(self):
        f = self.fixture
        r = f.complete()
        r['selected_bytes'] += 1
        f.save(0, r)
        with self.assertRaisesRegex(StudyError, 'file bytes differ'):
            f.summary()
        r['selected_bytes'] -= 1
        f.save(0, r)
        wav(f.results / '000' / 'selected.wav', [257] * 640)
        with self.assertRaisesRegex(StudyError, 'not an exact PWM-domain'):
            f.summary()

    def test_data_growth_and_reference_substitution_are_rejected(self):
        f = self.fixture
        r = f.complete()
        selected = f.results / '000' / 'segment-000' / 'candidate-v9.lpx'
        original = selected.read_bytes()
        grown = bytearray(original + b'\0')
        grown[11:13] = struct.pack('<H', len(grown) - 13)
        selected.write_bytes(grown)
        r['selected_bytes'] += 1
        f.save(0, r)
        with self.assertRaisesRegex(StudyError, 'Compressed data grew'):
            f.summary()
        selected.write_bytes(original)
        r['selected_bytes'] -= 1
        f.save(0, r)
        wav(f.manifest.parent / f.cases[0]['reference'], [1025] * 640)
        with self.assertRaisesRegex(StudyError, 'Reference binding differs'):
            f.summary()

    def test_exact_fallback_is_an_unchanged_whole_record(self):
        f = self.fixture
        f.complete(selected=0, before_stoi=.6, after_stoi=.6,
                   before_score=1, after_score=1, guarded=False)
        result = f.summary()
        self.assertEqual(result['all']['fallback_records'], 1)
        self.assertEqual(result['all']['any_pwm_change_records'], 0)
        self.assertEqual(result['records'][0]['baseline'], result['records'][0]['selected'])

    def test_summed_energy_ser_and_fixed_membership_means(self):
        f = Fixture(Path(self.temp.name) / 'two', 2)
        f.complete(0, selected=256, before_stoi=.4, after_stoi=.5)
        f.complete(1, baseline=256, selected=512, before_stoi=None, after_stoi=.9)
        report = f.summary()
        domain = report['all']['domains']['pwm8']
        power = sum(r['baseline']['metrics']['pwm8']['reference_energy'] for r in report['records'])
        error = sum(r['baseline']['metrics']['pwm8']['error_energy'] for r in report['records'])
        self.assertAlmostEqual(domain['baseline_ser']['ser_db'], 10*math.log10(power/error))
        mean_db = sum(r['baseline']['metrics']['pwm8']['ser_db'] for r in report['records']) / 2
        self.assertNotAlmostEqual(domain['baseline_ser']['ser_db'], mean_db)
        self.assertEqual(domain['stoi_assessed_records'], 1)
        self.assertEqual(domain['stoi_unassessed_records'], 1)
        self.assertEqual(domain['baseline_mean_stoi'], .4)
        self.assertEqual(domain['selected_mean_stoi'], .5)

    def test_privacy_allowlist_and_perfect_ser_are_json_safe(self):
        f = self.fixture
        f.complete(selected=1024)
        report = f.summary()
        text = json.dumps(report, allow_nan=False)
        for forbidden in (PRIVATE_NAME, PRIVATE_FINGERPRINT, 'private-person', 'reference_pcm16_sha256',
                          'input_file_sha256', 'collection_index_sha256', str(self.temp.name)):
            self.assertNotIn(forbidden, text)
        self.assertIsNone(report['records'][0]['selected']['metrics']['pwm8']['ser_db'])
        self.assertEqual(report['records'][0]['selected']['metrics']['pwm8']['ser_status'], 'perfect')
        self.assertEqual(report['records'][0]['pwm_ser_gain']['status'], 'improved_to_perfect')
        self.assertEqual(report['all']['material_pwm_proxy_records'], 1)
        self.assertIsNone(report['all']['perceived_quality_majority'])
        self.assertEqual(report['subjective_validation'], 'not_established')
        self.assertEqual(report['policy']['upper_band_specific_floor'], 'not_validated_by_this_exporter')

    def test_partial_production_corpus_cannot_claim_majority(self):
        f = self.fixture
        cases = []
        kinds = ['speech'] * 20 + ['speech'] * 20 + ['music'] * 7 + ['speech'] * 9 + ['music'] * 125
        cohorts = ['speech'] * 20 + ['regression'] * 27 + ['independent'] * 4 + ['phrases'] * 5 + ['music'] * 3 + ['instruments'] * 122
        speech_seen = 0
        for i in range(181):
            n = 100000 + (29 if i == 0 else 0) if i < 125 else 48000
            segments = [dict(index=0, start=0, samples=50000), dict(index=1, start=50000, samples=n-50000)] if i < 125 else None
            if kinds[i] == 'speech':
                split = 'tuning' if speech_seen < 20 else 'evaluation' if speech_seen < 40 else 'additional'
                speech_seen += 1
            else:
                split = 'non_speech'
            cases.append(f.case(i, samples=n, cohort=cohorts[i], kind=kinds[i], split=split, segments=segments))
        f.cases = cases
        f.write_manifest()
        self.assertEqual(f.contract().samples, PRODUCTION.samples)
        self.assertEqual(f.contract().segments, PRODUCTION.segments)
        f.complete(0)
        with self.assertRaisesRegex(StudyError, 'Incomplete study'):
            summarize(f.manifest, f.results)
        out = summarize(f.manifest, f.results, allow_partial=True)
        self.assertFalse(out['complete'])
        self.assertEqual(out['mode'], 'partial_diagnostic')
        self.assertEqual(out['all']['records'], 1)
        self.assertEqual(out['all']['material_pwm_proxy_records'], 1)
        self.assertFalse(out['all']['majority_eligible'])
        self.assertIsNone(out['all']['material_pwm_proxy_majority'])

    def test_majority_is_strict_and_always_a_proxy(self):
        f = Fixture(Path(self.temp.name) / 'two', 2)
        f.complete(0)
        f.complete(1, selected=0, before_score=1, after_score=1, before_stoi=.6, after_stoi=.6)
        rows = f.summary()['records']
        out = aggregate(rows, 2, eligible=True)
        self.assertFalse(out['material_pwm_proxy_majority'])
        self.assertIsNone(out['perceived_quality_majority'])
        self.assertIsNone(aggregate(rows, 3, eligible=False)['material_pwm_proxy_majority'])


if __name__ == '__main__':
    unittest.main()

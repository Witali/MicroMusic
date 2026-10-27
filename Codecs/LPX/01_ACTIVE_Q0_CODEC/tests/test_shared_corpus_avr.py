"""AVR job/oracle accounting and packet controls without a toolchain or simulator."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf

import speech_v4
from speech_compact import decode_model, pack, unpack
from standard_metrics import pwm_duties
from validate_shared_corpus_avr import (canonical, case_jobs, choose_heaviest,
    collect_jobs, repeated_packet_item, safe, sha, _measure, _status)


def stream(samples=640, profile=4, extras=False):
    packets = (samples + 319) // 320
    spectra = [[i + 1 + (p % 2) for i in range(10)] for p in range(packets)]
    params = [(2 + (i % 2), 37, 8) for i in range(packets * 2)]
    if profile == 4:
        pulse = [(int(speech_v4.POSITIONS4[0]), 8), (int(speech_v4.POSITIONS4[-1]), -8)]
    else:
        pulse = [(0, 2), (19, -2)]
    innovations = [(39, 1) if extras and i % 2 else (-1, 0) for i in range(packets * 8)]
    return pack(samples, profile, spectra, params, pulse * (packets * 8),
                extras=innovations, force_extras=extras)[0]


class SharedCorpusAVRTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.inputs = self.base / 'inputs'
        self.selected = self.base / 'selected'
        self.inputs.mkdir()
        self.selected.mkdir()

    def save_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data) + '\n', encoding='utf-8')

    def signature(self, report):
        report.pop('report_sha256', None)
        report['report_sha256'] = sha(canonical(report))
        return report

    def fixture(self, profiles=(4,), samples=640):
        identifier = 'case-fixture'
        reference = np.arange(samples, dtype=np.int16)
        source_hash = sha(reference.astype('<i2').tobytes())
        sf.write(self.inputs / 'original.wav', reference, 8000, subtype='PCM_16')
        case = dict(id=identifier, cohort='speech', samples=samples,
            reference='original.wav', reference_pcm16_sha256=source_hash,
            segments=[dict(index=0, start=0, samples=samples, reference='original.wav', pcm16_sha256=source_hash)])
        self.save_json(self.inputs / 'manifest.json', dict(schema='lpx-shared-corpus-v1', sample_rate=8000, cases=[case]))
        reports = {}
        for profile in profiles:
            folder = self.selected / identifier / str(profile)
            folder.mkdir(parents=True)
            blob = stream(samples, profile)
            pcm = decode_model(blob)
            (folder / 'segment-000.l4hy').write_bytes(blob)
            sf.write(folder / 'segment-000.wav', pcm, 8000, subtype='PCM_16')
            sf.write(folder / 'complete.wav', pcm, 8000, subtype='PCM_16')
            part = dict(index=0, start=0, samples=samples, reference_pcm16_sha256=source_hash,
                stream='segment-000.l4hy', decoded='segment-000.wav', stream_sha256=sha(blob),
                pcm16_sha256=sha(pcm.astype('<i2').tobytes()), pwm_sha256=sha(pwm_duties(pcm).tobytes()),
                cap_bytes=20 + ((samples + 319) // 320) * (20 if profile == 4 else 30), file_bytes=len(blob),
                native_model_pcm16_exact=True, native_compact_only_pcm16_exact=True, native_pwm_exact=True)
            report = self.signature(dict(id=identifier, profile=profile, samples=samples, status='complete',
                reference_pcm16_sha256=source_hash, segments=[part], pcm16_sha256=part['pcm16_sha256'],
                file_bytes=len(blob), payload_bytes=len(blob) - 22))
            self.save_json(folder / 'report.json', report)
            reports[profile] = report
        return case, reports

    def test_complete_jobs_use_saved_pwm_oracle_and_account_missing_profile(self):
        case, reports = self.fixture()
        jobs, accounting = collect_jobs(self.inputs, self.selected)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(accounting['expected_case_profiles'], 2)
        self.assertEqual(accounting['expected_segment_jobs'], 2)
        self.assertEqual(accounting['case_status_counts'], {'complete': 1, 'missing': 1})
        self.assertFalse(accounting['all_selected_cases_complete'])
        blob = jobs[0]['item']['blob']
        np.testing.assert_array_equal(np.frombuffer(jobs[0]['item']['pwm'], dtype='u1'), pwm_duties(decode_model(blob)))
        self.assertIn('selected_report_file_sha256', jobs[0]['context'])

    def test_shards_are_disjoint_and_failed_selection_is_explicit(self):
        case, reports = self.fixture(profiles=(4, 6))
        zero, z = collect_jobs(self.inputs, self.selected, shard=0, shards=2)
        one, o = collect_jobs(self.inputs, self.selected, shard=1, shards=2)
        self.assertEqual({j['item']['profile'] for j in zero}, {4})
        self.assertEqual({j['item']['profile'] for j in one}, {6})
        self.assertEqual(z['expected_shard_segment_jobs'], 1)
        reports[6]['status'] = 'no_fit'
        self.save_json(self.selected / case['id'] / '6/report.json', self.signature(reports[6]))
        jobs, accounting = collect_jobs(self.inputs, self.selected)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(accounting['case_status_counts']['selected_failure'], 1)
        self.assertEqual(accounting['case_profiles'][1]['selected_status'], 'no_fit')

    def test_report_oracle_native_flags_and_cap_tampering_are_rejected(self):
        case, reports = self.fixture()
        original = reports[4]
        for change in ['signature', 'native', 'cap', 'stream', 'sample_count']:
            with self.subTest(change=change):
                report = copy.deepcopy(original)
                if change == 'signature':
                    report['file_bytes'] += 1
                elif change == 'native':
                    report['segments'][0]['native_compact_only_pcm16_exact'] = False
                elif change == 'cap':
                    report['segments'][0]['cap_bytes'] += 1
                elif change == 'stream':
                    report['segments'][0]['stream_sha256'] = '0' * 64
                else:
                    report['segments'][0]['samples'] += 1
                if change != 'signature':
                    self.signature(report)
                self.save_json(self.selected / case['id'] / '4/report.json', report)
                jobs, accounting = collect_jobs(self.inputs, self.selected)
                self.assertFalse(jobs)
                self.assertEqual(accounting['case_status_counts']['invalid'], 1)

    def test_path_escape_and_incomplete_reference_coverage_are_rejected(self):
        case, reports = self.fixture()
        with self.assertRaisesRegex(ValueError, 'escapes'):
            safe(self.inputs, '../elsewhere.wav')
        with self.assertRaisesRegex(ValueError, 'escapes'):
            safe(self.inputs, str(self.base / 'absolute.wav'))
        report = copy.deepcopy(reports[4])
        report['segments'][0]['stream'] = '../../../../../elsewhere.l4hy'
        self.signature(report)
        self.save_json(self.selected / case['id'] / '4/report.json', report)
        jobs, accounting = collect_jobs(self.inputs, self.selected)
        self.assertFalse(jobs)
        self.assertEqual(accounting['case_status_counts']['invalid'], 1)
        case['segments'][0]['start'] = 1
        with self.assertRaisesRegex(ValueError, 'contiguous'):
            case_jobs(self.inputs, self.selected, case, 4, reports[4])

    def test_saved_complete_wave_and_model_are_independently_checked(self):
        case, reports = self.fixture()
        folder = self.selected / case['id'] / '4'
        wrong = np.full(case['samples'], 123, np.int16)
        sf.write(folder / 'segment-000.wav', wrong, 8000, subtype='PCM_16')
        sf.write(folder / 'complete.wav', wrong, 8000, subtype='PCM_16')
        report = copy.deepcopy(reports[4])
        report['pcm16_sha256'] = report['segments'][0]['pcm16_sha256'] = sha(wrong.astype('<i2').tobytes())
        report['segments'][0]['pwm_sha256'] = sha(pwm_duties(wrong).tobytes())
        self.signature(report)
        with self.assertRaisesRegex(ValueError, 'model'):
            case_jobs(self.inputs, self.selected, case, 4, report)

    def test_repeat_tiles_all_fields_to_200_packets_and_discloses_partial_tail(self):
        for profile in (4, 6):
            for n in (17, 321, 640):
                with self.subTest(profile=profile, samples=n):
                    blob = stream(n, profile, extras=True)
                    item = dict(blob=blob, case='case-source', profile=profile)
                    repeated, pcm, metadata = repeated_packet_item(item)
                    source = unpack(blob)
                    target = unpack(repeated['blob'])
                    self.assertEqual(target[:2], (64000, profile))
                    self.assertEqual([len(target[i]) for i in (2, 3, 4, 7)], [200, 400, 3200, 1600])
                    for field, width in [(2, 1), (3, 2), (4, 16), (7, 8)]:
                        for index in (0, 1, 2, 199):
                            source_index = index % len(source[2])
                            self.assertEqual(target[field][index * width:(index + 1) * width],
                                             source[field][source_index * width:(source_index + 1) * width])
                    np.testing.assert_array_equal(pcm[:n], decode_model(blob))
                    self.assertEqual(metadata['source_last_packet_previously_unplayed_samples'], (-n) % 320)
                    self.assertEqual(sha(pwm_duties(pcm).tobytes()), sha(repeated['pwm']))

    def test_repeat_uses_continuous_model_instead_of_restarted_wav_tiles(self):
        blob = pack(320, 6, [[5 + 6 * i for i in range(10)]],
                    [(8, 37, 8)] * 2, [(0, 7), (19, -7)] * 8)[0]
        repeated, pcm, metadata = repeated_packet_item(dict(blob=blob, case='source', profile=6))
        tiled = np.tile(decode_model(blob), 200)
        self.assertFalse(np.array_equal(pcm, tiled))
        np.testing.assert_array_equal(pcm, decode_model(repeated['blob']))
        self.assertIn('continuous', metadata['reset_scope'])

    def test_heaviest_choice_is_per_profile_complete_and_stream_bound(self):
        valid = {f'j{i}': {'item': {'stream_sha256': str(i)}} for i in range(3)}
        rows = {}
        for i, (profile, cycles) in enumerate([(4, 400), (4, 600), (6, 500)]):
            rows[f'j{i}'] = dict(status='complete', context=dict(profile=profile, selected_stream_sha256=str(i)),
                measurement=dict(assembly_enabled=True, extra_irq_cycles=0, mean_decode_wall_cycles=cycles))
        report = dict(schema='lpx-shared-corpus-avr-v1', mode='validate', compact_only=True, images=rows)
        choices, accounting = choose_heaviest([report], valid, True)
        self.assertEqual(choices[4][0], 'j1')
        self.assertEqual(choices[6][0], 'j2')
        self.assertTrue(accounting['all_valid_jobs_measured'])
        report['images']['j1']['context']['selected_stream_sha256'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'stream changed'):
            choose_heaviest([report], valid, True)

    def test_underruns_are_retained_without_failing_matrix(self):
        measurement = dict(underruns=7)
        with patch('validate_shared_corpus_avr.simulate', return_value=measurement), \
             patch('validate_shared_corpus_avr.same_harness'):
            result = _measure({'item': {}, 'context': {'id': 'job'}}, self.base / 'job',
                {}, {}, 'avr-bin', 'runner', 'lib', None, {})
        self.assertEqual(result['status'], 'complete')
        self.assertFalse(result['zero_underruns'])
        summary = _status({'images': {'job': result}})
        self.assertEqual(summary['measured_underruns'], 7)
        self.assertEqual(summary['images_with_underruns'], 1)

    def test_invalid_shard_and_unknown_cohort_are_not_empty_successes(self):
        self.fixture()
        with self.assertRaisesRegex(ValueError, 'shard'):
            collect_jobs(self.inputs, self.selected, shard=1, shards=1)
        with self.assertRaisesRegex(ValueError, 'cohort'):
            collect_jobs(self.inputs, self.selected, cohorts=['unknown'])


if __name__ == '__main__':
    unittest.main()

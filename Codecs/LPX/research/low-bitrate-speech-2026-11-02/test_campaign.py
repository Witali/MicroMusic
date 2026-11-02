"""Campaign storage/aggregation contracts, without native fitting or corpus jobs.

Synthetic receipt fixtures exercise provenance and restart logic only. Actual
codec/native equality remains the separate shared RoundAdmission obligation.
"""
from copy import deepcopy
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import campaign
import campaign_records as storage
import campaign_summary as summary


def metrics(ordinal=0):
    value = dict(samples=32000, reference_energy=100_000_000, error_energy=1_000_000,
                 stoi=.5 if ordinal < 20 else None)
    period = dict(frames=197, reference_period_frames=100, within_tolerance_frames=50)
    return dict(id=0, admissible=True, file_bytes=22, score=1., clipped_samples=0,
                metrics=dict(pcm16=deepcopy(value), pwm8=deepcopy(value)),
                voice=deepcopy(period), pwm_voice=deepcopy(period))


def transitions():
    return [dict(status='PASS', ordinal=index, kbps=kbps, group=summary.EXPECTED_GROUPS[index],
                 before=metrics(index), after=metrics(index), changed=False)
            for index in range(27) for kbps in (2, 3)]


ELIGIBLE = {str(k): list(range(20)) for k in (2, 3)}


class SummaryContracts(unittest.TestCase):
    def test_heldout_ser_and_pwm_coverage_each_have_their_registered_threshold(self):
        for criterion in ('ser', 'coverage'):
            rows = transitions()
            for row in rows:
                if row['ordinal'] in summary.HELDOUT and row['kbps'] == 3:
                    row['after']['score'] = .99
                    row['changed'] = True
                    if criterion == 'ser':
                        row['after']['metrics']['pwm8']['error_energy'] = 900_000
                    else:
                        row['after']['pwm_voice']['within_tolerance_frames'] = 55
            result = summary.summarize(rows, ELIGIBLE, 2)
            self.assertTrue(result['budgets']['3']['clear_numerical_gain'])
            self.assertFalse(result['budgets']['2']['clear_numerical_gain'])
            self.assertEqual(result['consecutive_no_clear'], 0)

    def test_three_completed_rounds_and_a_heldout_gain_reset(self):
        rows = transitions()
        count = 0
        for expected in (1, 2, 3):
            result = summary.summarize(rows, ELIGIBLE, count)
            self.assertEqual(result['consecutive_no_clear'], expected)
            self.assertEqual(result['stop_condition_met'], expected == 3)
            count = expected
        for row in rows:
            if row['ordinal'] in summary.HELDOUT and row['kbps'] == 2:
                row['after']['metrics']['pcm16']['stoi'] = .51
                row['after']['metrics']['pwm8']['stoi'] = .51
                row['after']['score'] = .99
                row['changed'] = True
        result = summary.summarize(rows, ELIGIBLE, 2)
        self.assertTrue(result['clear_numerical_gain'])
        self.assertEqual(result['consecutive_no_clear'], 0)
        self.assertFalse(result['budgets']['3']['clear_numerical_gain'])

    def test_tuning_improvement_and_small_heldout_gains_do_not_reset_counter(self):
        rows = transitions()
        for row in rows:
            if row['ordinal'] in summary.TUNING:
                row['after']['metrics']['pwm8']['stoi'] = .8
            elif row['ordinal'] in summary.HELDOUT:
                row['after']['metrics']['pwm8']['stoi'] = .501
                row['after']['metrics']['pwm8']['error_energy'] = 990_000
                row['after']['pwm_voice']['within_tolerance_frames'] = 51
            row['after']['score'] = .99
            row['changed'] = True
        result = summary.summarize(rows, ELIGIBLE, 1)
        self.assertEqual(result['consecutive_no_clear'], 2)
        self.assertFalse(result['clear_numerical_gain'])
        self.assertEqual(result['budgets']['2']['changed_cases'], 27)

    def test_summed_energy_and_fixed_stoi_membership_and_source_denominator(self):
        a, b = metrics(), metrics()
        a['metrics']['pwm8'].update(reference_energy=100, error_energy=10)
        b['metrics']['pwm8'].update(reference_energy=900, error_energy=10)
        result = summary.aggregate([dict(ordinal=4, metrics=a), dict(ordinal=5, metrics=b)], [4, 5])
        self.assertAlmostEqual(result['aggregate_pwm_ser_db'], 10 * __import__('math').log10(50))
        self.assertEqual(result['period']['pwm_voice']['source_windows'], 200)
        self.assertEqual(result['period']['pwm_voice']['unknown_reference_windows'], 194)
        b['metrics']['pwm8']['stoi'] = None
        with self.assertRaises(ValueError):
            summary.aggregate([dict(ordinal=4, metrics=a), dict(ordinal=5, metrics=b)], [4, 5])
        rows = transitions()
        rows[0]['after']['pwm_voice']['reference_period_frames'] -= 1
        with self.assertRaises(ValueError):
            summary.summarize(rows, ELIGIBLE, 0)

    def test_partial_claimed_running_or_failed_work_is_never_a_quality_round(self):
        with self.assertRaises(ValueError):
            summary.summarize(transitions()[:-1], ELIGIBLE, 0)
        for status in ('CLAIMED', 'RUNNING', 'FAIL', 'INFRA_FAILED'):
            rows = transitions()
            rows[0]['status'] = status
            with self.assertRaises(ValueError):
                summary.summarize(rows, ELIGIBLE, 0)


class StorageContracts(unittest.TestCase):
    def test_source_native_baseline_and_original_bindings_are_rechecked(self):
        with tempfile.TemporaryDirectory(dir=campaign.ROOT / 'build') as temporary:
            directory = Path(temporary)
            files = {name: directory / name for name in ('native', 'native-receipt', 'binding-private.json',
                                                       'receipt', 'report', 'original.wav')}
            for path in files.values():
                path.write_bytes(b'pinned local fixture')
            manifest = dict(sources={}, libraries={'common': dict(path=str(files['native']), sha256=storage.file_digest(files['native']))},
                library_receipt=str(files['native-receipt']), library_receipt_sha256=storage.file_digest(files['native-receipt']),
                baseline=str(directory), baseline_binding_sha256=storage.file_digest(files['binding-private.json']),
                initial=[dict(baseline_receipt=str(files['receipt']), baseline_receipt_sha256=storage.file_digest(files['receipt']),
                              baseline_report=str(files['report']), baseline_report_sha256=storage.file_digest(files['report']))],
                targets=[dict(raw_reference_file=str(files['original.wav']), raw_reference_file_sha256=storage.file_digest(files['original.wav']))])
            with patch.object(campaign, 'source_snapshot', return_value={}):
                campaign.assert_sources(manifest)
                for path in files.values():
                    path.write_bytes(b'changed fixture')
                    with self.assertRaises(ValueError):
                        campaign.assert_sources(manifest)
                    path.write_bytes(b'pinned local fixture')

    def test_immutable_publication_and_interrupted_pending_record(self):
        with tempfile.TemporaryDirectory(dir=campaign.ROOT / 'build') as temporary:
            directory = Path(temporary)
            path = directory / 'record-private.json'
            storage.immutable(path, {'generation': 1})
            original = path.read_bytes()
            storage.immutable(path, {'generation': 1})
            with self.assertRaises(ValueError):
                storage.immutable(path, {'generation': 2})
            self.assertEqual(path.read_bytes(), original)
            with patch.object(storage, 'publish_once', side_effect=OSError('Injected before publication')):
                with self.assertRaises(OSError):
                    storage.immutable(directory / 'missing-private.json', {'generation': 2})
            self.assertFalse((directory / 'missing-private.json').exists())
            self.assertFalse(list(directory.glob('*.partial')))

    def test_four_os_slots_remain_unavailable_to_another_process(self):
        with tempfile.TemporaryDirectory(dir=campaign.ROOT / 'build') as temporary:
            directory = Path(temporary)
            leases = [storage.Lease(directory / ('slot-%d.lock' % index)) for index in range(4)]
            for lease in leases:
                self.assertTrue(lease.acquire())
            script = ('import sys; from pathlib import Path; '
                      'sys.path.insert(0,sys.argv[1]); from campaign_records import available; '
                      'print(sum(available(Path(sys.argv[2])/(' + repr('slot-%d.lock') + '%i)) for i in range(4)))')
            try:
                result = subprocess.run([sys.executable, '-c', script, str(campaign.HERE), str(directory)],
                                        capture_output=True, text=True, check=True)
                self.assertEqual(result.stdout.strip(), '0')
                leases[2].release()
                result = subprocess.run([sys.executable, '-c', script, str(campaign.HERE), str(directory)],
                                        capture_output=True, text=True, check=True)
                self.assertEqual(result.stdout.strip(), '1')
            finally:
                for lease in leases:
                    lease.release()


class RecoveryContracts(unittest.TestCase):
    def fixture(self, directory):
        target_sha = storage.immutable_bytes(directory / 'target.pcm16', bytes(64000))
        initial, targets = [], []
        for ordinal in range(27):
            targets.append(dict(ordinal=ordinal, kind='speech' if ordinal < 20 else 'music',
                group=summary.EXPECTED_GROUPS[ordinal], split=summary.split(ordinal), samples=32000,
                target_file='target.pcm16', target_sha256=target_sha))
            for kbps in (2, 3):
                key = 'case-%03d-rate-%d' % (ordinal, kbps)
                # Header-shaped storage fixture, never sent to a decoder.
                blob = struct.pack('<4sBBHIHHHHH', b'L4HY', 8 if kbps == 2 else 5,
                    15 if kbps == 2 else 4, 8000, 32000, 13926, 0, 320, 320 if kbps == 2 else 160, 0)
                stream_file, metric_file = key + '.lpx', key + '-private.json'
                initial.append(dict(job_id=key, ordinal=ordinal, kbps=kbps, selected_file=stream_file,
                    selected_sha256=storage.immutable_bytes(directory / stream_file, blob),
                    metric_file=metric_file, metric_sha256=storage.immutable(directory / metric_file, metrics(ordinal))))
        manifest = dict(initial=initial, targets=targets, stoi_eligible=ELIGIBLE)
        storage.immutable(directory / 'campaign-private.json', manifest)
        ledger = campaign.recover_ledger(directory, manifest)
        folder, plan = campaign.round_plan(directory, manifest, ledger)
        for job in plan['jobs']:
            attempt, claim = campaign.create_claim(directory, manifest, folder / 'plan-private.json', job, 0, False)
            before = storage.read(directory / job['input_metric_file'])
            report = dict(candidates=[before], selected_id=0, selected_differs_from_incumbent=False)
            report_file = attempt / 'report-private.json'
            storage.immutable(report_file, report)
            row = dict(status='PASS', manifest_sha256=claim['manifest_sha256'], plan_sha256=claim['plan_sha256'],
                job_sha256=claim['job_sha256'], claim_id=claim['claim_id'], claim_sha256=storage.file_digest(attempt / 'claim-private.json'),
                job_id=job['job_id'], ordinal=job['ordinal'], kbps=job['kbps'], kind=job['kind'], group=job['group'],
                input_sha256=job['input_sha256'], target_sha256=job['target_sha256'],
                selected_file=job['input_file'], selected_sha256=job['input_sha256'],
                metric_file=job['input_metric_file'], metric_sha256=job['input_metric_sha256'],
                report_file=report_file.relative_to(directory).as_posix(), report_sha256=storage.file_digest(report_file),
                before=before, after=before, changed=False, source_bindings_verified=True,
                native_common_and_v5_only_pcm_pwm_exact=True, wall_seconds=1., cpu_seconds=.5, actual_work_totals={'trials': 7})
            storage.immutable(attempt / 'complete-private.json', row)
        return manifest, ledger, folder, plan

    def test_recovery_ignores_mutable_ledger_and_rechecks_complete_round_plan(self):
        with tempfile.TemporaryDirectory(dir=campaign.ROOT / 'build') as temporary:
            directory = Path(temporary)
            manifest, ledger, folder, plan = self.fixture(directory)
            completed = campaign.commit_round(directory, manifest, ledger, folder, plan)
            self.assertEqual(completed['consecutive_no_clear'], 1)
            (directory / 'ledger-private.json').write_text('{"stop_condition_met":true}')
            self.assertEqual(campaign.recover_ledger(directory, manifest)['consecutive_no_clear'], 1)
            plan_file = folder / 'plan-private.json'
            original = plan_file.read_bytes()
            commit_file = folder / 'commit-private.json'
            original_commit = commit_file.read_bytes()
            changed = storage.read(plan_file)
            changed['jobs'][0]['input_sha256'] = '0' * 64
            plan_file.write_bytes(storage.encoded(changed))
            commit = storage.read(commit_file)
            commit['plan_sha256'] = storage.file_digest(plan_file)
            commit_file.write_bytes(storage.encoded(commit))
            with self.assertRaises(ValueError):
                campaign.recover_ledger(directory, manifest)
            plan_file.write_bytes(original)
            commit_file.write_bytes(original_commit)
            summary_file = folder / 'anonymous-summary.json'
            original_summary = summary_file.read_bytes()
            changed = storage.read(summary_file)
            changed.update(clear_numerical_gain=True, consecutive_no_clear=0, stop_condition_met=False)
            summary_file.write_bytes(storage.encoded(changed))
            commit = storage.read(commit_file)
            commit['summary_sha256'] = storage.file_digest(summary_file)
            commit_file.write_bytes(storage.encoded(commit))
            with self.assertRaises(ValueError):
                campaign.recover_ledger(directory, manifest)
            summary_file.write_bytes(original_summary)
            commit_file.write_bytes(original_commit)
            receipt = next(folder.glob('jobs/*/attempt-*/complete-private.json'))
            changed = storage.read(receipt)
            changed['before']['metrics']['pwm8']['error_energy'] += 1
            receipt.write_bytes(storage.encoded(changed))
            commit = storage.read(commit_file)
            for item in commit['selected']:
                if item['receipt_file'] == receipt.relative_to(directory).as_posix():
                    item['receipt_sha256'] = storage.file_digest(receipt)
            commit_file.write_bytes(storage.encoded(commit))
            with self.assertRaises(ValueError):
                campaign.recover_ledger(directory, manifest)

    def test_partial_job_set_cannot_publish_a_round_commit(self):
        with tempfile.TemporaryDirectory(dir=campaign.ROOT / 'build') as temporary:
            directory = Path(temporary)
            manifest, ledger, folder, plan = self.fixture(directory)
            next(folder.glob('jobs/*/attempt-*/complete-private.json')).unlink()
            with self.assertRaises(ValueError):
                campaign.commit_round(directory, manifest, ledger, folder, plan)
            self.assertFalse((folder / 'commit-private.json').exists())
            self.assertEqual(campaign.recover_ledger(directory, manifest)['consecutive_no_clear'], 0)


if __name__ == '__main__':
    unittest.main()

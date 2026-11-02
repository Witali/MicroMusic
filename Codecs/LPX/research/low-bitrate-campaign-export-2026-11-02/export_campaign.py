"""Export anonymous campaign evidence and a private final firmware input pool.

Run after the registered campaign stops and its exact source/native archive
exists. This performs no encoding search and does not publish, push or merge.
Private media, identities and fingerprints remain under the ignored campaign.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
STUDY = ROOT / 'Codecs/LPX/research/low-bitrate-speech-2026-11-02'
ACTIVE = ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
sys.path.insert(0, str(STUDY))
sys.path.insert(0, str(ACTIVE / 'tools'))

from campaign import load_campaign, recover_ledger, checked_file
from campaign_records import read, immutable, immutable_bytes, file_digest, digest, encoded
from campaign_summary import aggregate, deltas, split, verify_transition


def safe_aggregate(value):
    result = {key: value[key] for key in ('cases', 'mean_pwm_stoi', 'stoi_assessed_cases',
        'stoi_unassessed_cases', 'pwm_reference_energy', 'pwm_error_energy', 'aggregate_pwm_ser_db',
        'encoded_bytes', 'clipped_samples')}
    if value['ser_status'] not in ('finite', 'perfect', 'zero_reference'):
        raise ValueError('Unknown aggregate metric status')
    result['ser_status'] = value['ser_status']
    result['period'] = {domain: {key: value['period'][domain][key] for key in
        ('source_windows', 'within_tolerance', 'coverage', 'total_reference_windows', 'unknown_reference_windows')}
        for domain in ('voice', 'pwm_voice')}
    return result


def safe_delta(value, *, round_threshold):
    result = {key: value[key] for key in ('mean_pwm_stoi', 'aggregate_pwm_ser_db',
        'aggregate_pwm_ser_improved_to_perfect', 'pwm_source_period_coverage_percentage_points')}
    if round_threshold:
        result['clear_numerical_gain'] = value['clear_numerical_gain']
    return result


def safe_metric(row):
    domains = {}
    for domain in ('pcm16', 'pwm8'):
        value = row['metrics'][domain]
        domains[domain] = {key: value[key] for key in ('samples', 'reference_energy', 'error_energy',
            'ser_db', 'ser_status', 'rmse_pcm16', 'max_abs_error_pcm16', 'stoi')}
    return dict(file_bytes=row['file_bytes'], joint_proxy_score=row['score'], domains=domains,
        clipped_samples=row['clipped_samples'], period={domain: {key: row[domain][key] for key in
            ('frames', 'reference_period_frames', 'within_tolerance_frames')}
            for domain in ('voice', 'pwm_voice')})


def privacy_check(data):
    """Defense after positive field selection; no external scanning service."""
    text = data.decode('utf-8')
    patterns = (r'[A-Za-z]:[\\/]', r'/mnt/', r'/Users/',
                r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', r'(?i)\b[0-9a-f]{40,}\b')
    if any(re.search(pattern, text) for pattern in patterns):
        raise ValueError('Anonymous export contains a path, contact or fingerprint category')


def archive_verified(campaign, manifest):
    archive = campaign / 'frozen-source'
    index = read(archive / 'archive-private.json')
    if index['source_count'] != len(manifest['sources']) or set(index['sources']) != set(manifest['sources']):
        raise ValueError('The complete frozen source archive is required before final export')
    for relative, expected in manifest['sources'].items():
        value = index['sources'][relative]
        if value['sha256'] != expected or file_digest(archive / value['file']) != expected:
            raise ValueError('A frozen source artifact differs')
    for value in list(index['private_bindings'].values()) + list(index['native_libraries'].values()):
        if file_digest(archive / value['file']) != value['sha256']:
            raise ValueError('A frozen binding or native artifact differs')
    return archive, index


def markdown(result):
    lines = ['# LPX 2/3 kbit/s successive quality rounds', '',
        'Three registered rounds completed on the established 27-clip corpus at both exact complete-file caps: '
        '54 jobs per round, 162 final PASS receipts. Each round used its immediate predecessor\'s complete selected streams. '
        'No additional search round was inferred from compilation, infrastructure checks or reference replay.', '',
        'All three rounds fell below the prospective per-round heldout thresholds: +0.01 mean PWM STOI, '
        '+0.3 dB summed-energy PWM SER, or +5 percentage points source-period coverage. The actual '
        'consecutive-no-clear counter reached three. Smaller admitted numerical gains remain selected.', '',
        '| Round | Operator | Cap, kbit/s | Changed / 27 | Heldout Δ STOI | Heldout Δ PWM SER, dB | Heldout Δ period coverage, pp |',
        '| ---: | --- | ---: | ---: | ---: | ---: | ---: |']
    for row in result['rounds']:
        for budget, value in row['budgets'].items():
            delta = value['groups']['heldout_speech']['delta']
            number = lambda x, digits: 'unassessed' if x is None else f'{x:+.{digits}f}'
            lines.append(f"| {row['round']} | {row['operator']} | {budget} | {value['changed_cases']} | "
                f"{number(delta['mean_pwm_stoi'], 6)} | {number(delta['aggregate_pwm_ser_db'], 5)} | "
                f"{number(delta['pwm_source_period_coverage_percentage_points'], 3)} |")
    lines += ['', '## Final selected streams versus round0 selected streams', '',
        '| Cap, kbit/s | Changed / 27 | Mean heldout PWM STOI | Aggregate heldout PWM SER, dB | Heldout period counts / source windows |',
        '| ---: | ---: | --- | --- | --- |']
    for budget, value in result['final_vs_round0_selected']['budgets'].items():
        group = value['groups']['heldout_speech']
        before, after = group['before'], group['after']
        a, b = before['period']['pwm_voice'], after['period']['pwm_voice']
        lines.append(f"| {budget} | {value['changed_cases']} | {before['mean_pwm_stoi']:.6f} → {after['mean_pwm_stoi']:.6f} | "
            f"{before['aggregate_pwm_ser_db']:.5f} → {after['aggregate_pwm_ser_db']:.5f} | "
            f"{a['within_tolerance']} → {b['within_tolerance']} / {a['source_windows']} |")
    lines += ['', 'The heldout subset contains ten speech clips at each budget, including its registered quiet/noisy '
        'derivatives. STOI membership is fixed from round0; newly missing scores were not dropped. SER uses '
        'summed reference/error energy, not an average of decibels. Source-period coverage retains the same '
        'source-window denominator; unknown source windows are reported separately in the numeric evidence. '
        'The public 2.4-second listening example is excluded from these confirming aggregates.', '',
        'Per-clip numeric changes, tuning/heldout/negative-control groups, actual byte totals and named operation '
        'counters are retained in [the anonymous JSON](campaign-results.json). The score and guards are numerical '
        'proxies, not calibrated audibility, perceived-quality percentages or complete pitch preservation.', '',
        'The decoder arithmetic, rate, sample count, declared target gain, formats and exact byte caps remained '
        'fixed. Formats are sparse80 version8/mode15 at 2 kbit/s and v5/P4 at 3 kbit/s. Every selected full output '
        'passed the model and both common/v5-only native PCM/PWM checks. Final private sidecars were also '
        'replayed through both frozen native receivers.', '',
        'A private manifest contains all 54 exact final streams, targets and expected PCM/PWM for later firmware '
        'admission. Changed streams require fresh complete-image Flash/SRAM/stack and active-IRQ timing/underrun '
        'checks. An unchanged stream can reuse an existing round0 firmware receipt only when the entire linked '
        'build context also matches; host/native PASS alone does not establish AVR real-time support.', '',
        'No listening preference or physical-board result is claimed here. No audio, private source identities, '
        'paths or fingerprints are included in this report. Publication and main-branch integration remain separate.', '',
        '[Registered operators and stopping rule](ITERATION_PROTOCOL.md).']
    return ('\n'.join(lines) + '\n').encode('utf-8')


def export(campaign_path):
    campaign, manifest = load_campaign(campaign_path)
    ledger = recover_ledger(campaign, manifest)
    if ledger['completed_rounds'] != 3 or ledger['consecutive_no_clear'] != 3 or not ledger['stop_condition_met']:
        raise ValueError('Expected the actually completed registered three-round campaign')
    archive, archive_index = archive_verified(campaign, manifest)
    initial = {(value['ordinal'], value['kbps']): value for value in manifest['initial']}
    targets = {value['ordinal']: value for value in manifest['targets']}
    rounds = []
    infrastructure = 0
    for number in range(1, 4):
        folder = campaign / 'rounds' / ('round-%04d' % number)
        value = read(folder / 'anonymous-summary.json')
        result = {key: value[key] for key in ('round', 'operator', 'completed_jobs', 'clear_numerical_gain',
            'previous_consecutive_no_clear', 'consecutive_no_clear', 'stop_condition_met',
            'wall_seconds_sum', 'cpu_seconds_sum', 'work_totals')}
        result['budgets'] = {budget: dict(changed_cases=item['changed_cases'], clear_numerical_gain=item['clear_numerical_gain'],
            groups={group: dict(before=safe_aggregate(group_value['before']), after=safe_aggregate(group_value['after']),
                delta=safe_delta(group_value['delta'], round_threshold=True))
                for group, group_value in item['groups'].items()}) for budget, item in value['budgets'].items()}
        infrastructure += len(list(folder.glob('jobs/*/attempt-*/failure-private.json')))
        rounds.append(result)
    rows, private_rows, blobs = [], [], []
    pool = campaign / 'final-selected'
    for final in ledger['selected']:
        ordinal, kbps = final['ordinal'], final['kbps']
        before_binding = initial[ordinal, kbps]
        before = read(checked_file(campaign, before_binding['metric_file'], before_binding['metric_sha256']))
        after = read(checked_file(campaign, final['metric_file'], final['metric_sha256']))
        verify_transition(before, after)
        blob = checked_file(campaign, final['selected_file'], final['selected_sha256']).read_bytes()
        changed = final['selected_sha256'] != before_binding['selected_sha256']
        rows.append(dict(ordinal=ordinal, kbps=kbps, group=targets[ordinal]['group'], split=split(ordinal),
            changed=changed, before=before, after=after))
        name = final['job_id']
        stream_file = 'streams/' + name + '.lpx'
        actual = immutable_bytes(pool / stream_file, blob)
        if actual != final['selected_sha256']:
            raise ValueError('The final selected stream copy differs')
        target = targets[ordinal]
        private_rows.append(dict(job_id=name, ordinal=ordinal, kbps=kbps, samples=32000, sample_hz=8000,
            format_version=8 if kbps == 2 else 5, mode=15 if kbps == 2 else 4,
            stream_file=stream_file, stream_sha256=actual, encoded_bytes=len(blob), complete_byte_cap=32000 * kbps // 64,
            target_file='../' + target['target_file'], target_sha256=target['target_sha256'], declared_level=target['level'],
            initial_stream_sha256=before_binding['selected_sha256'], unchanged_from_round0=not changed,
            requires_fresh_linked_image_due_to_changed_data=changed,
            round0_firmware_receipt_reuse_requires_identical_complete_build_context=True,
            full_target_firmware_admission_complete=False,
            final_campaign_receipt='../' + final['receipt_file'], final_campaign_receipt_sha256=final['receipt_sha256']))
        blobs.append(blob)
    # Frozen native reference replay only; there is no excitation or LPC search.
    import numpy as np
    from batch_decoder import BatchDecoder
    import speech_sparse80 as sparse
    expanded = [sparse.expand(blob) if item['kbps'] == 2 else blob for blob, item in zip(blobs, private_rows)]
    native = {}
    for role in ('common', 'v5_only'):
        value = archive_index['native_libraries'][role]
        receiver = BatchDecoder(archive / value['file'])
        native[role] = (receiver.decode_many_s16(expanded, 32000), receiver.decode_many(expanded, 32000))
    for index, item in enumerate(private_rows):
        pcm, pwm = native['common'][0][index], native['common'][1][index]
        if (pcm is None or pwm is None or not np.array_equal(pcm, native['v5_only'][0][index])
                or not np.array_equal(pwm, native['v5_only'][1][index])):
            raise ValueError('Final frozen native reference replay differs')
        target = targets[item['ordinal']]
        target_path = checked_file(campaign, target['target_file'], target['target_sha256'])
        reference = np.frombuffer(target_path.read_bytes(), dtype='<i2').astype(np.int64)
        for domain, actual in (('pcm16', pcm.astype(np.int64)), ('pwm8', (pwm.astype(np.int64)-128)*256)):
            error = actual - reference
            recorded = rows[index]['after']['metrics'][domain]
            if (float(reference @ reference) != recorded['reference_energy']
                    or float(error @ error) != recorded['error_energy']):
                raise ValueError('Final waveform sidecar differs from its complete-target metric binding')
        pcm_file, pwm_file = 'expected/' + item['job_id'] + '.pcm16', 'expected/' + item['job_id'] + '.pwm8'
        item.update(expected_pcm16_file=pcm_file,
            expected_pcm16_sha256=immutable_bytes(pool / pcm_file, pcm.astype('<i2').tobytes()),
            expected_pwm8_file=pwm_file, expected_pwm8_sha256=immutable_bytes(pool / pwm_file, pwm.tobytes()),
            frozen_common_and_v5_only_replay_exact=True)
    private_manifest = dict(schema='lpx-final-corpus-firmware-inputs-private-v1', samples_per_case=32000,
        sample_hz=8000, jobs=private_rows, job_count=54, completed_host_rounds=3,
        campaign_manifest_sha256=file_digest(campaign / 'campaign-private.json'),
        final_commit_sha256=ledger['previous_commit_sha256'], frozen_source_archive='../frozen-source/archive-private.json',
        native_libraries={role: dict(file='../frozen-source/' + value['file'], sha256=value['sha256'])
                          for role, value in archive_index['native_libraries'].items()},
        unchanged_from_round0=sum(value['unchanged_from_round0'] for value in private_rows),
        changed_requiring_fresh_linked_image=sum(value['requires_fresh_linked_image_due_to_changed_data'] for value in private_rows),
        scope='Private media and bindings; full hardware admission remains pending. No publication or main merge.')
    immutable(pool / 'firmware-inputs-private.json', private_manifest)
    final_budgets = {}
    for kbps in (2, 3):
        available = [row for row in rows if row['kbps'] == kbps]
        groups = {name: [row for row in available if row['split'] == name]
                  for name in ('heldout_speech', 'tuning_speech', 'negative_controls')}
        groups.update({name: [row for row in available if row['group'] == name] for name in set(r['group'] for r in rows)})
        values = {}
        for group, members in sorted(groups.items()):
            a = aggregate([dict(ordinal=r['ordinal'], metrics=r['before']) for r in members], manifest['stoi_eligible'][str(kbps)])
            b = aggregate([dict(ordinal=r['ordinal'], metrics=r['after']) for r in members], manifest['stoi_eligible'][str(kbps)])
            values[group] = dict(before=safe_aggregate(a), after=safe_aggregate(b), delta=safe_delta(deltas(a, b), round_threshold=False))
        final_budgets[str(kbps)] = dict(changed_cases=sum(row['changed'] for row in available), groups=values)
    public = dict(schema='lpx-lowrate-campaign-results-v1', corpus_cases=27, samples_per_case=32000,
        sample_hz=8000, complete_caps_bytes={'2': 1000, '3': 1500}, completed_followup_rounds=3,
        completed_final_pass_jobs=162, infrastructure_failure_attempts=infrastructure,
        registered_stopping=dict(consecutive_no_clear=3, stop_condition_met=True, heldout_pwm_stoi=.01,
            heldout_aggregate_pwm_ser_db=.3, heldout_pwm_period_coverage_percentage_points=5),
        rounds=rounds, final_vs_round0_selected=dict(budgets=final_budgets,
            rows=[dict(ordinal=r['ordinal'], kbps=r['kbps'], group=r['group'], split=r['split'],
                       changed=r['changed'], before=safe_metric(r['before']), after=safe_metric(r['after'])) for r in rows]),
        decoder_arithmetic_changed=False, private_media_included=False,
        scope='Anonymous numerical evidence only; no subjective audibility, complete pitch-preservation or AVR support guarantee. Cumulative comparison is descriptive; stopping was assessed per completed round.')
    json_data, md_data = encoded(public), markdown(public)
    privacy_check(json_data)
    privacy_check(md_data)
    immutable_bytes(STUDY / 'campaign-results.json', json_data)
    immutable_bytes(STUDY / 'CAMPAIGN_RESULTS.md', md_data)
    # Source/protocol pins must remain valid after adding only non-pinned results.
    load_campaign(campaign)
    return dict(archived_sources=archive_index['source_count'], final_streams=54,
        native_replays_exact=54, unchanged_from_round0=private_manifest['unchanged_from_round0'],
        changed_requiring_fresh_linked_image=private_manifest['changed_requiring_fresh_linked_image'],
        anonymous_exports=2, pinned_existing_sources_unchanged=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign', type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.campaign)))


if __name__ == '__main__':
    main()

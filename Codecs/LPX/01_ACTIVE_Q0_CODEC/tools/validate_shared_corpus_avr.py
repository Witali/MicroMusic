"""Actual AVR PWM/IRQ validation of saved shared-corpus 4/6 outputs.

Saved decoded PCM is the simulation oracle. The independent integer model
checks it before simulation; no active native decoder supplies the oracle.
All generated audio, binaries, cache and reports belong in ignored build/.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import soundfile as sf

from benchmark_speech_flash import (CANDIDATES, compile_image, environment,
    runtime_fingerprint, same_harness, simulate)
from benchmark_standards import save
from profile_avr import ROOT
from shared_corpus import _ignored_output
from speech_compact import decode_model, pack, unpack
from standard_metrics import pwm_duties

PROFILES = (4, 6)
WINNER = 'unroll1-tune0-lto-call-relax'
NATIVE_FLAGS = ('native_model_pcm16_exact', 'native_common_pcm16_exact',
                'native_compact_only_pcm16_exact', 'native_pwm_exact')


def sha(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def need(condition, message):
    if not condition:
        raise ValueError(message)


def safe(root, relative):
    root = Path(root).resolve()
    relative = Path(relative)
    path = (root / relative).resolve()
    need(not relative.is_absolute() and path.is_relative_to(root), 'Relative path escapes its declared tree')
    return path


def pcm_reference(root, relative, samples, expected):
    path = safe(root, relative)
    pcm, rate = sf.read(path, dtype='int16')
    need(rate == 8000 and pcm.shape == (samples,), 'Saved PCM geometry mismatch')
    need(sha(pcm.astype('<i2').tobytes()) == expected, 'Saved PCM sample hash mismatch')
    return pcm, sha(path.read_bytes())


def case_jobs(inputs, selected, case, profile, report):
    """Validate the entire case, then expose segment jobs and immutable oracles."""
    need(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', case['id']) is not None, 'Unsafe case identifier')
    dest = safe(selected, case['id'] + '/' + str(profile))
    unsigned = {k: v for k, v in report.items() if k != 'report_sha256'}
    need(report.get('report_sha256') == sha(canonical(unsigned)), 'Selected report integrity mismatch')
    need(report.get('status') == 'complete', 'Selected case is not complete')
    need(report.get('id') == case['id'] and report.get('profile') == profile and
         report.get('samples') == case['samples'] and report.get('reference_pcm16_sha256') == case['reference_pcm16_sha256'],
         'Selected report does not match prepared case')
    reference, original_wav_hash = pcm_reference(inputs, case['reference'], case['samples'], case['reference_pcm16_sha256'])
    need(len(report['segments']) == len(case['segments']) and bool(case['segments']), 'Selected segment count mismatch')
    for flag in NATIVE_FLAGS:
        need(flag not in report or report[flag] is True, 'Selected native attestation failed')
    jobs, pieces, start = [], [], 0
    for expected, record in zip(case['segments'], report['segments']):
        index = len(jobs)
        n = expected['samples']
        need(expected['index'] == index and expected['start'] == start and 1 <= n <= 64000,
             'Prepared segments must be contiguous, ordered and bounded')
        need(all(record[k] == expected[k] for k in ('index', 'start', 'samples')), 'Selected segment geometry mismatch')
        ref, ref_wav_hash = pcm_reference(inputs, expected['reference'], n, expected['pcm16_sha256'])
        need(np.array_equal(ref, reference[start:start + n]), 'Prepared segment differs from full reference')
        need(record['reference_pcm16_sha256'] == expected['pcm16_sha256'], 'Selected segment reference changed')
        stream_path = safe(dest, record['stream'])
        blob = stream_path.read_bytes()
        pcm, oracle_wav_hash = pcm_reference(dest, record['decoded'], n, record['pcm16_sha256'])
        need(blob[:5] == b'L4HY\x05' and blob[5] in (profile, profile | 128), 'Expected matching v5 profile')
        need(sha(blob) == record['stream_sha256'] and len(blob) == record['file_bytes'], 'Selected stream hash/size mismatch')
        cap = 20 + ((n + 319) // 320) * (20 if profile == 4 else 30)
        need(record['cap_bytes'] == cap and len(blob) <= cap, 'Selected stream exceeds complete-file cap')
        need(unpack(blob)[0] == n and np.array_equal(pcm, decode_model(blob)), 'Selected PCM/model/sample-count mismatch')
        pwm = pwm_duties(pcm).tobytes()
        need(sha(pwm) == record['pwm_sha256'], 'Selected useful PWM hash mismatch')
        attestations = {k: record[k] for k in NATIVE_FLAGS if k in record}
        need(all(v is True for v in attestations.values()), 'Selected segment native attestation failed')
        identifier = f'{case["id"]}-p{profile}-s{index:03d}'
        item = dict(id=identifier, case=case['id'], profile=profile, blob=blob, pwm=pwm,
            samples=n, stream_sha256=sha(blob), pcm_sha256=record['pcm16_sha256'])
        context = dict(id=identifier, case_id=case['id'], profile=profile, cohort=case['cohort'],
            segment_index=index, segment_start=start, samples=n,
            reference_pcm16_sha256=expected['pcm16_sha256'], reference_wav_sha256=ref_wav_hash,
            original_reference_pcm16_sha256=case['reference_pcm16_sha256'], original_reference_wav_sha256=original_wav_hash,
            selected_stream_sha256=sha(blob), saved_oracle_pcm16_sha256=record['pcm16_sha256'],
            saved_oracle_wav_sha256=oracle_wav_hash, useful_pwm_sha256=sha(pwm),
            cap_bytes=cap, native_attestations=attestations,
            native_attestation_scope='Recorded encoder checks only; saved PCM and fresh integer model define the AVR oracle.',
            reset_scope='Decoder resets at each independently encoded prepared segment.')
        jobs.append({'item': item, 'context': context})
        pieces.append(pcm)
        start += n
    need(start == case['samples'], 'Prepared segments omit reference samples')
    full, full_wav_hash = pcm_reference(dest, 'complete.wav', case['samples'], report['pcm16_sha256'])
    need(np.array_equal(np.concatenate(pieces), full), 'Selected complete PCM differs from segment concatenation')
    need(report['file_bytes'] == sum(r['file_bytes'] for r in report['segments']), 'Selected full stream byte accounting mismatch')
    if 'payload_bytes' in report:
        need(report['payload_bytes'] == sum(r['file_bytes'] - 22 for r in report['segments']), 'Selected full payload accounting mismatch')
    for job in jobs:
        job['context']['selected_report_sha256'] = report['report_sha256']
        job['context']['selected_report_file_sha256'] = sha((dest / 'report.json').read_bytes())
        job['context']['saved_complete_oracle_wav_sha256'] = full_wav_hash
    return jobs


def collect_jobs(inputs, selected, cohorts=None, shard=0, shards=1):
    need(0 <= shard < shards, 'Invalid shard')
    inputs, selected = Path(inputs), Path(selected)
    manifest = load(inputs / 'manifest.json')
    need(manifest.get('schema') == 'lpx-shared-corpus-v1' and manifest.get('sample_rate') == 8000,
         'Expected prepared shared-corpus manifest at 8 kHz')
    need(len({c['id'] for c in manifest['cases']}) == len(manifest['cases']), 'Duplicate prepared case identifiers')
    available = {c['cohort'] for c in manifest['cases']}
    need(cohorts is None or bool(cohorts) and set(cohorts) <= available, 'Unknown or empty cohort selection')
    cases = [c for c in manifest['cases'] if cohorts is None or c['cohort'] in cohorts]
    need(bool(cases), 'No prepared cases selected')
    expected_index, jobs, records = 0, [], []
    expected_shard = 0
    for case in cases:
        for profile in PROFILES:
            indexes = list(range(expected_index, expected_index + len(case['segments'])))
            expected_index += len(indexes)
            assigned = [i for i in indexes if i % shards == shard]
            expected_shard += len(assigned)
            path = safe(selected, case['id'] + '/' + str(profile) + '/report.json')
            summary = dict(case_id=case['id'], profile=profile, expected_segments=len(indexes), assigned_segments=len(assigned))
            if not path.is_file():
                summary.update(status='missing', reason='Selected case report is absent')
                records.append(summary)
                continue
            try:
                report = load(path)
                summary['selected_report_file_sha256'] = sha(path.read_bytes())
                if report.get('status') != 'complete':
                    summary.update(status='selected_failure', selected_status=report.get('status', 'unspecified'))
                else:
                    valid = case_jobs(inputs, selected, case, profile, report)
                    summary['status'] = 'complete'
                    jobs += [job for index, job in zip(indexes, valid) if index % shards == shard]
            except (ValueError, KeyError, TypeError, OSError, AssertionError) as error:
                summary.update(status='invalid', error_type=type(error).__name__, reason='Selected input/output validation failed')
            records.append(summary)
    counts = Counter(row['status'] for row in records)
    accounting = dict(input_manifest_sha256=sha((inputs / 'manifest.json').read_bytes()),
        expected_case_profiles=2 * len(cases), expected_segment_jobs=expected_index,
        expected_shard_segment_jobs=expected_shard, valid_shard_segment_jobs=len(jobs),
        case_status_counts=dict(counts), case_profiles=records,
        all_selected_cases_complete=counts.get('complete', 0) == 2 * len(cases))
    return jobs, accounting


def flash_environment(avr_bin, compact_only=True):
    result = environment(ROOT, avr_bin, compact_only)
    result['dependencies'][Path(__file__).name] = sha(Path(__file__).read_bytes())
    return result


def _output_tree(output, inputs, selected):
    output = Path(output).resolve()
    _ignored_output(output)
    for original in (Path(inputs).resolve(), Path(selected).resolve()):
        need(output != original and output not in original.parents and original not in output.parents,
             'AVR output and input/selection trees must not overlap')
    output.mkdir(parents=True, exist_ok=True)
    return output


def _status(report):
    images = list(report['images'].values())
    return dict(measured_images=len(images), failed_images=sum(r['status'] != 'complete' for r in images),
        measured_underruns=sum(r['measurement'].get('underruns', 0) for r in images if 'measurement' in r),
        images_with_underruns=sum(r.get('measurement', {}).get('underruns', 0) > 0 for r in images),
        complete_zero_underrun_images=sum(r['status'] == 'complete' and r['measurement']['underruns'] == 0 for r in images))


def _measure(job, folder, env, runtime, avr_bin, runner, lib, wsl, baseline, assembly=True, irq=0):
    row = dict(context=job['context'], status='failed')
    try:
        measurement = simulate(ROOT, env, CANDIDATES[WINNER], job['item'], folder,
            avr_bin, runner, lib, wsl, runtime, assembly=assembly, irq=irq)
        same_harness(measurement, baseline)
        row.update(status='complete', measurement=measurement,
                   zero_underruns=measurement['underruns'] == 0)
    except (ValueError, RuntimeError, AssertionError, OSError, subprocess.CalledProcessError) as error:
        row['error_type'] = type(error).__name__
        row['reason'] = 'Actual AVR compile/simulation/output or harness validation failed; inspect ignored local logs.'
        cache = Path(folder) / 'verification.json'
        if cache.exists():
            previous = load(cache)
            value = previous.get('measurement', {})
            if previous.get('environment') == env and previous.get('measurement_sha256') == sha(canonical(value)):
                row['measurement'] = value
    return row


def validate(inputs, selected, output, avr_bin, runner, lib, wsl=None, shard=0, shards=1, cohorts=None, common=False):
    output = _output_tree(output, inputs, selected)
    jobs, accounting = collect_jobs(inputs, selected, cohorts, shard, shards)
    env = flash_environment(avr_bin, not common)
    runtime = runtime_fingerprint(runner, lib, wsl)
    mode = 'common' if common else 'compact-only'
    report = dict(schema='lpx-shared-corpus-avr-v1', mode='validate', compact_only=not common,
        environment=env, runtime=runtime, candidate=WINNER, specification=CANDIDATES[WINNER],
        shard=shard, shards=shards, accounting=accounting, images={}, physical_hardware_measured=False,
        oracle='Complete useful PWM from saved selected PCM16, checked against the independent integer model.',
        stack_scope='Observed after profile_ready; not startup/worst-case proof.', wall_scope='Includes active IRQ and instrumentation.')
    result = output / f'verification-{mode}-{shard:02d}-of-{shards:02d}.json'
    save(result, report)
    baseline = None
    for job in jobs:
        if baseline is None:
            baseline = compile_image(ROOT, env, CANDIDATES['baseline'], job['item'],
                output / 'reference' / mode / f'shard-{shard:02d}', avr_bin)
        identifier = job['item']['id']
        report['images'][identifier] = _measure(job, output / 'images' / mode / identifier,
            env, runtime, avr_bin, runner, lib, wsl, baseline)
        report['summary'] = _status(report)
        save(result, report)
    report['summary'] = _status(report)
    report['summary']['all_expected_shard_images_measured'] = (
        len(report['images']) == accounting['expected_shard_segment_jobs'] and
        not report['summary']['failed_images'])
    save(result, report)
    return report


def repeated_packet_item(item, samples=64000):
    """Tile full stored parameter packets, then model one continuous decode."""
    need(samples == 64000, 'The continuous control is exactly 64000 samples')
    n, profile, spectra, params, pulses, pre, bright, extras = unpack(item['blob'])
    packets = (n + 319) // 320
    need(len(spectra) == packets and len(params) == packets * 2 and
         len(pulses) == packets * 16 and len(extras) == packets * 8, 'Source packet field geometry mismatch')
    order = [i % packets for i in range(200)]
    repeated_spectra = [spectra[i] for i in order]
    repeated_params = [p for i in order for p in params[i * 2:(i + 1) * 2]]
    repeated_pulses = [p for i in order for p in pulses[i * 16:(i + 1) * 16]]
    repeated_extras = [p for i in order for p in extras[i * 8:(i + 1) * 8]]
    blob, _ = pack(samples, profile, repeated_spectra, repeated_params, repeated_pulses,
        pre, bright, repeated_extras, force_extras=bool(item['blob'][5] & 128))
    pcm = decode_model(blob)
    need(pcm.shape == (samples,), 'Continuous model sample count mismatch')
    repeated = dict(id=f'stress-p{profile}', case=item['case'], profile=profile, samples=samples,
        blob=blob, pwm=pwm_duties(pcm).tobytes(), stream_sha256=sha(blob), pcm_sha256=sha(pcm.astype('<i2').tobytes()))
    derivation = dict(source_stream_sha256=sha(item['blob']), source_samples=n,
        source_stored_packets=packets, source_partial_last_packet_samples=n % 320,
        source_last_packet_previously_unplayed_samples=(-n) % 320,
        target_samples=samples, target_packets=200,
        packet_order_sha256=sha(np.asarray(order, dtype='<u2').tobytes()),
        policy='Tile complete stored packet fields including any source partial-packet unused tail; truncate the packet sequence at exactly 200 packets.',
        reset_scope='One fresh decoder reset at control start; continuous predictor/filter state across all packet repeats.',
        oracle='Fresh integer model on the newly packed 64000-sample stream; never concatenated decoded WAVs.')
    return repeated, pcm, derivation


def choose_heaviest(reports, valid_jobs, compact_only):
    available, duplicates = {}, 0
    for report in reports:
        need(report.get('schema') == 'lpx-shared-corpus-avr-v1' and report.get('mode') == 'validate', 'Expected normal shared-corpus AVR measurements')
        need(report.get('compact_only') is compact_only, 'Measurement format profile differs')
        for identifier, row in report['images'].items():
            if identifier not in valid_jobs or row.get('status') != 'complete':
                continue
            measurement = row['measurement']
            need(row['context']['selected_stream_sha256'] == valid_jobs[identifier]['item']['stream_sha256'], 'Source measurement stream changed')
            need(measurement['assembly_enabled'] and measurement['extra_irq_cycles'] == 0, 'Expected normal ASM measurements')
            if identifier in available:
                duplicates += 1
                need(available[identifier]['measurement'] == measurement, 'Conflicting duplicate measurements')
            available[identifier] = row
    choices = {}
    for profile in PROFILES:
        eligible = [(identifier, row) for identifier, row in available.items() if row['context']['profile'] == profile]
        if eligible:
            identifier, row = min(eligible, key=lambda pair: (-pair[1]['measurement']['mean_decode_wall_cycles'], pair[0]))
            choices[profile] = (identifier, row)
    return choices, dict(measured_source_jobs=len(available), expected_valid_jobs=len(valid_jobs),
        duplicate_identical_measurements=duplicates, all_valid_jobs_measured=len(available) == len(valid_jobs),
        selection_scope='Maximum measured mean decode wall cycles per profile among available complete normal ASM measurements.')


def stress(inputs, selected, output, avr_bin, runner, lib, wsl=None, cohorts=None, common=False, measurements=None):
    output = _output_tree(output, inputs, selected)
    jobs, accounting = collect_jobs(inputs, selected, cohorts)
    valid = {job['item']['id']: job for job in jobs}
    paths = []
    mode = 'common' if common else 'compact-only'
    for entry in measurements or [output]:
        entry = Path(entry)
        paths += sorted(entry.glob(f'verification-{mode}-*-of-*.json')) if entry.is_dir() else [entry]
    need(bool(paths), 'No normal AVR measurement reports were supplied')
    reports = [load(p) for p in paths]
    choices, selection = choose_heaviest(reports, valid, not common)
    env = flash_environment(avr_bin, not common)
    runtime = runtime_fingerprint(runner, lib, wsl)
    for previous in reports:
        need(previous['environment'] == env and previous['runtime'] == runtime, 'Source measurements use different source/toolchain/runtime')
        need(previous['accounting']['input_manifest_sha256'] == accounting['input_manifest_sha256'], 'Source measurements use another prepared corpus')
    report = dict(schema='lpx-shared-corpus-avr-v1', mode='stress', compact_only=not common,
        environment=env, runtime=runtime, candidate=WINNER, specification=CANDIDATES[WINNER],
        accounting=accounting, source_selection=selection,
        source_measurement_report_sha256=[sha(p.read_bytes()) for p in paths],
        controls={}, images={}, physical_hardware_measured=False,
        stack_scope='Observed after profile_ready; not startup/worst-case proof.',
        wall_scope='Includes active IRQ and instrumentation.')
    result = output / f'stress-{mode}.json'
    save(result, report)
    for profile in PROFILES:
        if profile not in choices:
            report['controls'][str(profile)] = {'status': 'missing', 'reason': 'No validated normal source measurement'}
            save(result, report)
            continue
        identifier, measured = choices[profile]
        item, pcm, derivation = repeated_packet_item(valid[identifier]['item'])
        folder = output / 'stress' / mode / str(profile)
        folder.mkdir(parents=True, exist_ok=True)
        sf.write(folder / 'model-reference.wav', pcm, 8000, subtype='PCM_16')
        (folder / 'control.l4hy').write_bytes(item['blob'])
        control = dict(status='measured', source_job=identifier,
            source_mean_decode_wall_cycles=measured['measurement']['mean_decode_wall_cycles'], derivation=derivation,
            control_stream_sha256=item['stream_sha256'], model_pcm16_sha256=item['pcm_sha256'],
            model_wav_sha256=sha((folder / 'model-reference.wav').read_bytes()))
        report['controls'][str(profile)] = control
        baseline = compile_image(ROOT, env, CANDIDATES['baseline'], item, folder / 'reference', avr_bin)
        for name, assembly, irq in [('normal', True, 0), ('extra_irq100', True, 100), ('c_fallback', False, 0)]:
            context = dict(id=f'p{profile}-{name}', profile=profile, source_job=identifier,
                samples=64000, control=name, model_pcm16_sha256=item['pcm_sha256'],
                useful_pwm_sha256=sha(item['pwm']), derivation=derivation)
            job = {'item': item, 'context': context}
            report['images'][context['id']] = _measure(job, folder / name, env, runtime,
                avr_bin, runner, lib, wsl, baseline, assembly, irq)
            report['summary'] = _status(report)
            save(result, report)
    report['summary'] = _status(report)
    save(result, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    for name in ('validate', 'stress'):
        command = sub.add_parser(name)
        for option in ('inputs', 'selected', 'output', 'avr-bin', 'runner', 'lib'):
            command.add_argument('--' + option, type=Path, required=True)
        command.add_argument('--wsl')
        command.add_argument('--common', action='store_true')
        command.add_argument('--cohorts', nargs='+')
        if name == 'validate':
            command.add_argument('--shard', type=int, default=0)
            command.add_argument('--shards', type=int, default=1)
        else:
            command.add_argument('--measurements', type=Path, nargs='+')
    args = vars(parser.parse_args())
    mode = args.pop('mode')
    result = globals()[mode](**args)
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()

"""Locally compare frozen four-pulse search with exact saved round3 2k winners.

Input bindings, hashes, paths, symbols and all payloads are PRIVATE ignored
artifacts. Public export uses an explicit whitelist of anonymous numeric fields.
Never recreate, resample, align or normalize the saved integer targets.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import time
import traceback

for variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[variable] = '1'

PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument('command', choices=('prepare', 'pilot', 'all', 'export'))
PARSER.add_argument('--packages', type=Path)
PARSER.add_argument('--campaign', type=Path)
PARSER.add_argument('--output', type=Path, required=True)
PARSER.add_argument('--public', type=Path)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                       allow_nan=False) + '\n').encode('utf-8')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.partial')
    pending.write_bytes(encoded(value))
    pending.replace(path)


def checked(root, relative, expected):
    path = (root / relative).resolve()
    path.relative_to(root.resolve())
    if digest(path.read_bytes()) != expected:
        raise ValueError('Authoritative saved file digest mismatch')
    return path


def initialize(packages):
    if packages:
        sys.path.insert(0, str(packages.resolve()))
    global e, np, sparse, NativeReceiver, OUTPUT, REPO, ACTIVE, summary
    import exhaustive as e
    import numpy as np
    import speech_sparse80 as sparse
    from native_receiver import NativeReceiver, OUTPUT, REPO, ACTIVE
    sys.path.insert(0, str(REPO / 'Codecs/LPX/research/low-bitrate-speech-2026-11-02'))
    import campaign_summary as summary


def software():
    files = [HERE / name for name in ('exhaustive.py', 'run_campaign.py', 'native_receiver.py',
             'decoder_server.cpp', 'MECHANISM_PROTOCOL.md', 'SPEECH_PROTOCOL.md')]
    files += sorted((ACTIVE / 'tools').glob('*.py'))
    files += [p for p in sorted((ACTIVE / 'src').iterdir()) if p.is_file()]
    files += [REPO / 'Codecs/LPX/research/low-bitrate-speech-2026-11-02/campaign_summary.py']
    return {p.relative_to(REPO).as_posix(): digest(p.read_bytes()) for p in files}


def runtime():
    from importlib.metadata import version
    return dict(python=sys.version.split()[0], system=platform.system(), machine=platform.machine(),
                packages={name: version(name) for name in ('numpy', 'scipy', 'numba', 'soundfile', 'pystoi')})


def private_output(path):
    path = path.resolve()
    path.relative_to((REPO / 'build').resolve())
    if path == (REPO / 'build').resolve():
        raise ValueError('Use a dedicated ignored experiment directory')
    return path


def bind_campaign(root):
    """Read only the old campaign. Resolve final27, never 81 historical cases."""
    root = root.resolve()
    manifest_bytes = (root / 'campaign-private.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    if (manifest['schema'] != 'lpx-followup-campaign-v1' or len(manifest['targets']) != 27
            or len(manifest['initial']) != 54):
        raise ValueError('Expected the original complete 27-target campaign')
    targets = {t['ordinal']: t for t in manifest['targets']}
    if set(targets) != set(range(27)):
        raise ValueError('Original target membership changed')
    for ordinal, target in targets.items():
        if (target['samples'] != 32000 or target['sample_hz'] != 8000
                or target['group'] != summary.EXPECTED_GROUPS[ordinal]
                or target['kind'] != ('speech' if ordinal < 20 else 'music')
                or target['split'] != summary.split(ordinal)):
            raise ValueError('Original group, heldout split or target geometry changed')
        level = target['level']
        exponent = level['gain_power2_exponent']
        if (level['policy'] != 'auto-quiet' or type(exponent) is not int or not 0 <= exponent <= 16
                or level['gain'] != 1 << exponent):
            raise ValueError('Saved declared target policy changed')
        payload = checked(root, target['target_file'], target['target_sha256']).read_bytes()
        if len(payload) != 64000:
            raise ValueError('Saved integer target size changed')
    previous = digest(manifest_bytes)
    selected = manifest['initial']
    verified = 0
    for number in range(1, 4):
        folder = root / 'rounds' / ('round-%04d' % number)
        commit_bytes = (folder / 'commit-private.json').read_bytes()
        commit = json.loads(commit_bytes)
        operator = ('pitch_proposals', 'spectral_round', 'beam_innovations')[number - 1]
        if (commit['round'] != number or commit['manifest_sha256'] != digest(manifest_bytes)
                or commit['previous_commit_sha256'] != previous or commit['operator'] != operator
                or len(commit['selected']) != 54):
            raise ValueError('Original round commit chain changed')
        plan = read(checked(root, (folder / 'plan-private.json').relative_to(root), commit['plan_sha256']))
        jobs = []
        for prior in selected:
            target = targets[prior['ordinal']]
            jobs.append(dict(job_id=prior['job_id'], ordinal=prior['ordinal'], kbps=prior['kbps'],
                kind=target['kind'], group=target['group'], split=target['split'], samples=target['samples'],
                target_file=target['target_file'], target_sha256=target['target_sha256'],
                input_file=prior['selected_file'], input_sha256=prior['selected_sha256'],
                input_metric_file=prior['metric_file'], input_metric_sha256=prior['metric_sha256']))
        expected_plan = dict(schema='lpx-followup-round-plan-v1', round=number, operator=operator,
                             manifest_sha256=digest(manifest_bytes), previous_commit_sha256=previous, jobs=jobs)
        if plan != expected_plan:
            raise ValueError('Original immediately preceding selection binding changed')
        if {(s['ordinal'], s['kbps']) for s in commit['selected']} != {(i, k) for i in range(27) for k in (2, 3)}:
            raise ValueError('Original committed case membership changed')
        checked(root, commit['summary_file'], commit['summary_sha256'])
        for item in commit['selected']:
            # Verify both-budget chain files, but ONLY 2k will be searched.
            stream = checked(root, item['selected_file'], item['selected_sha256'])
            metric_file = checked(root, item['metric_file'], item['metric_sha256'])
            receipt_file = checked(root, item['receipt_file'], item['receipt_sha256'])
            metric, receipt = read(metric_file), read(receipt_file)
            job = next(j for j in jobs if (j['ordinal'], j['kbps']) == (item['ordinal'], item['kbps']))
            claim_file = receipt_file.parent / 'claim-private.json'
            claim = read(claim_file)
            if (receipt['status'] != 'PASS' or receipt['manifest_sha256'] != digest(manifest_bytes)
                    or receipt['plan_sha256'] != commit['plan_sha256'] or receipt['job_sha256'] != digest(encoded(job))
                    or receipt['input_sha256'] != job['input_sha256'] or receipt['target_sha256'] != job['target_sha256']
                    or receipt['claim_id'] != claim['claim_id'] or receipt['claim_sha256'] != digest(claim_file.read_bytes())
                    or not receipt['source_bindings_verified'] or not receipt['native_common_and_v5_only_pcm_pwm_exact']
                    or any(receipt[key] != item[key] for key in ('selected_file', 'selected_sha256',
                                                                  'metric_file', 'metric_sha256'))):
                raise ValueError('Original completion receipt is not bound to its immutable job')
            report = read(checked(root, receipt['report_file'], receipt['report_sha256']))
            pointer = read(stream.parent / 'best-private.json')
            if (pointer['candidate_sha256'] != item['selected_sha256'] or pointer['candidate_file'] != stream.name
                    or pointer['selected_id'] != metric['id'] or not metric['admissible']
                    or report['candidates'][report['selected_id']] != metric or receipt['after'] != metric
                    or metric['file_bytes'] != stream.stat().st_size):
                raise ValueError('Original best pointer, report, metric or stream disagrees')
            summary.validate_metrics(metric)
            verified += 1
        selected, previous = commit['selected'], digest(commit_bytes)
    final = []
    for item in selected:
        if item['kbps'] != 2:
            continue
        target = targets[item['ordinal']]
        blob = checked(root, item['selected_file'], item['selected_sha256']).read_bytes()
        n, *_ = sparse.unpack(blob)
        if n != 32000 or len(blob) > n // 32:
            raise ValueError('Final2k winner does not meet its original complete byte cap')
        final.append(dict(ordinal=item['ordinal'], group=target['group'], split=target['split'],
                          kind=target['kind'], target=target, selected=item))
    if len(final) != 27 or set(manifest['stoi_eligible']['2']) - set(range(20)):
        raise ValueError('Original final2k/STOI membership changed')
    return manifest, final, dict(verified_original_pointers=verified, original_rounds=3,
        target_files=27, final_2k_cases=27, original_raw_paths_available=sum(Path(t['raw_reference_file']).is_file()
                                                                        for t in targets.values()),
        saved_target_bytes_used_unchanged=True, original_preprocessing_independently_rerun=False)


def measure_context(reference):
    from refine_sparse80_pulses import _measure, _band_context, _band_measure
    from speech_noise_objective import NoiseObjective
    from voice_character import track_pitch
    from standard_metrics import pwm_pcm16
    track = track_pitch(reference)
    objective = NoiseObjective(reference, track.period)
    band = _band_context(reference)
    def measure(pcm, speech):
        return _measure(reference, pcm, track, objective, speech)
    def bands(pcm):
        return dict(pcm16=_band_measure(band, pcm), pwm8=_band_measure(band, pwm_pcm16(pcm)))
    return measure, bands


def check_saved_metrics(saved, fresh):
    # Arithmetic/SSE/source-window identities must be exact. Derived float
    # objectives can differ with runtime versions; compare, record, never replace
    # the saved stream or target. The experiment's fresh baseline is protected.
    for domain in ('pcm16', 'pwm8'):
        for key in ('samples', 'reference_energy', 'error_energy'):
            if saved['metrics'][domain][key] != fresh['metrics'][domain][key]:
                raise ValueError('Fresh native baseline changes the saved source or waveform errors')
    for old, new in ((saved['voice'], fresh['voice'][0]), (saved['pwm_voice'], fresh['voice'][1])):
        for key in ('reference_period_frames', 'within_tolerance_frames', 'frames'):
            if old[key] != new[key]:
                raise ValueError('Fresh baseline changes the saved source-period membership')
    if saved['clipped_samples'] != fresh['clipped'][0]:
        raise ValueError('Fresh native baseline changes clipping')
    return dict(old_joint_delta=fresh['score'] - saved['score'],
                stoi_deltas={d: (fresh['metrics'][d]['stoi'] - saved['metrics'][d]['stoi']
                                 if fresh['metrics'][d]['stoi'] is not None and saved['metrics'][d]['stoi'] is not None else None)
                             for d in ('pcm16', 'pwm8')})


def prepare(args):
    root = args.campaign.resolve()
    out = private_output(args.output)
    if out.exists():
        raise ValueError('Prepare requires a fresh ignored directory')
    before = software()
    out.mkdir(parents=True)
    wall, cpu = time.perf_counter(), time.process_time()
    manifest, cases, validation = bind_campaign(root)
    write(out / 'freeze-private.json', dict(schema='lpx-sparse2-speech-freeze-v1', sources=before,
        runtime=runtime(), native_build=read(OUTPUT / 'build.json'), campaign=str(root),
        campaign_manifest_sha256=digest((root / 'campaign-private.json').read_bytes()),
        cases=cases, binding=validation, stoi_eligible=manifest['stoi_eligible']['2']))
    # Warm JIT on synthetic data; count this separately from baseline checks.
    synthetic = sparse.pack(320, [[3 + 5 * j for j in range(10)]], [(13, 37, 10)], [(0, 7)] * 4, 8192, 4096)
    warm = time.perf_counter()
    e.Context(synthetic)
    warm_seconds = time.perf_counter() - warm
    with NativeReceiver('common') as common, NativeReceiver('v5-only') as only:
        receiver = e.bridge_receiver(common, only)
        for case in cases:
            ordinal = case['ordinal']
            folder = out / ('case-%03d' % ordinal)
            folder.mkdir()
            target = checked(root, case['target']['target_file'], case['target']['target_sha256']).read_bytes()
            blob = checked(root, case['selected']['selected_file'], case['selected']['selected_sha256']).read_bytes()
            (folder / 'target.pcm16').write_bytes(target)
            (folder / 'baseline.lpx').write_bytes(blob)
            reference = np.frombuffer(target, dtype='<i2').copy()
            context = e.Context(blob)
            pcm, duty = e._oracle(receiver, blob, context.pcm)
            measure, bands = measure_context(reference)
            fresh = measure(pcm, ordinal < 20)
            saved = read(checked(root, case['selected']['metric_file'], case['selected']['metric_sha256']))
            metric_difference = check_saved_metrics(saved, fresh)
            (folder / 'baseline.pcm16').write_bytes(pcm.astype('<i2').tobytes())
            (folder / 'baseline.pwm8').write_bytes(duty.tobytes())
            write(folder / 'baseline-private.json', dict(binding=case, metrics=fresh, bands=bands(pcm),
                saved_metrics=saved, metric_difference=metric_difference,
                native_common_and_v5_only_pcm_pwm_exact=True, target_sha256=digest(target),
                baseline_sha256=digest(blob), samples=len(reference), bytes=len(blob)))
            print(json.dumps(dict(stage='baseline_verified', ordinal=ordinal)), flush=True)
    if software() != before:
        raise ValueError('Source changed during baseline preparation')
    write(out / 'prepared-private.json', dict(status='PASS', cases=27, binding=validation,
        warmup_seconds=warm_seconds, wall_seconds=time.perf_counter() - wall, cpu_seconds=time.process_time() - cpu,
        warmup_scope='Synthetic Context only; any metric JIT/cache loading remains in preparation time',
        cpu_scope='Python process only; excludes persistent WSL native receiver CPU',
        baseline_snapshot_samples=27 * 32000, independent_model_samples=27 * 32000,
        full_metric_evaluations=27, frequency_diagnostic_evaluations=54,
        frequency_diagnostic_unit='One _band_measure call for one output domain',
        native_requests_per_receiver=54, native_output_samples_both_receivers_domains=27 * 32000 * 4))
    print(json.dumps(dict(stage='prepared', cases=27, warmup_seconds=warm_seconds)), flush=True)


def frozen(out):
    freeze = read(out / 'freeze-private.json')
    if freeze['sources'] != software() or freeze['runtime'] != runtime():
        raise ValueError('Frozen experiment sources or runtime changed')
    if read(out / 'prepared-private.json')['status'] != 'PASS':
        raise ValueError('All protected baselines must pass before search')
    if read(OUTPUT / 'build.json') != freeze['native_build']:
        raise ValueError('Frozen native reference build changed')
    for case in freeze['cases']:
        folder = out / ('case-%03d' % case['ordinal'])
        if (digest((folder / 'target.pcm16').read_bytes()) != case['target']['target_sha256']
                or digest((folder / 'baseline.lpx').read_bytes()) != case['selected']['selected_sha256']):
            raise ValueError('Protected target or final-round3 baseline changed')
    return freeze


def save_candidate(folder, name, candidate):
    files = {name + '.lpx': candidate.blob, name + '.pcm16': candidate.pcm.astype('<i2').tobytes(),
             name + '.pwm8': candidate.pwm.tobytes()}
    for relative, payload in files.items():
        (folder / relative).write_bytes(payload)
    return {relative: digest(payload) for relative, payload in files.items()}


def run_case(out, case, receiver, freeze):
    wall, cpu = time.perf_counter(), time.process_time()
    ordinal = case['ordinal']
    folder = out / ('case-%03d' % ordinal)
    if (folder / 'complete-private.json').exists():
        raise ValueError('A case may be searched only once')
    baseline = read(folder / 'baseline-private.json')
    blob = (folder / 'baseline.lpx').read_bytes()
    reference = np.frombuffer((folder / 'target.pcm16').read_bytes(), dtype='<i2').copy()
    search_wall, search_cpu = time.perf_counter(), time.process_time()
    result = e.search(reference, blob, receiver)
    search_seconds, search_cpu_seconds = time.perf_counter() - search_wall, time.process_time() - search_cpu
    select_wall, select_cpu = time.perf_counter(), time.process_time()
    selections, journal = e.admit(reference, result, speech=ordinal < 20)
    admission_seconds, admission_cpu_seconds = time.perf_counter() - select_wall, time.process_time() - select_cpu
    if journal['baseline'] != baseline['metrics']:
        raise ValueError('Search admission changed the protected baseline metrics')
    measure, bands = measure_context(reference)
    artifacts = {}
    raw = {'exhaustive': result.raw}
    raw.update({'beam' + str(w): (values[0] if values else result.baseline)
                for w, values in result.control_shortlists.items()})
    # Every complete leaf stream is retained privately; waveform hashes record
    # its already-checked native outputs. Raw/final waveforms are retained too.
    leaf_rows = []
    regions = []
    for region in result.regions:
        pools = [dict(packet=p.packet, symbols=p.symbols, immediate_winner=p.immediate_winner,
                      tail_winner=p.tail_winner, immediate_losses=p.immediate_losses,
                      tail_losses=p.tail_losses) for p in region.pools]
        regions.append(dict(frame=region.frame, baseline_pcm_sse=region.baseline_pcm_sse, pools=pools,
            exhaustive_sse=region.exhaustive.pcm_sse,
            control_sse={str(w): c.pcm_sse for w, c in region.controls.items()},
            surviving_symbols=region.surviving_symbols))
        for leaf in region.leaves:
            name = 'frame-%03d-leaf-%03d.lpx' % (region.frame, leaf.ordinal)
            (folder / name).write_bytes(leaf.blob)
            artifacts[name] = digest(leaf.blob)
            leaf_rows.append(dict(file=name, sha256=artifacts[name], symbols=leaf.symbols,
                frame=region.frame, ordinal=leaf.ordinal, pcm_sse=leaf.pcm_sse,
                pcm_sha256=digest(leaf.pcm.astype('<i2').tobytes()), pwm_sha256=digest(leaf.pwm.tobytes())))
    variants = {}
    for topology, selected in selections.items():
        values = {}
        for kind, candidate in (('raw', raw[topology]), ('final', selected)):
            name = kind + '-' + topology
            artifacts.update(save_candidate(folder, name, candidate))
            metrics = journal['baseline'] if candidate.blob == blob else next(
                row['metrics'] for rows in journal['candidates'].values() for row in rows
                if row['sha256'] == digest(candidate.blob))
            if ordinal in freeze['stoi_eligible'] and any(metrics['metrics'][d]['stoi'] is None
                                                           for d in ('pcm16', 'pwm8')):
                raise ValueError('Original fixed STOI subset acquired a missing score')
            if len(candidate.blob) != len(blob):
                raise ValueError('Candidate changed actual complete bytes')
            fields, old = sparse.unpack(candidate.blob), sparse.unpack(blob)
            if fields[:3] != old[:3] or fields[4:] != old[4:]:
                raise ValueError('Candidate changed non-pulse decoder fields')
            values[kind] = dict(metrics=metrics, bands=bands(candidate.pcm),
                changed=candidate.blob != blob, pcm_changed_samples=int(np.count_nonzero(candidate.pcm != result.baseline.pcm)),
                pwm_changed_samples=int(np.count_nonzero(candidate.pwm != result.baseline.pwm)),
                region=candidate.region, symbols=candidate.symbols, sha256=digest(candidate.blob))
        variants[topology] = values
    actual = dict(result.counters)
    actual.update(baseline_snapshot_samples=len(reference),
        independent_model_samples=len(reference) * result.counters['full_model_checks'],
        native_requests_each_receiver=result.counters['native_oracle_calls'] * 2,
        native_output_samples_both_receivers_domains=result.counters['native_oracle_calls'] * len(reference) * 4,
        full_metric_evaluations=1 + sum(len(rows) for rows in journal['candidates'].values()),
        frequency_diagnostic_evaluations=1 + sum(len(rows) for rows in journal['candidates'].values()) + 16,
        frequency_diagnostic_unit='One _band_measure call for one output domain',
        retained_artifacts=len(artifacts))
    receipt = dict(schema='lpx-sparse2-complete-private-v1', status='PASS', ordinal=ordinal,
        group=case['group'], split=case['split'], kind=case['kind'], bytes=len(blob), samples=len(reference),
        source_freeze_sha256=digest(encoded(freeze)), input_binding=case,
        baseline=baseline, variants=variants, regions=regions, leaves=leaf_rows,
        admission=journal, counters=actual, artifacts=artifacts,
        search_seconds=search_seconds, search_cpu_seconds=search_cpu_seconds,
        admission_seconds=admission_seconds, admission_cpu_seconds=admission_cpu_seconds,
        wall_seconds=time.perf_counter() - wall, cpu_seconds=time.process_time() - cpu,
        cpu_scope='Python process only; excludes persistent WSL native receiver CPU',
        native_model_all_leaves_exact=True, same_actual_bytes=True, changed_only_original_pulse_bits=True)
    if software() != freeze['sources']:
        raise ValueError('Frozen source changed during search')
    write(folder / 'complete-private.json', receipt)
    # Atomic final pointer only after every stream, waveform and full receipt.
    write(folder / 'result-pointer-private.json', dict(receipt_file='complete-private.json',
        receipt_sha256=digest((folder / 'complete-private.json').read_bytes()),
        selected_file='final-exhaustive.lpx', selected_sha256=variants['exhaustive']['final']['sha256']))
    print(json.dumps(dict(stage='case_complete', ordinal=ordinal,
        exhaustive_changed=variants['exhaustive']['final']['changed'],
        raw_pcm_gain=baseline['metrics']['metrics']['pcm16']['error_energy'] - result.raw.pcm_sse,
        wall_seconds=receipt['wall_seconds'])), flush=True)


def numeric_summary(metrics, bands):
    """Public whitelist: no input/stream digest, symbols, identity or path."""
    score = dict(score=metrics['score'], pwm_joint_score=metrics['pwm_joint_score'],
                 pwm_voice_score=metrics['pwm_voice_score'], clipped=metrics['clipped'])
    score['waveform'] = {d: {k: metrics['metrics'][d][k] for k in
        ('samples', 'reference_energy', 'error_energy', 'ser_db', 'ser_status', 'stoi')} for d in ('pcm16', 'pwm8')}
    score['voice'] = [{k: v.get(k) for k in ('frames', 'reference_period_frames', 'within_tolerance_frames',
        'decoded_collapsed_active_frames', 'fixed_decoded_period_error_mean', 'relative_spectral_shape_rms_db_mean')}
        for v in metrics['voice']]
    score['pwm_noise'] = {k: metrics['pwm_noise'].get(k) for k in ('score',
        'balance_absolute_error_mean_with_missing_penalty', 'fine_shape_hellinger_mean',
        'candidate_off_harmonic_fraction_mean_observed')}
    score['frequency'] = {d: {k: bands[d][k] for k in
        ('band_error_totals', 'max_source_relative_frame_error')} for d in ('pcm16', 'pwm8')}
    return score


def public_case(receipt):
    variants = {}
    for topology, data in receipt['variants'].items():
        variants[topology] = {kind: dict(changed=row['changed'],
            pcm_changed_samples=row['pcm_changed_samples'], pwm_changed_samples=row['pwm_changed_samples'],
            **numeric_summary(row['metrics'], row['bands'])) for kind, row in data.items()}
    rejected = {}
    for topology, entries in receipt['admission']['candidates'].items():
        counts = Counter()
        for row in entries:
            for key, passed in row['floors'].items():
                if not passed:
                    counts[key] += 1
            if all(row['floors'].values()) and not row['selected_at_step']:
                counts['joint_objectives_or_already_better'] += 1
        rejected[topology] = dict(counts)
    return dict(ordinal=receipt['ordinal'], group=receipt['group'], split=receipt['split'],
        samples=receipt['samples'], bytes=receipt['bytes'], bitrate_bps=receipt['bytes'] * 64000 / receipt['samples'],
        baseline=numeric_summary(receipt['baseline']['metrics'], receipt['baseline']['bands']),
        variants=variants, rejection_counts=rejected, counters=receipt['counters'],
        regions=[dict(frame=r['frame'], exhaustive_sse=r['exhaustive_sse'], control_sse=r['control_sse'])
                 for r in receipt['regions']],
        search_seconds=receipt['search_seconds'], admission_seconds=receipt['admission_seconds'],
        wall_seconds=receipt['wall_seconds'], cpu_seconds=receipt['cpu_seconds'])


def aggregate(cases, selected, eligible):
    result = dict(cases=len(cases), encoded_bytes=sum(c['bytes'] for c in cases))
    for domain in ('pcm16', 'pwm8'):
        metrics = [selected(c)['waveform'][domain] for c in cases]
        power = sum(m['reference_energy'] for m in metrics)
        error = sum(m['error_energy'] for m in metrics)
        assessed = [(c, selected(c)['waveform'][domain]['stoi']) for c in cases if c['ordinal'] in eligible]
        if any(value is None or not math.isfinite(value) for _, value in assessed):
            raise ValueError('Fixed STOI membership cannot drop an unassessed score')
        result[domain] = dict(reference_energy=power, error_energy=error,
            summed_energy_ser_db=10 * math.log10(power / error) if power and error else None,
            mean_stoi=sum(v for _, v in assessed) / len(assessed) if assessed else None,
            stoi_assessed_cases=len(assessed), stoi_unassessed_cases=len(cases) - len(assessed))
    return result


def export(out, public):
    freeze = frozen(out)
    cases = []
    for case in freeze['cases']:
        folder = out / ('case-%03d' % case['ordinal'])
        pointer = folder / 'result-pointer-private.json'
        if not pointer.exists():
            continue
        p = read(pointer)
        receipt = read(checked(folder, p['receipt_file'], p['receipt_sha256']))
        if receipt['source_freeze_sha256'] != digest(encoded(freeze)):
            raise ValueError('Completed case has a different source freeze')
        for relative, expected in receipt['artifacts'].items():
            checked(folder, relative, expected)
        cases.append(public_case(receipt))
    groups = {}
    subsets = {'all': cases,
               **{name: [c for c in cases if c['split'] == name]
                  for name in ('tuning_speech', 'heldout_speech', 'negative_controls')},
               **{name: [c for c in cases if c['group'] == name] for name in set(summary.EXPECTED_GROUPS)}}
    eligible = set(freeze['stoi_eligible'])
    for name, subset in sorted(subsets.items()):
        groups[name] = dict(baseline=aggregate(subset, lambda c: c['baseline'], eligible),
            variants={topology: {kind: aggregate(subset, lambda c, t=topology, k=kind: c['variants'][t][k], eligible)
                       for kind in ('raw', 'final')} for topology in ('exhaustive', 'beam1', 'beam2', 'beam4')},
            changed={topology: sum(c['variants'][topology]['final']['changed'] for c in subset)
                     for topology in ('exhaustive', 'beam1', 'beam2', 'beam4')})
    report = dict(schema='lpx-sparse2-anonymous-comparison-v1', completed_cases=len(cases),
        expected_cases=27, pilot_is_not_additional_case=True, cases=cases, groups=groups,
        implementation_sources=freeze['sources'], runtime=freeze['runtime'],
        binding_validation=freeze['binding'], original_stoi_eligible_ordinals=freeze['stoi_eligible'],
        preparation=read(out / 'prepared-private.json'),
        cpu_scope='Reported CPU seconds are Python-process only; total wall time includes native IPC/decoding',
        scope='Fixed one-pass host research against exact saved final-round3 targets/streams; no listening or new AVR claim')
    # Preparation contains only counts/time/booleans. Never copy the private
    # freeze, per-case journals or artifact dictionaries into public output.
    if public:
        public = public.resolve()
        public.relative_to(HERE.resolve())
        write(public, report)
    return report


def main(args):
    initialize(args.packages)
    out = private_output(args.output)
    try:
        if args.command == 'prepare':
            if args.campaign is None:
                raise ValueError('Campaign binding is required for preparation')
            prepare(args)
            return 0
        freeze = frozen(out)
        if args.command in ('pilot', 'all'):
            cases = freeze['cases']
            if args.command == 'pilot':
                cases = [next(c for c in cases if c['split'] == 'tuning_speech')]
            with NativeReceiver('common') as common, NativeReceiver('v5-only') as only:
                receiver = e.bridge_receiver(common, only)
                for case in cases:
                    if (out / ('case-%03d' % case['ordinal']) / 'result-pointer-private.json').exists():
                        continue  # Reuse the exact verified pilot, never search twice.
                    run_case(out, case, receiver, freeze)
        result = export(out, args.public)
        if args.command == 'all' and result['completed_cases'] != 27:
            raise ValueError('A full comparison requires every original case')
        print(json.dumps(dict(stage='exported', completed_cases=result['completed_cases'])), flush=True)
        return 0
    except BaseException as error:
        if out.exists():
            (out / 'infrastructure-error-private.log').write_text(traceback.format_exc(), encoding='utf-8')
        print(json.dumps(dict(status='INFRASTRUCTURE_STOP', exception=type(error).__name__)), flush=True)
        return 2


if __name__ == '__main__':
    sys.exit(main(PARSER.parse_args()))

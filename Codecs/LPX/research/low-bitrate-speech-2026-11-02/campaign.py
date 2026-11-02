"""Private, resumable coordination of the registered LPX follow-up rounds.

This module does not publish or merge anything. Quality admission belongs to
RoundAdmission. Four OS-held worker slots cap numerical workers, including
workers surviving a controller restart. Immutable records bind every result.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
import uuid

from campaign_records import Lease, available, current, digest, encoded, file_digest, immutable, immutable_bytes, pid_alive, read
from campaign_summary import EXPECTED_GROUPS, HELDOUT, same_anchor, split, summarize, validate_metrics, verify_transition

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ACTIVE = ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
SPECTRAL = HERE.parent / 'low-bitrate-spectral-round-2026-11-02'
OPERATORS = ('pitch_proposals', 'spectral_round', 'beam_innovations')
TESTS = ((HERE, 'test_round_admission.py'), (HERE, 'test_beam_innovations.py'),
         (SPECTRAL, 'test_spectral_round.py'), (HERE, 'test_campaign.py'))
PROTOCOLS = ('PROTOCOL.md', 'PITCH_PROTOCOL.md', 'SPECTRAL_PROTOCOL.md',
             'BEAM_PROTOCOL.md', 'ITERATION_PROTOCOL.md', 'CAMPAIGN.md')


def utc():
    return datetime.now(timezone.utc).isoformat()


def private_output(path):
    path = Path(path).resolve()
    path.relative_to((ROOT / 'build').resolve())
    if path == (ROOT / 'build').resolve():
        raise ValueError('Use a dedicated ignored campaign directory')
    return path


def source_snapshot():
    files = list((ACTIVE / 'tools').glob('*.py'))
    files += [p for p in (ACTIVE / 'src').iterdir() if p.is_file()]
    files += list(HERE.glob('*.py')) + list(SPECTRAL.glob('*.py'))
    files += [HERE / name for name in PROTOCOLS] + [SPECTRAL / 'PROTOCOL.md']
    return {p.relative_to(ROOT).as_posix(): file_digest(p) for p in sorted(set(files))}


def assert_sources(manifest):
    if manifest['sources'] != source_snapshot():
        raise ValueError('Pinned implementation or registered protocol changed; do not mix revisions')
    for value in manifest['libraries'].values():
        if file_digest(value['path']) != value['sha256']:
            raise ValueError('A pinned native reference library changed')
    if (file_digest(manifest['library_receipt']) != manifest['library_receipt_sha256']
            or file_digest(Path(manifest['baseline']) / 'binding-private.json') != manifest['baseline_binding_sha256']):
        raise ValueError('Native provenance or the original baseline binding changed')
    for value in manifest['initial']:
        if (file_digest(value['baseline_receipt']) != value['baseline_receipt_sha256']
                or file_digest(value['baseline_report']) != value['baseline_report_sha256']):
            raise ValueError('A pinned final baseline receipt or report changed')
    for value in manifest['targets']:
        if file_digest(value['raw_reference_file']) != value['raw_reference_file_sha256']:
            raise ValueError('A pinned original source file changed')


def baseline_records(baseline):
    baseline = private_output(baseline)
    binding = read(baseline / 'binding-private.json')
    cases = binding['cases']
    if len(cases) != 27 or binding['level_policy'] != 'auto-quiet':
        raise ValueError('Expected the registered complete round0 corpus and level policy')
    result = []
    for ordinal, case in enumerate(cases):
        if (case['ordinal'] != ordinal or case['samples'] != 32000
                or case['group'] != EXPECTED_GROUPS[ordinal]
                or case['kind'] != ('speech' if ordinal < 20 else 'music')):
            raise ValueError('Round0 grouping or sample binding differs from the registered corpus')
        for kbps in (2, 3):
            path = baseline / ('case-%03d' % ordinal) / ('rate-%d-complete-private.json' % kbps)
            if not path.is_file():
                raise ValueError('All 54 round0 PASS receipts are required before campaign preparation')
            row = read(path)
            if (row.get('status') != 'PASS' or row.get('ordinal') != ordinal or row.get('kbps') != kbps
                    or row.get('samples') != 32000 or row.get('group') != case['group']
                    or row.get('kind') != case['kind'] or not row.get('source_frozen')
                    or not row.get('common_and_v5_only_native_exact')):
                raise ValueError('A merely claimed, running, failed or unbound round0 job is not complete')
            validate_metrics(row['selected'])
            result.append((case, row, path))
    return baseline, binding, result


def dependencies():
    for variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[variable] = '1'
    for path in (ACTIVE / 'tools', HERE, SPECTRAL):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    import numpy as np
    import soundfile as sf
    from batch_decoder import BatchDecoder
    from voice_input import quantize_target
    return np, sf, BatchDecoder, quantize_target


def runtime_binding():
    import platform
    from importlib.metadata import version
    return dict(python=sys.version, system=platform.system(), machine=platform.machine(),
                packages={name: version(name) for name in ('numpy', 'scipy', 'numba', 'soundfile', 'pystoi')})


def validate(baseline, output):
    """Explicit post-baseline unit gate; never triggered by prepare or control."""
    baseline_records(baseline)
    output = private_output(output)
    output.mkdir(parents=True, exist_ok=False)
    before = source_snapshot()
    for path in before:
        if path.endswith('.py'):
            ast.parse((ROOT / path).read_text(encoding='utf-8'))
    env = os.environ.copy()
    for variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS', 'MKL_NUM_THREADS'):
        env[variable] = '1'
    env['NUMBA_CACHE_DIR'] = str(output / 'numba-cache')
    checks = []
    for index, (folder, pattern) in enumerate(TESTS):
        if not (folder / pattern).is_file():
            raise ValueError('A registered unit suite is missing')
        command = [sys.executable, '-m', 'unittest', 'discover', '-s', str(folder), '-p', pattern]
        started = time.perf_counter()
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True)
        log = output / ('check-%02d-private.log' % index)
        immutable_bytes(log, result.stdout + result.stderr)
        count = re.search(r'Ran\s+([0-9]+)\s+tests?', result.stderr.decode('utf-8', errors='replace'))
        checks.append(dict(test=pattern, returncode=result.returncode, tests=int(count[1]) if count else 0,
                           wall_seconds=time.perf_counter() - started, log_sha256=file_digest(log)))
        if result.returncode or not checks[-1]['tests']:
            immutable(output / 'checks-failed-private.json', dict(checks=checks, passed=False))
            raise ValueError('A registered unit check failed; no campaign launch is authorized')
    if before != source_snapshot():
        raise ValueError('Implementation changed while unit checks were running')
    receipt = dict(schema='lpx-campaign-unit-gate-v1', passed=True, sources=before,
                   checks=checks, runtime=runtime_binding(), created_utc=utc())
    immutable(output / 'validation-private.json', receipt)
    return receipt


def prepare(baseline, output, library_receipt, validation):
    baseline, binding, rows = baseline_records(baseline)
    validation = Path(validation).resolve()
    unit = read(validation)
    sources = source_snapshot()
    if (unit.get('schema') != 'lpx-campaign-unit-gate-v1' or not unit.get('passed')
            or unit.get('sources') != sources or len(unit.get('checks', [])) != len(TESTS)
            or any(value['returncode'] or not value.get('tests') for value in unit['checks'])):
        raise ValueError('Current syntax/unit evidence is required before campaign preparation')
    native = read(library_receipt)
    if (native.get('schema') != 'lpx-native-reference-pins-private-v1'
            or not isinstance(native.get('verification'), str) or not native['verification']):
        raise ValueError('Expected the supplied native reference provenance receipt')
    libraries = native['libraries']
    for name, compact_only in (('common', False), ('v5_only', True)):
        value = libraries[name]
        if (not value['speech'] or not value['speech_compact'] or value['assembly']
                or value['compact_only'] != compact_only or file_digest(value['path']) != value['sha256']):
            raise ValueError('Expected the verified real common and v5-only portable native libraries')
    output = private_output(output)
    output.mkdir(parents=True, exist_ok=False)
    np, sf, BatchDecoder, quantize_target = dependencies()
    if runtime_binding() != unit['runtime']:
        raise ValueError('Numerical runtime differs from the validated environment')
    # Load the real ctypes ABIs now; workers perform every full-output native
    # comparison again through RoundAdmission. No speculative native rebuild.
    BatchDecoder(Path(libraries['common']['path']))
    BatchDecoder(Path(libraries['v5_only']['path']))
    initial, targets, eligible = [], {}, {'2': [], '3': []}
    for case, receipt, receipt_path in rows:
        ordinal, kbps = receipt['ordinal'], receipt['kbps']
        source = Path(binding['corpus']) / case['id'] / 'reference.wav'
        if ordinal not in targets:
            raw, rate = sf.read(source, dtype='int16')
            if rate != 8000 or raw.shape != (32000,) or digest(raw.astype('<i2').tobytes()) != case['reference_sha256']:
                raise ValueError('The exact original PCM source binding changed')
            level = receipt['level']
            exponent = level['gain_power2_exponent']
            if (level['policy'] != 'auto-quiet' or isinstance(exponent, bool) or not isinstance(exponent, int)
                    or not 0 <= exponent <= 16 or level['gain'] != 1 << exponent):
                raise ValueError('The round0 declared whole-input gain is invalid')
            target, clipped = quantize_target(raw.astype(np.int64), level)
            if clipped:
                raise ValueError('The declared round0 target unexpectedly clips')
            target_file = 'references/case-%03d.pcm16' % ordinal
            target_sha = immutable_bytes(output / target_file, target.astype('<i2').tobytes())
            targets[ordinal] = dict(ordinal=ordinal, samples=32000, sample_hz=8000,
                raw_reference_file=str(source.resolve()), raw_reference_sha256=case['reference_sha256'],
                raw_reference_file_sha256=file_digest(source),
                target_file=target_file, target_sha256=target_sha, level=level,
                group=case['group'], kind=case['kind'], split=split(ordinal))
        if receipt['level'] != targets[ordinal]['level']:
            raise ValueError('The two budgets used different declared round0 targets')
        candidate_dir = receipt_path.parent / ('rate-%d' % kbps)
        report_file = candidate_dir / 'report-private.json'
        report = read(report_file)
        selected = report['candidates'][report['selected_id']]
        blob_path = candidate_dir / ('candidate-%03d.lpx' % report['selected_id'])
        blob = blob_path.read_bytes()
        if (selected != receipt['selected'] or report['samples'] != 32000
                or len(blob) != receipt['bytes'] or len(blob) != selected['file_bytes']
                or len(blob) > 32000 * kbps // 64 or report['level'] != receipt['level']):
            raise ValueError('The completed round0 stream, metric and level records are incoherent')
        key = 'case-%03d-rate-%d' % (ordinal, kbps)
        selected_file, metric_file = 'initial/' + key + '.lpx', 'initial/' + key + '-private.json'
        stream_sha = immutable_bytes(output / selected_file, blob)
        metric_sha = immutable(output / metric_file, selected)
        initial.append(dict(job_id=key, ordinal=ordinal, kbps=kbps, selected_file=selected_file,
            selected_sha256=stream_sha, metric_file=metric_file, metric_sha256=metric_sha,
            baseline_receipt=str(receipt_path), baseline_receipt_sha256=file_digest(receipt_path),
            baseline_report=str(report_file),
            baseline_report_sha256=file_digest(report_file)))
        if ordinal < 20 and selected['metrics']['pwm8']['stoi'] is not None:
            eligible[str(kbps)].append(ordinal)
    manifest = dict(schema='lpx-followup-campaign-v1', created_utc=utc(), sources=sources,
        validation_file=str(validation), validation_sha256=file_digest(validation),
        runtime=unit['runtime'], python=str(Path(sys.executable).resolve()), libraries=libraries,
        library_receipt=str(Path(library_receipt).resolve()), library_receipt_sha256=file_digest(library_receipt),
        native_receipt_verification_scope='Textual provenance only; 54 final baseline PASS receipts and fresh common/v5-only RoundAdmission comparisons supply numerical evidence',
        baseline=str(baseline), baseline_binding_sha256=file_digest(baseline / 'binding-private.json'),
        targets=list(targets.values()), initial=initial, stoi_eligible=eligible,
        operators=list(OPERATORS), max_workers=4,
        stopping=dict(completed_consecutive_no_clear_rounds=3, pwm_stoi=.01, pwm_ser_db=.3,
                      pwm_source_period_percentage_points=5), scope='Private local research only; no publication or main merge')
    if sources != source_snapshot():
        raise ValueError('Implementation changed while preparing the campaign')
    immutable(output / 'campaign-private.json', manifest)
    return manifest


def load_campaign(output):
    output = private_output(output)
    manifest = read(output / 'campaign-private.json')
    if (manifest['schema'] != 'lpx-followup-campaign-v1' or manifest['max_workers'] != 4
            or tuple(manifest['operators']) != OPERATORS or len(manifest['initial']) != 54):
        raise ValueError('Unrecognized campaign manifest')
    assert_sources(manifest)
    if file_digest(manifest['validation_file']) != manifest['validation_sha256']:
        raise ValueError('The validation evidence changed')
    if runtime_binding() != manifest['runtime']:
        raise ValueError('The pinned numerical runtime changed')
    return output, manifest


def authorize(output, baseline_pids, confirmed_exit):
    """Root review is explicit; this is not inferred user consent to publish."""
    output, manifest = load_campaign(output)
    baseline_records(manifest['baseline'])
    if not confirmed_exit or any(pid_alive(pid) for pid in baseline_pids):
        raise ValueError('Root must verify baseline worker exit before enabling the four campaign slots')
    activation = dict(schema='lpx-campaign-local-activation-v1', created_utc=utc(),
        manifest_sha256=file_digest(output / 'campaign-private.json'),
        baseline_worker_pids=list(baseline_pids), baseline_exit_verified=True,
        root_review_complete=True, max_workers=4, publication_authorized=False)
    immutable(output / 'activation-private.json', activation)
    return activation


def activation(output, manifest):
    value = read(output / 'activation-private.json')
    if (value['manifest_sha256'] != file_digest(output / 'campaign-private.json')
            or not value.get('root_review_complete') or not value.get('baseline_exit_verified')):
        raise ValueError('Local root-reviewed activation and exited baseline workers are required')
    baseline_records(manifest['baseline'])


def checked_file(output, relative, expected):
    path = (output / relative).resolve()
    path.relative_to(output)
    if file_digest(path) != expected:
        raise ValueError('A campaign input or completed result changed')
    return path


def recover_ledger(output, manifest):
    """Rebuild state only from complete immutable round commits, not ledger.json."""
    manifest_sha = file_digest(output / 'campaign-private.json')
    previous, count, selected, completed = manifest_sha, 0, manifest['initial'], 0
    while True:
        folder = output / 'rounds' / ('round-%04d' % (completed + 1))
        commit_file = folder / 'commit-private.json'
        if not commit_file.exists():
            break
        if count >= 3:
            raise ValueError('A round was appended after the actual stopping condition')
        commit = read(commit_file)
        if (commit['manifest_sha256'] != manifest_sha or commit['previous_commit_sha256'] != previous
                or commit['round'] != completed + 1 or commit['operator'] != OPERATORS[completed % 3]
                or len(commit['selected']) != 54):
            raise ValueError('Broken immutable campaign round chain')
        prior = dict(completed_rounds=completed, consecutive_no_clear=count,
                     previous_commit_sha256=previous, selected=selected)
        plan_file = folder / 'plan-private.json'
        if not plan_file.is_file() or file_digest(plan_file) != commit['plan_sha256']:
            raise ValueError('The committed immutable round plan changed')
        plan = read(plan_file)
        if plan != make_round_plan(output, manifest, prior):
            raise ValueError('The recovered round plan does not use the immediately prior selected inputs')
        summary_file = checked_file(output, commit['summary_file'], commit['summary_sha256'])
        summary = read(summary_file)
        expected = 0 if summary['clear_numerical_gain'] else count + 1
        if (summary['completed_jobs'] != 54 or summary['previous_consecutive_no_clear'] != count
                or summary['consecutive_no_clear'] != expected
                or summary['stop_condition_met'] != (expected >= 3)):
            raise ValueError('A round summary changed the preregistered stopping transition')
        keys = {(item['ordinal'], item['kbps']) for item in commit['selected']}
        if keys != {(i, k) for i in range(27) for k in (2, 3)}:
            raise ValueError('A committed round does not contain 54 unique corpus jobs')
        results = []
        by_key = {(item['ordinal'], item['kbps']): item for item in commit['selected']}
        for job in plan['jobs']:
            item = by_key[job['ordinal'], job['kbps']]
            checked_file(output, item['selected_file'], item['selected_sha256'])
            checked_file(output, item['metric_file'], item['metric_sha256'])
            receipt_file = checked_file(output, item['receipt_file'], item['receipt_sha256'])
            receipt = validate_success(output, manifest, plan_file, job, receipt_file)
            if any(receipt[key] != item[key] for key in ('selected_file', 'selected_sha256', 'metric_file', 'metric_sha256')):
                raise ValueError('The committed selection does not match its bound completion receipt')
            results.append(receipt)
        if summary != round_summary(results, manifest, plan, count):
            raise ValueError('The recovered stopping summary does not match all 54 verified full-output transitions')
        selected, previous, count = commit['selected'], file_digest(commit_file), expected
        completed += 1
    state = dict(schema='lpx-followup-ledger-v1', completed_rounds=completed,
        consecutive_no_clear=count, stop_condition_met=count >= 3,
        previous_commit_sha256=previous, selected=selected)
    current(output / 'ledger-private.json', state)
    return state


def make_round_plan(output, manifest, ledger):
    number = ledger['completed_rounds'] + 1
    targets = {value['ordinal']: value for value in manifest['targets']}
    jobs = []
    for previous in ledger['selected']:
        ordinal, kbps = previous['ordinal'], previous['kbps']
        target = targets[ordinal]
        jobs.append(dict(job_id=previous['job_id'], ordinal=ordinal, kbps=kbps,
            kind=target['kind'], group=target['group'], split=target['split'], samples=target['samples'],
            target_file=target['target_file'], target_sha256=target['target_sha256'],
            input_file=previous['selected_file'], input_sha256=previous['selected_sha256'],
            input_metric_file=previous['metric_file'], input_metric_sha256=previous['metric_sha256']))
    return dict(schema='lpx-followup-round-plan-v1', round=number,
        operator=OPERATORS[(number - 1) % 3], manifest_sha256=file_digest(output / 'campaign-private.json'),
        previous_commit_sha256=ledger['previous_commit_sha256'], jobs=jobs)


def round_plan(output, manifest, ledger):
    value = make_round_plan(output, manifest, ledger)
    folder = output / 'rounds' / ('round-%04d' % value['round'])
    path = folder / 'plan-private.json'
    immutable(path, value)
    return folder, value


def job_folder(folder, job):
    return folder / 'jobs' / job['job_id']


def validate_success(output, manifest, plan_file, job, path):
    value = read(path)
    claim_file = path.parent / 'claim-private.json'
    claim = read(claim_file)
    if (value.get('status') != 'PASS' or value.get('manifest_sha256') != file_digest(output / 'campaign-private.json')
            or value.get('plan_sha256') != file_digest(plan_file) or value.get('job_sha256') != digest(encoded(job))
            or value['input_sha256'] != job['input_sha256'] or value['target_sha256'] != job['target_sha256']
            or value['claim_id'] != claim['claim_id'] or value['claim_sha256'] != file_digest(claim_file)):
        raise ValueError('A completion receipt is not bound to this exact round job')
    selected_path = checked_file(output, value['selected_file'], value['selected_sha256'])
    report = read(checked_file(output, value['report_file'], value['report_sha256']))
    metric = read(checked_file(output, value['metric_file'], value['metric_sha256']))
    previous = read(checked_file(output, job['input_metric_file'], job['input_metric_sha256']))
    previous_blob = checked_file(output, job['input_file'], job['input_sha256']).read_bytes()
    selected_blob = selected_path.read_bytes()
    expected_prefix = b'L4HY\x08\x0f' if job['kbps'] == 2 else b'L4HY\x05\x04'
    if (selected_blob[:6] != expected_prefix or selected_blob[12:16] != previous_blob[12:16]
            or int.from_bytes(selected_blob[8:12], 'little') != job['samples']
            or int.from_bytes(selected_blob[6:8], 'little') != 8000
            or len(selected_blob) != metric['file_bytes'] or len(selected_blob) > job['samples'] * job['kbps'] // 64
            or value['changed'] != (value['selected_sha256'] != job['input_sha256'])
            or report['selected_differs_from_incumbent'] != value['changed']):
        raise ValueError('A completed stream changed its cap, header filters, format or sample geometry')
    if (report['candidates'][report['selected_id']] != metric or value['after'] != metric
            or value['before'] != previous
            or any(value[key] != job[key] for key in ('job_id', 'ordinal', 'kbps', 'kind', 'group'))
            or not value.get('source_bindings_verified') or not value.get('native_common_and_v5_only_pcm_pwm_exact')):
        raise ValueError('Completed stream and immutable selected metrics disagree')
    same_anchor(previous, report['candidates'][0])
    verify_transition(previous, metric)
    return value


def successful(output, manifest, plan_file, job):
    directory = job_folder(plan_file.parent, job)
    found = []
    for path in sorted(directory.glob('attempt-*/complete-private.json')):
        found.append((path, validate_success(output, manifest, plan_file, job, path)))
    if not found:
        return None
    if len({value['selected_sha256'] for _, value in found}) != 1:
        raise ValueError('Repeated exact jobs produced different completed outputs; audit before proceeding')
    return found[0]


def still_running(directory):
    if not available(directory / 'job.lock'):
        return True
    for attempt in directory.glob('attempt-*'):
        if (attempt / 'complete-private.json').exists() or (attempt / 'failure-private.json').exists():
            continue
        for name in ('started-private.json', 'launched-private.json'):
            path = attempt / name
            if path.exists() and pid_alive(read(path)['pid']):
                return True
    return False


def create_claim(output, manifest, plan_file, job, slot, retry):
    directory = job_folder(plan_file.parent, job)
    directory.mkdir(parents=True, exist_ok=True)
    attempts = sorted(path for path in directory.glob('attempt-*') if path.is_dir())
    failed_or_incomplete = [path for path in attempts if not (path / 'not-run-private.json').exists()]
    if failed_or_incomplete and not retry:
        raise ValueError('An incomplete or failed prior attempt requires explicit root-reviewed retry')
    number = max([int(path.name.split('-')[1]) for path in attempts], default=-1) + 1
    attempt = directory / ('attempt-%04d' % number)
    attempt.mkdir()
    claim = dict(schema='lpx-followup-job-claim-v1', claim_id=uuid.uuid4().hex,
        created_utc=utc(), owner_pid=os.getpid(), slot=slot, job_id=job['job_id'],
        manifest_sha256=file_digest(output / 'campaign-private.json'),
        plan_sha256=file_digest(plan_file), job_sha256=digest(encoded(job)))
    immutable(attempt / 'claim-private.json', claim)
    return attempt, claim


def worker(output, plan_file, job_id, attempt, slot):
    output = private_output(output)
    plan_file, attempt = Path(plan_file).resolve(), Path(attempt).resolve()
    plan_file.relative_to(output)
    attempt.relative_to(output)
    if slot not in range(4):
        raise ValueError('Worker slots are exactly zero through three')
    # Acquire both leases before numerical imports/JIT/native work. Workers
    # surviving a controller restart still count against these four slots.
    slot_lease = Lease(output / 'slots' / ('slot-%d.lock' % slot))
    job_lease = Lease(attempt.parent / 'job.lock')
    if not slot_lease.acquire():
        immutable(attempt / 'not-run-private.json', dict(status='SLOT_BUSY'))
        return 3
    if not job_lease.acquire():
        slot_lease.release()
        immutable(attempt / 'not-run-private.json', dict(status='JOB_BUSY'))
        return 3
    wall, cpu = time.perf_counter(), time.process_time()
    try:
        output, manifest = load_campaign(output)
        activation(output, manifest)
        plan = read(plan_file)
        if (plan.get('schema') != 'lpx-followup-round-plan-v1' or plan.get('round', 0) < 1
                or plan.get('operator') != OPERATORS[(plan['round'] - 1) % 3]
                or plan.get('manifest_sha256') != file_digest(output / 'campaign-private.json')
                or len(plan.get('jobs', [])) != 54):
            raise ValueError('Worker received an unregistered operator or round plan')
        job = next(value for value in plan['jobs'] if value['job_id'] == job_id)
        claim = read(attempt / 'claim-private.json')
        if (claim['slot'] != slot or claim['job_id'] != job_id
                or claim['manifest_sha256'] != file_digest(output / 'campaign-private.json')
                or claim['plan_sha256'] != file_digest(plan_file) or claim['job_sha256'] != digest(encoded(job))):
            raise ValueError('Worker launch does not match its immutable exclusive claim')
        immutable(attempt / 'started-private.json', dict(pid=os.getpid(), created_utc=utc(), claim_id=claim['claim_id']))
        np, _, BatchDecoder, _ = dependencies()
        if runtime_binding() != manifest['runtime']:
            raise ValueError('Numerical runtime changed between preparation and worker execution')
        target_path = checked_file(output, job['target_file'], job['target_sha256'])
        target = np.frombuffer(target_path.read_bytes(), dtype='<i2').copy()
        if target.shape != (32000,):
            raise ValueError('The complete prepared target geometry changed')
        target.flags.writeable = False
        source = next(value for value in manifest['targets'] if value['ordinal'] == job['ordinal'])
        import soundfile as sf
        raw, rate = sf.read(source['raw_reference_file'], dtype='int16')
        if rate != 8000 or digest(raw.astype('<i2').tobytes()) != source['raw_reference_sha256']:
            raise ValueError('The original source binding changed during the campaign')
        incumbent = checked_file(output, job['input_file'], job['input_sha256']).read_bytes()
        before = read(checked_file(output, job['input_metric_file'], job['input_metric_sha256']))
        common = BatchDecoder(Path(manifest['libraries']['common']['path']))
        only = BatchDecoder(Path(manifest['libraries']['v5_only']['path']))
        operator = importlib.import_module(plan['operator'])
        numerical_output = attempt / 'admission'
        selected, _, report = operator.run(target, incumbent, numerical_output, common, only, speech=job['kind'] == 'speech')
        from round_admission import recover_best
        recovered, after = recover_best(numerical_output)
        if selected != recovered or after != report['candidates'][report['selected_id']]:
            raise ValueError('The authoritative best pointer differs from the completed operator result')
        same_anchor(before, report['candidates'][0])
        verify_transition(before, after)
        if digest(incumbent) != job['input_sha256'] or digest(target.astype('<i2').tobytes()) != job['target_sha256']:
            raise ValueError('An operator modified its protected target or incumbent')
        assert_sources(manifest)
        relative = lambda path: path.relative_to(output).as_posix()
        selected_path = numerical_output / ('candidate-%03d.lpx' % report['selected_id'])
        metric_path = numerical_output / ('candidate-%03d-private.json' % report['selected_id'])
        report_path = numerical_output / 'report-private.json'
        receipt = dict(schema='lpx-followup-completion-v1', status='PASS', claim_id=claim['claim_id'],
            claim_sha256=file_digest(attempt / 'claim-private.json'),
            manifest_sha256=claim['manifest_sha256'], plan_sha256=claim['plan_sha256'], job_sha256=claim['job_sha256'],
            job_id=job_id, ordinal=job['ordinal'], kbps=job['kbps'], kind=job['kind'], group=job['group'],
            target_sha256=job['target_sha256'], input_sha256=job['input_sha256'],
            selected_file=relative(selected_path), selected_sha256=file_digest(selected_path),
            metric_file=relative(metric_path), metric_sha256=file_digest(metric_path),
            report_file=relative(report_path), report_sha256=file_digest(report_path), before=before, after=after,
            changed=selected != incumbent, actual_work_totals=report['actual_work_totals'],
            wall_seconds=time.perf_counter() - wall, cpu_seconds=time.process_time() - cpu,
            source_bindings_verified=True, native_common_and_v5_only_pcm_pwm_exact=True)
        immutable(attempt / 'complete-private.json', receipt)
        return 0
    except BaseException as error:
        immutable_bytes(attempt / 'exception-private.log', traceback.format_exc().encode('utf-8'))
        immutable(attempt / 'failure-private.json', dict(schema='lpx-followup-infrastructure-failure-v1',
            status='INFRA_FAILED', exception=type(error).__name__,
            wall_seconds=time.perf_counter() - wall, cpu_seconds=time.process_time() - cpu,
            counts_as_completed_quality_round=False))
        return 2
    finally:
        job_lease.release()
        slot_lease.release()


def round_summary(receipts, manifest, plan, previous_count):
    records = [{key: row[key] for key in ('status', 'ordinal', 'kbps', 'group', 'before', 'after', 'changed')}
               for row in receipts]
    summary = summarize(records, manifest['stoi_eligible'], previous_count)
    summary.update(round=plan['round'], operator=plan['operator'])
    summary['work_totals'] = {}
    summary['wall_seconds_sum'] = summary['cpu_seconds_sum'] = 0.
    for row in receipts:
        summary['wall_seconds_sum'] += row['wall_seconds']
        summary['cpu_seconds_sum'] += row['cpu_seconds']
        for key, value in row['actual_work_totals'].items():
            summary['work_totals'][key] = summary['work_totals'].get(key, 0) + value
    return summary


def commit_round(output, manifest, ledger, folder, plan):
    results, selected = [], []
    for job in plan['jobs']:
        result = successful(output, manifest, folder / 'plan-private.json', job)
        if result is None:
            raise ValueError('All 54 final PASS receipts are required to commit a quality round')
        path, row = result
        results.append(row)
        selected.append(dict(job_id=job['job_id'], ordinal=job['ordinal'], kbps=job['kbps'],
            selected_file=row['selected_file'], selected_sha256=row['selected_sha256'],
            metric_file=row['metric_file'], metric_sha256=row['metric_sha256'],
            receipt_file=path.relative_to(output).as_posix(), receipt_sha256=file_digest(path)))
    summary = round_summary(results, manifest, plan, ledger['consecutive_no_clear'])
    summary_file = folder / 'anonymous-summary.json'
    immutable(summary_file, summary)
    commit = dict(schema='lpx-followup-round-commit-v1', round=plan['round'], operator=plan['operator'],
        manifest_sha256=file_digest(output / 'campaign-private.json'), previous_commit_sha256=ledger['previous_commit_sha256'],
        plan_sha256=file_digest(folder / 'plan-private.json'),
        summary_file=summary_file.relative_to(output).as_posix(), summary_sha256=file_digest(summary_file), selected=selected)
    immutable(folder / 'commit-private.json', commit)
    return recover_ledger(output, manifest)


def control(output, *, max_rounds=None, retry=False, poll_seconds=5.):
    output, manifest = load_campaign(output)
    activation(output, manifest)
    if max_rounds is not None and max_rounds < 1 or not 0 < poll_seconds <= 60:
        raise ValueError('Invalid bounded controller invocation')
    with Lease(output / 'controller.lock'):
        ledger = recover_ledger(output, manifest)
        starting = ledger['completed_rounds']
        children = {}
        while not ledger['stop_condition_met']:
            if max_rounds is not None and ledger['completed_rounds'] - starting >= max_rounds:
                return ledger
            assert_sources(manifest)
            folder, plan = round_plan(output, manifest, ledger)
            plan_file = folder / 'plan-private.json'
            finished = {}
            launched_here = set()
            while len(finished) != 54:
                assert_sources(manifest)
                for slot, (process, attempt) in list(children.items()):
                    code = process.poll()
                    if code is None:
                        continue
                    del children[slot]
                    if code and code != 3 and not (attempt / 'failure-private.json').exists():
                        immutable(attempt / 'failure-private.json', dict(status='PROCESS_EXIT', exit_code=code,
                            counts_as_completed_quality_round=False))
                finished = {job['job_id']: value for job in plan['jobs']
                            if (value := successful(output, manifest, plan_file, job)) is not None}
                pending = [job for job in plan['jobs'] if job['job_id'] not in finished]
                for job in pending:
                    directory = job_folder(folder, job)
                    if still_running(directory):
                        continue
                    slots = [slot for slot in range(4) if slot not in children
                             and available(output / 'slots' / ('slot-%d.lock' % slot))]
                    if not slots:
                        break
                    slot = slots[0]
                    attempt, _ = create_claim(output, manifest, plan_file, job, slot,
                        retry and job['job_id'] not in launched_here)
                    command = [manifest['python'], str(Path(__file__).resolve()), 'worker', str(output),
                        '--plan', str(plan_file), '--job', job['job_id'], '--attempt', str(attempt), '--slot', str(slot)]
                    env = os.environ.copy()
                    for variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS', 'MKL_NUM_THREADS'):
                        env[variable] = '1'
                    env['NUMBA_CACHE_DIR'] = str(output / 'numba-cache' / ('slot-%d' % slot))
                    with (attempt / 'process-private.log').open('xb') as log:
                        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
                    immutable(attempt / 'launched-private.json', dict(pid=process.pid, created_utc=utc()))
                    children[slot] = process, attempt
                    launched_here.add(job['job_id'])
                current(output / 'status-private.json', dict(round=plan['round'], operator=plan['operator'],
                    completed_jobs=len(finished), pending_jobs=54 - len(finished),
                    consecutive_no_clear=ledger['consecutive_no_clear'], stop_condition_met=False))
                if len(finished) != 54:
                    time.sleep(poll_seconds)
            ledger = commit_round(output, manifest, ledger, folder, plan)
            print(json.dumps(dict(completed_rounds=ledger['completed_rounds'],
                consecutive_no_clear=ledger['consecutive_no_clear'], stop_condition_met=ledger['stop_condition_met'])), flush=True)
        return ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('validate')
    check.add_argument('baseline', type=Path)
    check.add_argument('output', type=Path)
    create = commands.add_parser('prepare')
    create.add_argument('baseline', type=Path)
    create.add_argument('output', type=Path)
    create.add_argument('--libraries', type=Path, required=True)
    create.add_argument('--validation', type=Path, required=True)
    approve = commands.add_parser('authorize')
    approve.add_argument('output', type=Path)
    approve.add_argument('--baseline-worker-pids', type=int, nargs='*', default=[])
    approve.add_argument('--confirmed-baseline-exit', action='store_true')
    launch = commands.add_parser('control')
    launch.add_argument('output', type=Path)
    launch.add_argument('--max-rounds', type=int)
    launch.add_argument('--retry-reviewed-failures', action='store_true')
    run = commands.add_parser('worker')
    run.add_argument('output', type=Path)
    run.add_argument('--plan', type=Path, required=True)
    run.add_argument('--job', required=True)
    run.add_argument('--attempt', type=Path, required=True)
    run.add_argument('--slot', type=int, required=True)
    status = commands.add_parser('status')
    status.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'validate':
            validate(args.baseline, args.output)
            print('PASS: registered syntax and unit checks; no search campaign launched')
        elif args.command == 'prepare':
            prepare(args.baseline, args.output, args.libraries, args.validation)
            print('Prepared 54 bound incumbents and 27 unchanged declared targets; launch remains disabled')
        elif args.command == 'authorize':
            authorize(args.output, args.baseline_worker_pids, args.confirmed_baseline_exit)
            print('Local root-reviewed activation recorded; nothing published')
        elif args.command == 'control':
            state = control(args.output, max_rounds=args.max_rounds, retry=args.retry_reviewed_failures)
            print(json.dumps({key: state[key] for key in ('completed_rounds', 'consecutive_no_clear', 'stop_condition_met')}))
        elif args.command == 'worker':
            return worker(args.output, args.plan, args.job, args.attempt, args.slot)
        else:
            output, manifest = load_campaign(args.output)
            state = recover_ledger(output, manifest)
            print(json.dumps({key: state[key] for key in ('completed_rounds', 'consecutive_no_clear', 'stop_condition_met')}))
        return 0
    except Exception as error:
        # File paths, source identities and fingerprints stay in the local log.
        target = getattr(args, 'output', None)
        if target is not None:
            try:
                directory = private_output(target)
                if directory.is_dir():
                    (directory / ('controller-error-' + uuid.uuid4().hex + '-private.log')).write_text(
                        traceback.format_exc(), encoding='utf-8')
            except Exception:
                pass
        print(json.dumps(dict(status='INFRASTRUCTURE_STOP', exception=type(error).__name__,
                              counts_as_completed_quality_round=False)), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

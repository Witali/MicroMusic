"""Frozen full-speech quiet/voice study; private artifacts stay in build/."""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

CORE_COMMIT = '5b4800f7'
PREFIX = 'Codecs/LPX/01_ACTIVE_Q0_CODEC/'
HERE = Path(__file__).resolve().parent
PROTOCOL = HERE.parent / 'PROTOCOL.md'
PRE_GRID = (0, 8192, 13926)
REQUIRED_CORE_MODULES = ('encode_speech_voice', 'voice_character', 'speech_voice_objective',
                         'speech_v4', 'speech_compact', 'q0_model', 'wav_lpc',
                         'standard_metrics', 'refine_speech_compact', 'batch_decoder',
                         'benchmark_speech_flash')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def validate_binding(binding):
    if binding.get('identity') != sha(canonical({k: v for k, v in binding.items() if k != 'identity'})):
        raise ValueError('Prepared binding content identity changed')


def save(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.writing')
    for target in (path, temporary):
        if target.is_symlink() or target.exists() and target.stat().st_nlink > 1:
            raise ValueError('Output aliases are not allowed')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_bytes(json.dumps(value, indent=2, allow_nan=False).encode() + b'\n')
    temporary.replace(path)


def immutable_bytes(path, data):
    path = Path(path)
    if path.is_symlink() or path.exists() and path.stat().st_nlink > 1:
        raise ValueError('Stream aliases are not allowed')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('An immutable stream changed')
    else:
        path.write_bytes(data)


def snapshot(source_root):
    active = source_root / PREFIX
    paths = [*sorted((active / 'tools').glob('*.py')),
             *sorted(p for p in (active / 'src').rglob('*') if p.is_file())]
    return {'core': {p.relative_to(source_root).as_posix(): sha(p.read_bytes()) for p in paths},
            'runner': sha(Path(__file__).read_bytes()), 'protocol': sha(PROTOCOL.read_bytes()),
            'tests': sha(HERE.joinpath('test_protocol.py').read_bytes())}


def require_core_epoch(source_root):
    names = subprocess.check_output(['git', '-C', str(source_root), 'ls-tree', '-r', '--name-only',
                                     CORE_COMMIT, '--', PREFIX + 'tools', PREFIX + 'src'], text=True).splitlines()
    names = [name for name in names if name.startswith(PREFIX + 'src/') or name.endswith('.py')]
    expected = {name: sha(subprocess.check_output(['git', '-C', str(source_root), 'show', CORE_COMMIT + ':' + name]))
                for name in names}
    if snapshot(source_root)['core'] != expected:
        raise ValueError('Core files must exactly match frozen frontend epoch ' + CORE_COMMIT)


def environment():
    compiler = shutil.which('g++')
    if compiler is None:
        raise ValueError('Native compiler is required for the pinned preparation environment')
    return {'python': sys.version, 'platform': platform.platform(),
            'packages': {name: version(name) for name in ('numpy', 'numba', 'scipy', 'pystoi', 'soundfile')},
            'compiler_file_sha256': sha(Path(compiler).read_bytes()),
            'compiler_version': subprocess.check_output([compiler, '--version'], text=True).splitlines()[0],
            'threads': {name: os.environ.get(name) for name in
                        ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS')}}


def assert_core_module_origins(source_root, modules=None):
    """Reject a cached local import from any other checkout, even with matching disk hashes."""
    modules = sys.modules if modules is None else modules
    tools = (Path(source_root) / PREFIX / 'tools').resolve()
    known = {p.stem: p.resolve() for p in tools.glob('*.py')}
    for name in REQUIRED_CORE_MODULES:
        known[name] = tools / (name + '.py')
        if name not in modules:
            raise ValueError('A required core module was not loaded from the frozen source root')
    project_tail = '/' + PREFIX + 'tools/'
    for name, module in list(modules.items()):
        origin = getattr(module, '__file__', None)
        if name in known:
            if origin is None or Path(origin).resolve() != known[name]:
                raise ValueError('Cached core module belongs to another source root: ' + name)
        elif origin is not None and project_tail.casefold() in Path(origin).as_posix().casefold():
            # Also inspect project-local dependencies imported under an alias.
            if Path(origin).resolve().parent != tools:
                raise ValueError('A loaded local dependency belongs to another source root')


def load_core(source_root):
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS'):
        os.environ[name] = '1'
    sys.path.insert(0, str(source_root / PREFIX / 'tools'))
    import numpy as np
    import soundfile as sf
    import speech_compact as compact
    from batch_decoder import BatchSession, build_library
    from benchmark_speech_flash import source_hashes
    from encode_speech_voice import encode, prepare_level, _quality, _voice_gate
    from speech_voice_objective import VoiceObjective
    from standard_metrics import pwm_duties, pwm_pcm16
    from voice_character import track_pitch, compare_voice
    assert_core_module_origins(source_root)
    return SimpleNamespace(**locals())


def geometry(record):
    position = 0
    result = []
    for index, segment in enumerate(record['segments']):
        n = segment['samples']
        if (segment['index'] != index or segment['start'] != position or
                segment['profile'] != record['profile'] or type(n) is not int or not 1 <= n <= 64000):
            raise ValueError('Actual reset order, offsets or geometry changed')
        result.append((n, record['profile']))
        position += n
    if not result or position != record['samples']:
        raise ValueError('Reset segments do not cover the complete original source')
    return result


def grouped_sources(records):
    groups = {}
    for index, record in enumerate(records):
        key = record['private_case_id']
        if key not in groups:
            groups[key] = []
        groups[key].append(index)
    result = list(groups.values())
    for indices in result:
        rows = [records[i] for i in indices]
        if (len(rows) != 2 or {r['profile'] for r in rows} != {4, 6} or
                len({r['reference']['pcm16_sha256'] for r in rows}) != 1 or
                len({r['samples'] for r in rows}) != 1):
            raise ValueError('Each source must retain both matching profile groups')
    return result


def assert_close(actual, expected):
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise AssertionError('Source-bound report keys changed')
        for key in expected:
            assert_close(actual[key], expected[key])
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise AssertionError('Source-bound report list changed')
        for a, b in zip(actual, expected):
            assert_close(a, b)
    elif isinstance(expected, (float, int)) and not isinstance(expected, bool):
        if not isinstance(actual, (float, int)) or not math.isfinite(actual) or abs(actual - expected) > 1e-12:
            raise AssertionError('Source-bound numeric metric changed')
    elif actual != expected:
        raise AssertionError('Source-bound report value changed')


class CapturingDecoder:
    """Forward native calls unchanged; retain successful V5 inputs, owned/order-deduped."""
    def __init__(self, receiver, on_fit=None):
        self.receiver = receiver
        self.streams = []
        self._seen = set()
        self.completed_v4_fits = 0
        self.on_fit = on_fit

    def decode_one_s16(self, blob, samples):
        actual = self.receiver.decode_one_s16(blob, samples)
        data = bytes(blob)
        if actual is not None and data[:4] == b'L4HY':
            if data[4:5] == b'\x04':
                self.completed_v4_fits += 1
                if self.on_fit is not None:
                    self.on_fit(self.completed_v4_fits)
            if data[4:5] == b'\x05' and data not in self._seen:
                self.streams.append(data)
                self._seen.add(data)
        return actual

    def __getattr__(self, name):
        return getattr(self.receiver, name)


def choose_budget(entries, original_bytes, percent):
    if type(original_bytes) is not int or original_bytes < 22 or percent not in (100, 95, 90):
        raise ValueError('Expected original complete bytes and a declared budget percentage')
    cap = original_bytes * percent // 100
    fitting = [entry for entry in entries if entry is not None and entry['stream_bytes'] <= cap]
    eligible = [entry for entry in fitting if entry['automatic_quality_eligible']]
    priority = {'control': 0, 'concat-selected': 1, 'concat-raw': 2}
    key = lambda entry: (entry['voice_score'], entry['stream_bytes'], priority[entry['role']])
    distinct = {tuple(s['stream_sha256'] for s in entry['segments']) for entry in fitting}
    return {'percent': percent, 'cap': cap,
            'selected': min(eligible, key=key)['role'] if eligible else None,
            'raw_tradeoff': min(fitting, key=key)['role'] if fitting else None,
            'fitting_chain_count': len(fitting), 'eligible_chain_count': len(eligible),
            'distinct_fitting_chain_count': len(distinct),
            'no_fit': not fitting, 'no_automatic_admission': not eligible}


def prepare(args, C):
    out, root = args.output.resolve(), args.source_root.resolve()
    if (not out.is_relative_to((root / 'build').resolve()) or
            {p.name for p in out.iterdir()} != {'tmp'}):
        raise ValueError('Preparation must own a fresh directory with only its runtime bootstrap')
    require_core_epoch(root)
    initial_source, initial_environment = snapshot(root), environment()
    raw = args.manifest.read_bytes()
    manifest = json.loads(raw)
    if manifest['schema'] != 'lpx-v5-encoder-quality-study-v1':
        raise ValueError('Expected frozen baseline-v2 manifest')
    records, groups = manifest['records'], grouped_sources(manifest['records'])
    if len(records) != 98 or len(groups) != 49 or sum(len(r['segments']) for r in records) != 118:
        raise ValueError('Expected complete49/98/118 speech scope')
    if C.source_hashes(root / PREFIX / 'src') != manifest['source_sha256']:
        raise ValueError('Production decoder differs from original baseline')
    handoff_raw = args.target_handoff.read_bytes()
    handoff_pairs = json.loads(handoff_raw)['pairs']
    if len(handoff_pairs) != 1:
        raise ValueError('Expected one fixed targeted listening pair')
    targeted = handoff_pairs[0]['record']['reference']['pcm16_sha256']
    inputs = {str(args.manifest.resolve()): sha(raw), str(args.target_handoff.resolve()): sha(handoff_raw)}
    ordinal_by_record, quiet_ordinals = {}, []
    for ordinal, indices in enumerate(groups):
        first = records[indices[0]]
        ref, rate = C.sf.read(first['reference']['path'], dtype='int16')
        if rate != 8000 or ref.ndim != 1 or len(ref) != first['samples']:
            raise ValueError('Original reference geometry changed')
        if sha(ref.astype('<i2').tobytes()) != first['reference']['pcm16_sha256']:
            raise ValueError('Original reference PCM changed')
        rms = float(C.np.std(ref.astype(C.np.float64)))
        if rms < 256:
            if len(ref) > 64000 or any(len(records[i]['segments']) != 1 for i in indices):
                raise ValueError('This auto research protocol requires whole single-reset quiet sources')
            _, info = C.prepare_level(ref, 'auto-quiet')
            if info['gain'] <= 1:
                raise ValueError('Expected declared nonidentity quiet research gains')
            quiet_ordinals.append(ordinal)
        for index in indices:
            ordinal_by_record[index] = ordinal
    if len(quiet_ordinals) != 4:
        raise ValueError('Quiet research scope changed from four whole sources')
    jobs = []
    for index, record in enumerate(records):
        geometry(record)
        if record['baseline_bytes'] != sum(s['file_bytes'] for s in record['segments']):
            raise ValueError('Original complete stored bytes changed')
        for path, digest in [(record['reference']['path'], record['reference']['file_sha256']),
                             *((s['path'], s['stream_sha256']) for s in record['segments'])]:
            data = Path(path).read_bytes()
            if sha(data) != digest:
                raise ValueError('Original frozen input file changed')
            inputs[str(Path(path).resolve())] = digest
        ordinal = ordinal_by_record[index]
        jobs.append({'record_index': index, 'source_ordinal': ordinal, 'mode': 'preserve'})
        if args.auto_quiet_research and ordinal in quiet_ordinals:
            jobs.append({'record_index': index, 'source_ordinal': ordinal, 'mode': 'auto-quiet'})
    (out / 'native').mkdir()
    (out / 'workers').mkdir()
    (out / 'records').mkdir()
    libraries = {}
    for name, only in (('common.so', False), ('v5-only.so', True)):
        path = out / 'native' / name
        C.build_library(path, v3_features=124, speech=True, speech_compact=True, compact_only=only)
        libraries[name] = sha(path.read_bytes())
    if snapshot(root) != initial_source or environment() != initial_environment:
        raise ValueError('Preparation source/runtime changed')
    binding = {'schema': 'lpx-quiet-voice-corpus-binding-private-v1', 'core_commit': CORE_COMMIT,
               'source_root': str(root), 'source': initial_source, 'environment': initial_environment,
               'manifest_sha256': sha(raw), 'manifest_path': str(args.manifest.resolve()),
               'input_files_sha256': inputs, 'native_libraries_sha256': libraries,
               'records': records, 'jobs': jobs, 'quiet_source_ordinals': quiet_ordinals,
               'targeted_reference_pcm16_sha256': targeted,
               'settings': {'pre_grid': list(PRE_GRID), 'shards': 2,
                            'auto_quiet_research': args.auto_quiet_research,
                            'whole_pool': ['control', 'concat-selected', 'concat-raw']},
               'expected_preserve_fits': 354, 'expected_auto_fits': 32 if args.auto_quiet_research else 0,
               'gain_one_auto_identity_reuse_eligible_groups': 90}
    binding['expected_by_shard'] = {
        str(shard): {'mode_groups': sum(j['source_ordinal'] % 2 == shard for j in jobs),
                     'completed_fresh_encoder_fits': sum(
                         len(records[j['record_index']]['segments']) * (4 if j['mode'] == 'auto-quiet' else 3)
                         for j in jobs if j['source_ordinal'] % 2 == shard)}
        for shard in (0, 1)}
    if sum(r['reference']['pcm16_sha256'] == targeted for r in records) != 2:
        raise ValueError('Targeted listening source must mark exactly two profiles')
    binding['identity'] = sha(canonical(binding))
    save(out / 'binding-private.json', binding)
    print(json.dumps({'phase': 'prepared', 'sources': 49, 'profile_groups': 98,
                      'segments': 118, 'mode_groups': len(jobs),
                      'preserve_fits': 354, 'auto_research_fits': binding['expected_auto_fits']}), flush=True)


def guard(binding, args, C, all_inputs=False):
    if (snapshot(args.source_root.resolve()) != binding['source'] or
            environment() != binding['environment']):
        raise ValueError('Frozen source/runtime epoch changed')
    for name, digest in binding['native_libraries_sha256'].items():
        if sha((args.output / 'native' / name).read_bytes()) != digest:
            raise ValueError('Prepared native library changed')
    for path, digest in binding['input_files_sha256'].items():
        if all_inputs or path == binding['manifest_path']:
            if sha(Path(path).read_bytes()) != digest:
                raise ValueError('Frozen input changed')


def verify_chain(blobs, reset_geometry, C, common, only, counters):
    parts = []
    if len(blobs) != len(reset_geometry):
        raise AssertionError('Complete chain segment count changed')
    for blob, expected_geometry in zip(blobs, reset_geometry):
        if C.compact.unpack(blob)[:2] != expected_geometry:
            raise AssertionError('Candidate reset length/profile changed')
        pcm = C.compact.decode_model(blob)
        pwm = C.pwm_duties(pcm)
        for receiver in (common, only):
            if (not C.np.array_equal(receiver.decode_one_s16(blob, len(pcm)), pcm) or
                    not C.np.array_equal(receiver.decode_one(blob, len(pcm)), pwm)):
                raise AssertionError('Complete ordered chain native/model PCM/PWM mismatch')
            counters['native_output_domain_comparisons'] += 2
        counters['model_samples'] += len(pcm)
        parts.append(pcm)
    return C.np.concatenate(parts)


def chain_entry(role, blobs, paths, target, reset_geometry, track, objective,
                baseline, C, common, only, counters):
    if blobs is None:
        return None
    pcm = verify_chain(blobs, reset_geometry, C, common, only, counters)
    if len(pcm) != len(target):
        raise AssertionError('Complete source sample count changed')
    metrics = C._quality(target, pcm, True)
    voice = C.compare_voice(target, pcm, reference_track=track)
    pwm_voice = C.compare_voice(target, C.pwm_pcm16(pcm), reference_track=track)
    score = objective(pcm)
    flags = {'old_pcm_pwm_floors_passed': True, 'pcm_voice_proxy_floors_passed': True,
             'pwm_voice_proxy_floors_passed': True, 'voice_objective_nonregression': True}
    if baseline is not None:
        from refine_speech_compact import no_regression
        flags = {'old_pcm_pwm_floors_passed': bool(no_regression(metrics, baseline['metrics'])),
                 'pcm_voice_proxy_floors_passed': bool(C._voice_gate(voice, baseline['voice'])),
                 'pwm_voice_proxy_floors_passed': bool(C._voice_gate(pwm_voice, baseline['pwm_voice'])),
                 'voice_objective_nonregression': score <= baseline['voice_score'] + 1e-12}
    segments, position = [], 0
    for index, (blob, path, (samples, profile)) in enumerate(zip(blobs, paths, reset_geometry)):
        segments.append({'path': str(Path(path).resolve()), 'stream_sha256': sha(blob),
                         'file_bytes': len(blob), 'samples': samples, 'start': position,
                         'index': index, 'profile': profile})
        position += samples
    return {'role': role, 'samples': len(target), 'segments': segments,
            'stream_bytes': sum(map(len, blobs)), 'pcm16_sha256': sha(pcm.astype('<i2').tobytes()),
            'pwm_sha256': sha(C.pwm_duties(pcm).tobytes()), 'metrics': metrics,
            'voice': voice, 'pwm_voice': pwm_voice, 'voice_score': score,
            'voice_components': objective.components(pcm), **flags,
            'automatic_quality_eligible': all(flags.values())}


def load_reference(record, C):
    reference = record['reference']
    data = Path(reference['path']).read_bytes()
    if len(data) != reference['file_bytes'] or sha(data) != reference['file_sha256']:
        raise ValueError('Original reference file changed')
    ref, rate = C.sf.read(reference['path'], dtype='int16')
    if (rate != 8000 or ref.ndim != 1 or len(ref) != record['samples'] or
            sha(ref.astype('<i2').tobytes()) != reference['pcm16_sha256']):
        raise ValueError('Original complete PCM reference changed')
    blobs = []
    for s, g in zip(record['segments'], geometry(record)):
        blob = Path(s['path']).read_bytes()
        if (len(blob) != s['file_bytes'] or sha(blob) != s['stream_sha256'] or
                C.compact.unpack(blob)[:2] != g):
            raise ValueError('Original ordered stream changed')
        blobs.append(blob)
    return ref, blobs


def inspect_cache(folder, identity):
    marker = json.loads((folder / 'complete-private.json').read_text())
    path = folder / 'record-private.json'
    if marker['identity'] != identity or marker['report_sha256'] != sha(path.read_bytes()):
        raise ValueError('Immutable record cache identity/report changed')
    for name, digest in marker['artifacts_sha256'].items():
        path = folder / name
        if not path.resolve().is_relative_to(folder.resolve()) or sha(path.read_bytes()) != digest:
            raise ValueError('Immutable record cache artifact changed')
    return json.loads((folder / 'record-private.json').read_text())


def run_record(job, record, binding, args, C, common, only):
    mode = job['mode']
    folder = args.output / 'records' / ('source-%03d' % job['source_ordinal']) / ('profile-%d' % record['profile']) / mode
    identity = sha(canonical([binding['identity'], job]))
    ref, original = load_reference(record, C)
    if (folder / 'complete-private.json').exists():
        return inspect_cache(folder, identity), True
    folder.mkdir(parents=True, exist_ok=True)
    reset_geometry = geometry(record)
    counters = {'native_output_domain_comparisons': 0, 'model_samples': 0}
    original_pcm = verify_chain(original, reset_geometry, C, common, only, counters)
    if (sha(original_pcm.astype('<i2').tobytes()) != record['baseline_pcm16_sha256'] or
            sha(C.pwm_duties(original_pcm).tobytes()) != record['baseline_pwm_sha256']):
        raise AssertionError('Original complete output fingerprints changed')
    assert_close(C._quality(ref, original_pcm, True), record['baseline_metrics'])
    if mode == 'auto-quiet':
        if len(original) != 1 or len(ref) > 64000:
            raise ValueError('Auto research must apply one whole-source gain')
        target, level = C.prepare_level(ref, mode)
    else:
        target = ref.copy()
        rms = float(C.np.std(ref.astype(C.np.float64)))
        level = {'policy': mode, 'gain': 1, 'gain_db': 0., 'input_ac_rms_pcm16': rms,
                 'input_peak_pcm16': int(C.np.max(C.np.abs(ref.astype(C.np.int64)))),
                 'target_ac_rms_pcm16': rms, 'output_level_matches_original': True}
    track = C.track_pitch(target)
    objective = C.VoiceObjective(target, track.period)
    captured_all, controls, control_paths = [], [], []
    choices = {'concat-selected': [], 'concat-raw': []}
    choice_paths = {'concat-selected': [], 'concat-raw': []}
    segment_reports = []
    fits = 0
    position = 0
    attempts = folder / 'attempts'
    attempts.mkdir(exist_ok=True)
    prior_attempts = [json.loads(p.read_text()) for p in sorted(attempts.glob('attempt-*-private.json'))]
    if any(a['identity'] != identity for a in prior_attempts):
        raise ValueError('Incomplete prior attempt used another source epoch')
    attempt_path = attempts / ('attempt-%03d-private.json' % len(prior_attempts))
    attempt = {'identity': identity, 'status': 'running', 'completed_v4_native_fit_calls': 0,
               'active_segment': None}
    save(attempt_path, attempt)
    for index, (old, (samples, profile)) in enumerate(zip(original, reset_geometry)):
        start = time.perf_counter()
        attempt['active_segment'] = index
        def observed_fit(count):
            attempt['completed_v4_native_fit_calls'] = fits + count
            save(attempt_path, attempt)
        capture = CapturingDecoder(common, observed_fit)
        selected, _, report, raw = C.encode(ref[position:position + samples], profile, capture,
            baseline=old, max_bytes=record['baseline_bytes'], pre_values=PRE_GRID,
            level_policy=mode, speech=True, compact_decoder=only)
        expected_fits = 4 if mode == 'auto-quiet' else 3
        if (capture.completed_v4_fits != expected_fits or not capture.streams or
                len(report['trials']) != 3 or report['level']['gain'] != level['gain']):
            raise AssertionError('Frozen frontend work/capture/level contract changed')
        fits += capture.completed_v4_fits
        local_target = target[position:position + samples]
        local_track = C.track_pitch(local_target)
        local_objective = C.VoiceObjective(local_target, local_track.period)
        control = capture.streams[0]
        control_pcm = C.compact.decode_model(control)
        if len(control) != report['control_bytes']:
            raise AssertionError('First capture is not the declared control size')
        assert_close(C._quality(local_target, control_pcm, True), report['baseline_metrics'])
        assert_close(C.compare_voice(local_target, control_pcm, reference_track=local_track), report['baseline_voice'])
        assert_close(C.compare_voice(local_target, C.pwm_pcm16(control_pcm), reference_track=local_track), report['baseline_pwm_voice'])
        assert_close(local_objective(control_pcm), report['baseline_voice_score'])
        if mode == 'preserve' and control != old:
            raise AssertionError('Preserve control was replaced')
        paths = {}
        for ordinal, blob in enumerate(capture.streams):
            path = folder / ('segment-%03d' % index) / ('capture-%02d.l4hy' % ordinal)
            immutable_bytes(path, blob)
            paths[blob] = path
            captured_all.append({'path': str(path.resolve()), 'stream_sha256': sha(blob),
                                 'file_bytes': len(blob), 'segment': index, 'capture_order': ordinal})
        controls.append(control)
        control_paths.append(paths[control])
        for role, blob in (('concat-selected', selected), ('concat-raw', raw)):
            choices[role].append(blob)
            choice_paths[role].append(None if blob is None else paths[blob])
        segment_reports.append({'index': index, 'start': position, 'samples': samples,
                                'completed_fresh_encoder_fits': capture.completed_v4_fits,
                                'report': report, 'wall_seconds': time.perf_counter() - start})
        position += samples
    control = chain_entry('control', controls, control_paths, target, reset_geometry, track,
                          objective, None, C, common, only, counters)
    entries = [control]
    for role in ('concat-selected', 'concat-raw'):
        blobs = choices[role]
        entry = None if any(blob is None for blob in blobs) else chain_entry(role, blobs,
            choice_paths[role], target, reset_geometry, track, objective, control, C, common, only, counters)
        entries.append(entry)
    budgets = [choose_budget(entries, record['baseline_bytes'], percent) for percent in (100, 95, 90)]
    if mode == 'preserve' and budgets[0]['selected'] is None:
        raise AssertionError('Original complete rollback disappeared')
    load_reference(record, C)  # Guard the exact original after all record work.
    guard(binding, args, C)
    if attempt['completed_v4_native_fit_calls'] != fits:
        raise AssertionError('Observed native fit calls differ from completed record work')
    result = {'schema': 'lpx-quiet-voice-corpus-record-private-v1', 'identity': identity,
              **job, 'id': record['id'], 'profile': record['profile'], 'samples': len(ref),
              'split': record['split'], 'cohort': record['cohort'],
              'targeted_not_independent_heldout': record['reference']['pcm16_sha256'] == binding['targeted_reference_pcm16_sha256'],
              'level': level, 'whole_original_bytes': record['baseline_bytes'],
              'original_level_control': {'segments': record['segments'], 'metrics': record['baseline_metrics'],
                                         'pcm16_sha256': record['baseline_pcm16_sha256'], 'pwm_sha256': record['baseline_pwm_sha256']},
              'original_reference_pcm16_sha256': sha(ref.astype('<i2').tobytes()),
              'target_reference_pcm16_sha256': sha(target.astype('<i2').tobytes()),
              'target_pwm_voice': C.compare_voice(target, C.pwm_pcm16(target), reference_track=track),
              'objective': objective.describe(), 'segment_searches': segment_reports,
              'completed_fresh_encoder_fits': fits, 'chains': entries, 'budgets': budgets,
              'prior_attempts': prior_attempts,
              'all_attempts_completed_v4_native_fit_calls': fits + sum(
                  a['completed_v4_native_fit_calls'] for a in prior_attempts),
              'prior_incomplete_attempts': sum(a['status'] != 'complete' for a in prior_attempts),
              'captured_streams': captured_all, 'validation': counters,
              'scope': 'Whole actual reset chains; three finite choices, no cap-specific refit or mixture. Auto target level is separate.'}
    save(folder / 'record-private.json', result)
    artifacts = {p.relative_to(folder).as_posix(): sha(p.read_bytes()) for p in folder.rglob('*.l4hy')}
    attempt.update(status='complete', active_segment=None)
    save(attempt_path, attempt)
    # Last commit point: a complete cache must never retain a running attempt.
    save(folder / 'complete-private.json', {'identity': identity,
        'report_sha256': sha((folder / 'record-private.json').read_bytes()), 'artifacts_sha256': artifacts})
    return result, False


def worker(args, C):
    binding_path = args.output / 'binding-private.json'
    raw = binding_path.read_bytes()
    binding = json.loads(raw)
    validate_binding(binding)
    if binding['source_root'] != str(args.source_root.resolve()) or args.shard not in (0, 1):
        raise ValueError('Worker source root/shard does not match prepared study')
    require_core_epoch(args.source_root.resolve())
    guard(binding, args, C, all_inputs=True)
    jobs = [j for j in binding['jobs'] if j['source_ordinal'] % 2 == args.shard]
    report = {'schema': 'lpx-quiet-voice-corpus-worker-private-v1', 'status': 'running',
              'binding_sha256': sha(raw), 'identity': binding['identity'], 'shard': args.shard,
              'source': binding['source'], 'records': [], 'fresh_encoder_fits': 0,
              'reused_records': 0, 'executed_records': 0}
    began = time.perf_counter()
    output = args.output / 'workers' / ('shard-%d-private.json' % args.shard)
    save(output, report)
    with C.BatchSession('batch', prebuilt=args.output / 'native/common.so') as common, C.BatchSession(
            'batch', prebuilt=args.output / 'native/v5-only.so') as only:
        for number, job in enumerate(jobs, 1):
            if binding_path.read_bytes() != raw:
                raise ValueError('Prepared binding changed')
            guard(binding, args, C)
            row, reused = run_record(job, binding['records'][job['record_index']], binding, args, C, common, only)
            report['records'].append(row)
            report['reused_records' if reused else 'executed_records'] += 1
            if not reused:
                report['fresh_encoder_fits'] += row['completed_fresh_encoder_fits']
            report['wall_seconds'] = time.perf_counter() - began
            save(output, report)
            print(json.dumps({'phase': 'quiet-voice-corpus', 'shard': args.shard,
                              'completed_mode_groups': number, 'total_mode_groups': len(jobs),
                              'mode': job['mode'], 'reused': reused}), flush=True)
    guard(binding, args, C, all_inputs=True)
    if binding_path.read_bytes() != raw:
        raise ValueError('Prepared binding changed at completion')
    report.update(status='complete', wall_seconds=time.perf_counter() - began,
                  recorded_encoder_fits=sum(r['completed_fresh_encoder_fits'] for r in report['records']))
    if (len(report['records']) != binding['expected_by_shard'][str(args.shard)]['mode_groups'] or
            report['recorded_encoder_fits'] != binding['expected_by_shard'][str(args.shard)]['completed_fresh_encoder_fits']):
        raise AssertionError('Completed shard work differs from the frozen study')
    save(output, report)
    print(json.dumps({'phase': 'quiet-voice-complete', 'shard': args.shard,
                      'mode_groups': len(jobs), 'fresh_encoder_fits': report['fresh_encoder_fits'],
                      'reused_records': report['reused_records']}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--target-handoff', type=Path)
    parser.add_argument('--auto-quiet-research', action='store_true')
    parser.add_argument('--shard', type=int, choices=(0, 1))
    args = parser.parse_args()
    args.source_root, args.output = args.source_root.resolve(), args.output.resolve()
    if not args.output.is_relative_to((args.source_root / 'build').resolve()):
        parser.error('Output must stay under source-root/build/')
    if args.prepare:
        if args.manifest is None or args.target_handoff is None or args.shard is not None:
            parser.error('Prepare requires manifest/handoff and no shard')
        if args.output.exists():
            parser.error('Prepare requires a fresh output directory')
    elif (args.shard is None or args.manifest is not None or args.target_handoff is not None or
          args.auto_quiet_research):
        parser.error('A worker uses only the prepared binding and a shard')
    temporary = args.output / 'tmp' / ('prepare' if args.prepare else 'shard-' + str(args.shard))
    temporary.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(temporary)
    os.environ['NUMBA_CACHE_DIR'] = str(temporary / 'numba-cache')
    C = load_core(args.source_root)
    if args.prepare:
        prepare(args, C)
    else:
        worker(args, C)


if __name__ == '__main__':
    main()

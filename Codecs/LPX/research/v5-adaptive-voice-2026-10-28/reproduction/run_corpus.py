"""Frozen V2 regression/subset study with reusable, verified V1 stream seeds.

All media, original identifiers, private bindings and generated streams stay in
ignored build storage. This driver never calls a fresh seed-fitting encoder.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from fractions import Fraction
import importlib.util
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
import traceback
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PREFIX = 'Codecs/LPX/01_ACTIVE_Q0_CODEC/'
PROTOCOL = HERE.parent / 'PROTOCOL.md'
V1_HELPER = HERE.parents[1] / 'v5-quiet-voice-encoder-2026-10-28/reproduction/run_corpus.py'
spec = importlib.util.spec_from_file_location('adaptive_study_v1_utilities', V1_HELPER)
V1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V1)
sha, canonical = V1.sha, V1.canonical
_save_once = V1.save
immutable_bytes, geometry, assert_close = V1.immutable_bytes, V1.geometry, V1.assert_close


def save(path, value):
    """Retry only transient Windows access/sharing failures of atomic save.

    No operator is retried. Every attempt retains V1's alias checks and exact
    bytes, and persistent permissions failures still propagate to the caller.
    """
    delays = (.02, .05, .1, .2, .4)
    for attempt in range(len(delays) + 1):
        try:
            return _save_once(path, value)
        except PermissionError as exc:
            if getattr(exc, 'winerror', None) not in (5, 32) or attempt == len(delays):
                raise
            time.sleep(delays[attempt])

REQUIRED_MODULES = ('adaptive_speech_voice', 'speech_noise_objective', 'speech_voice_objective',
    'voice_character', 'voice_input', 'speech_v4', 'speech_compact', 'q0_model', 'wav_lpc',
    'standard_metrics', 'refine_speech_compact', 'refine_speech_lpc', 'enhance_speech_compact',
    'batch_decoder', 'benchmark_speech_flash', 'encode_speech_voice')
PHASES = ('speech-screen', 'speech-default', 'nonspeech-default')


def local_cap(whole_bytes):
    if type(whole_bytes) is not int or whole_bytes < 22:
        raise ValueError('Expected a real complete-source byte cap')
    return min(whole_bytes, 65535)


def representative_ordinals(records, groups, excluded=()):
    eligible = sorted((i for i in range(len(groups)) if i not in excluded),
                      key=lambda i: (records[groups[i][0]]['samples'], i))
    if len(eligible) < 3:
        raise ValueError('Three distinct representative sources are required')
    return [eligible[0], eligible[len(eligible)//2], eligible[-1]]


def assert_origins(root, modules=None):
    modules = sys.modules if modules is None else modules
    tools = (root / PREFIX / 'tools').resolve()
    known = {p.stem: p.resolve() for p in tools.glob('*.py')}
    for name in REQUIRED_MODULES:
        if name not in modules:
            raise ValueError('A required V2 project module was not loaded')
        known[name] = tools / (name + '.py')
    origins = {}
    for name, module in list(modules.items()):
        origin = getattr(module, '__file__', None)
        if name in known:
            if origin is None or Path(origin).resolve() != known[name]:
                raise ValueError('A cached core import belongs to another checkout')
            origins[name] = Path(origin).resolve().relative_to(root.resolve()).as_posix()
        elif origin is not None and ('/' + PREFIX + 'tools/').casefold() in Path(origin).as_posix().casefold():
            if Path(origin).resolve().parent != tools:
                raise ValueError('A project-local dependency belongs to another checkout')
            origins[name] = Path(origin).resolve().relative_to(root.resolve()).as_posix()
    return origins


def load_core(root):
    for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS'):
        os.environ[key] = '1'
    sys.path.insert(0, str(root / PREFIX / 'tools'))
    import numpy as np
    import soundfile as sf
    import adaptive_speech_voice as adaptive
    import speech_v4
    import speech_compact as compact
    from batch_decoder import BatchSession, build_library
    from benchmark_speech_flash import source_hashes
    from encode_speech_voice import prepare_level, _quality, _voice_gate
    from refine_speech_compact import no_regression
    from speech_voice_objective import VoiceObjective
    from speech_noise_objective import NoiseObjective
    from standard_metrics import pwm_duties, pwm_pcm16
    from voice_character import compare_voice, track_pitch
    origins = assert_origins(root)
    return SimpleNamespace(**locals())


def snapshot(root):
    active = root / PREFIX
    paths = [*sorted((active/'tools').glob('*.py')),
             *sorted((active/'tests').glob('test_*.py')),
             *sorted(p for p in (active/'src').rglob('*') if p.is_file())]
    research = [Path(__file__), PROTOCOL, HERE/'test_protocol.py', V1_HELPER]
    return {'core': {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in paths},
            'research': {str(p.resolve()): sha(p.read_bytes()) for p in research}}


def require_core_commit(root, commit):
    resolved = subprocess.check_output(['git', '-C', str(root), 'rev-parse', commit+'^{commit}'], text=True).strip()
    names = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-r', '--name-only', resolved,
        '--', PREFIX+'tools', PREFIX+'tests', PREFIX+'src'], text=True).splitlines()
    names = [n for n in names if n.startswith(PREFIX+'src/') or
             n.startswith(PREFIX+'tools/') and n.endswith('.py') and '/' not in n[len(PREFIX+'tools/'):] or
             n.startswith(PREFIX+'tests/test_') and n.endswith('.py') and '/' not in n[len(PREFIX+'tests/'):]]
    expected = {name: sha(subprocess.check_output(['git', '-C', str(root), 'show', resolved+':'+name])) for name in names}
    if snapshot(root)['core'] != expected:
        raise ValueError('Working implementation/tests must exactly match the explicit frozen core commit')
    return resolved


def environment():
    compiler = shutil.which('g++')
    if compiler is None:
        raise ValueError('The pinned native compiler is required')
    return {'python': sys.version, 'executable_sha256': sha(Path(sys.executable).read_bytes()),
            'platform': platform.platform(),
            'packages': {n: version(n) for n in ('numpy', 'numba', 'scipy', 'pystoi', 'soundfile')},
            'compiler_file_sha256': sha(Path(compiler).read_bytes()),
            'compiler_version': subprocess.check_output([compiler, '--version'], encoding='utf-8', errors='replace').splitlines()[0],
            'threads': {k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS')}}


def pin(inputs, path, expected=None):
    path = Path(path).resolve()
    if path.is_symlink():
        raise ValueError('Pinned inputs must not be aliases')
    digest = sha(path.read_bytes())
    if expected is not None and digest != expected:
        raise ValueError('A frozen input fingerprint changed')
    inputs[str(path)] = digest
    return digest


def load_v1_record(v1_root, binding, job, inputs=None):
    record = binding['records'][job['record_index']]
    folder = (v1_root/'records'/('source-%03d' % job['source_ordinal']) /
              ('profile-%d' % record['profile'])/job['mode'])
    identity = sha(canonical([binding['identity'], job]))
    result = V1.inspect_cache(folder, identity)
    marker = json.loads((folder/'complete-private.json').read_text())
    for name, expected in marker['artifacts_sha256'].items():
        if inputs is not None:
            pin(inputs, folder/name, expected)
    if inputs is not None:
        pin(inputs, folder/'record-private.json', marker['report_sha256'])
        pin(inputs, folder/'complete-private.json')
    if (result['record_index'] != job['record_index'] or result['mode'] != job['mode'] or
            result['source_ordinal'] != job['source_ordinal'] or result['profile'] != record['profile']):
        raise ValueError('V1 record identity/geometry changed')
    budget = next(b for b in result['budgets'] if b['percent'] == 100)
    if budget['selected'] is None:
        raise ValueError('Active V1 whole rollback is absent')
    anchor = next(c for c in result['chains'] if c is not None and c['role'] == budget['selected'])
    if not anchor['automatic_quality_eligible'] or anchor['stream_bytes'] > record['baseline_bytes']:
        raise ValueError('Active V1 whole rollback was not admitted')
    return result, folder


def record_inputs(record, inputs):
    geometry(record)
    if record['baseline_bytes'] != sum(s['file_bytes'] for s in record['segments']):
        raise ValueError('Original complete cap differs from its stored reset streams')
    pin(inputs, record['reference']['path'], record['reference']['file_sha256'])
    for segment in record['segments']:
        pin(inputs, segment['path'], segment['stream_sha256'])


def worst_and_tail(reference, blobs, record, C):
    errors = []
    for segment, blob in zip(record['segments'], blobs):
        at, n = segment['start'], segment['samples']
        delta = reference[at:at+n].astype(C.np.int64) - C.compact.decode_model(blob).astype(C.np.int64)
        errors.append(int(C.np.dot(delta, delta)))
    worst = max(range(len(errors)), key=lambda i: (Fraction(errors[i], record['segments'][i]['samples']), -i))
    return list(dict.fromkeys((worst, len(errors)-1))), errors


def prepare(args, C):
    root, out = args.source_root, args.output
    if {p.name for p in out.iterdir()} != {'tmp'}:
        raise ValueError('Preparation requires a fresh owned build directory')
    commit = require_core_commit(root, args.core_commit)
    initial_source, initial_runtime = snapshot(root), environment()
    inputs = {}
    v1_path = args.v1_root/'binding-private.json'
    pin(inputs, v1_path)
    previous = json.loads(v1_path.read_text())
    V1.validate_binding(previous)
    audit = json.loads((args.v1_audit/'audit-private.json').read_text())
    context = json.loads((args.v1_audit/'context-audit.json').read_text())
    if (audit['status'] != 'passed' or audit['binding_sha256'] != sha(v1_path.read_bytes()) or
            context['status'] != 'passed'):
        raise ValueError('The exact V1 binding requires passed independent audits')
    for name in ('audit-private.json', 'audit.json', 'context-audit.json'):
        pin(inputs, args.v1_audit/name)
    speech = previous['records']
    groups = V1.grouped_sources(speech)
    quiet = previous['quiet_source_ordinals']
    if len(speech) != 98 or len(groups) != 49 or len(quiet) != 4:
        raise ValueError('The full active speech source scope changed')
    selected_speech = sorted(set(quiet + representative_ordinals(speech, groups, quiet)))
    if len(selected_speech) != 7:
        raise ValueError('Default-budget speech subset must have seven sources')
    jobs = []
    v1_by_key = {(j['record_index'], j['mode']): j for j in previous['jobs']}
    for ordinal, indices in enumerate(groups):
        mode = 'auto-quiet' if ordinal in quiet else 'preserve'
        for index in indices:
            record_inputs(speech[index], inputs)
            v1_job = v1_by_key[(index, mode)]
            load_v1_record(args.v1_root, previous, v1_job, inputs)
            for phase, limit in [('speech-screen', 1)] + ([('speech-default', 4)] if ordinal in selected_speech else []):
                jobs.append(dict(phase=phase, source_ordinal=ordinal, record_index=index,
                    speech=True, mode=mode, max_refinement_calls=limit,
                    edited_segments=list(range(len(speech[index]['segments']))), v1_job=v1_job))
    pin(inputs, args.nonspeech_manifest)
    nonspeech_manifest = json.loads(args.nonspeech_manifest.read_text())
    nonspeech = nonspeech_manifest['records']
    nonspeech_groups = V1.grouped_sources(nonspeech)
    if nonspeech_manifest['schema'] != 'lpx-v5-encoder-quality-nonspeech-v1' or len(nonspeech_groups) != 132 or len(nonspeech) != 264:
        raise ValueError('Expected the original full nonspeech manifest')
    selected_nonspeech = representative_ordinals(nonspeech, nonspeech_groups)
    for ordinal in selected_nonspeech:
        for index in nonspeech_groups[ordinal]:
            record = nonspeech[index]
            record_inputs(record, inputs)
            ref, blobs = V1.load_reference(record, C)
            edited, errors = worst_and_tail(ref, blobs, record, C)
            jobs.append(dict(phase='nonspeech-default', source_ordinal=ordinal,
                record_index=index, speech=False, mode='preserve', max_refinement_calls=4,
                edited_segments=edited, original_segment_pcm_sse=errors))
    production = {p: d for p, d in initial_source['core'].items() if p.startswith(PREFIX+'src/')}
    v1_production = {p: d for p, d in previous['source']['core'].items() if p.startswith(PREFIX+'src/')}
    if production != v1_production or C.source_hashes(root/PREFIX/'src') != nonspeech_manifest['source_sha256']:
        raise ValueError('The production decoder must remain identical to both baseline studies')
    libraries = {}
    for name, only in (('common.so', False), ('v5-only.so', True)):
        path = out/'native'/name
        path.parent.mkdir(exist_ok=True)
        C.build_library(path, v3_features=124, speech=True, speech_compact=True, compact_only=only)
        libraries[name] = sha(path.read_bytes())
    if initial_source != snapshot(root) or initial_runtime != environment():
        raise ValueError('Preparation implementation/runtime changed')
    binding = dict(schema='lpx-adaptive-voice-binding-private-v2', source_root=str(root),
        core_commit=commit, source=initial_source, environment=initial_runtime,
        module_origins=assert_origins(root), input_files_sha256=inputs,
        native_libraries_sha256=libraries, v1_root=str(args.v1_root),
        v1_binding_sha256=sha(v1_path.read_bytes()), v1_binding=previous,
        v1_audit_root=str(args.v1_audit), speech_records=speech, nonspeech_records=nonspeech,
        jobs=jobs, selected_default_speech_ordinals=selected_speech,
        selected_nonspeech_ordinals=selected_nonspeech, quiet_source_ordinals=quiet,
        targeted_reference_pcm16_sha256=previous['targeted_reference_pcm16_sha256'],
        settings=dict(shards=2, phases=list(PHASES), whole_pool=['control','concat-selected','concat-raw'],
            lpc_preset='expanded', extra_full_evaluations=128, new_seed_fits=0,
            local_cap='min(original_complete_bytes,65535)'))
    binding['expected'] = {phase: dict(groups=sum(j['phase'] == phase for j in jobs),
        refinement_call_upper_bound=sum(j['max_refinement_calls']*len(j['edited_segments']) for j in jobs if j['phase'] == phase)) for phase in PHASES}
    if [binding['expected'][p]['groups'] for p in PHASES] != [98,14,6]:
        raise ValueError('Frozen phase scope differs from 98/14/6 groups')
    binding['identity'] = sha(canonical(binding))
    save(out/'binding-private.json', binding)
    print(json.dumps(dict(phase='prepared-v2', expected=binding['expected'], new_seed_fits=0)), flush=True)


def guard(binding, args, all_inputs=False, extra_paths=()):
    if snapshot(args.source_root) != binding['source'] or environment() != binding['environment']:
        raise ValueError('Frozen V2 implementation/runtime changed')
    origins = assert_origins(args.source_root)
    if any(origins.get(k) != v for k,v in binding['module_origins'].items()):
        raise ValueError('An originally loaded project module changed origin')
    for name, digest in binding['native_libraries_sha256'].items():
        if sha((args.output/'native'/name).read_bytes()) != digest:
            raise ValueError('A prepared native library changed')
    chosen = binding['input_files_sha256'] if all_inputs else {str(Path(p).resolve()): binding['input_files_sha256'][str(Path(p).resolve())] for p in extra_paths}
    for name, digest in chosen.items():
        if sha(Path(name).read_bytes()) != digest:
            raise ValueError('A frozen source/seed input changed')


def clipped(pcm, C):
    return int(C.np.count_nonzero((pcm <= -32768) | (pcm >= 32767)))


def evaluators(target, C):
    track = C.track_pitch(target)
    noise = C.NoiseObjective(target, track.period)
    return track, noise.voice_objective, noise


def measure(target, pcm, speech, evaluator, C):
    track, voice, noise = evaluator
    pwm = C.pwm_pcm16(pcm)
    noise_rows = [noise.summary(d) for d in (pcm,pwm)]
    scores = [float(voice(d) + n['score']) for d,n in zip((pcm,pwm),noise_rows)]
    if any(not math.isfinite(score) for score in scores):
        raise ValueError('The frozen objective returned a nonfinite score')
    return dict(metrics=C._quality(target, pcm, speech),
        voice=C.compare_voice(target, pcm, reference_track=track),
        pwm_voice=C.compare_voice(target, pwm, reference_track=track),
        noise=noise_rows[0], pwm_noise=noise_rows[1],
        domain_scores=scores, score=float(C.np.mean(scores)), clipped_samples=clipped(pcm,C),
        voice_components=voice.components(pcm), pwm_voice_components=voice.components(pwm))


def admission(row, baseline, C):
    flags = dict(old_pcm_pwm_floors_passed=bool(C.no_regression(row['metrics'], baseline['metrics'])),
        clipped_sample_floor_passed=row['clipped_samples'] <= baseline['clipped_samples'],
        pcm_period_coverage_floor_passed=row['voice']['within_tolerance_frames'] >= baseline['voice']['within_tolerance_frames'],
        pwm_period_coverage_floor_passed=row['pwm_voice']['within_tolerance_frames'] >= baseline['pwm_voice']['within_tolerance_frames'])
    flags['joint_objective_nonregression'] = row['score'] <= baseline['score'] + 1e-12
    return flags


def choose_budget(entries, original_bytes, percent):
    if percent not in (100,95,90) or type(original_bytes) is not int or original_bytes < 22:
        raise ValueError('Expected an original whole cap and declared percentage')
    cap = original_bytes*percent//100
    fitting = [e for e in entries if e is not None and e['stream_bytes'] <= cap]
    eligible = [e for e in fitting if e['automatic_quality_eligible']]
    priority = {'control':0, 'concat-selected':1, 'concat-raw':2}
    key = lambda e: (e['score'], e['stream_bytes'], priority[e['role']])
    return dict(percent=percent, cap=cap,
        selected=min(eligible,key=key)['role'] if eligible else None,
        raw_tradeoff=min(fitting,key=key)['role'] if fitting else None,
        fitting_chain_count=len(fitting), eligible_chain_count=len(eligible),
        distinct_fitting_chain_count=len({tuple(s['stream_sha256'] for s in e['segments']) for e in fitting}),
        no_fit=not fitting, no_automatic_admission=not eligible)


def chain_entry(role, blobs, paths, record, target, speech, evaluator, baseline,
                C, common, only, counters):
    if blobs is None or any(b is None for b in blobs):
        return None
    pcm = V1.verify_chain(blobs, geometry(record), C, common, only, counters)
    if len(pcm) != len(target):
        raise ValueError('Whole ordered chain does not cover the full source')
    row = measure(target, pcm, speech, evaluator, C)
    flags = admission(row, row if baseline is None else baseline, C)
    segments = [dict(path=str(Path(path).resolve()), stream_sha256=sha(blob),
        file_bytes=len(blob), index=s['index'],start=s['start'],samples=s['samples'],profile=s['profile'])
        for blob,path,s in zip(blobs,paths,record['segments'])]
    return dict(role=role,samples=len(target),segments=segments,stream_bytes=sum(map(len,blobs)),
        pcm16_sha256=sha(pcm.astype('<i2').tobytes()),pwm_sha256=sha(C.pwm_duties(pcm).tobytes()),
        **row,**flags,automatic_quality_eligible=all(flags.values()))


def read_chain(chain):
    blobs, paths = [], []
    for segment in chain['segments']:
        path = Path(segment['path'])
        blob = path.read_bytes()
        if len(blob) != segment['file_bytes'] or sha(blob) != segment['stream_sha256']:
            raise ValueError('An audited V1 chain stream changed')
        blobs.append(blob)
        paths.append(path)
    return blobs, paths


def verify_v1_chain(chain, legacy, target, record, C, common, only, counters):
    track = C.track_pitch(target)
    objective = C.VoiceObjective(target,track.period)
    rows = []
    for saved in (legacy,chain):
        blobs,_ = read_chain(saved)
        pcm = V1.verify_chain(blobs,geometry(record),C,common,only,counters)
        actual = dict(metrics=C._quality(target,pcm,True),
            voice=C.compare_voice(target,pcm,reference_track=track),
            pwm_voice=C.compare_voice(target,C.pwm_pcm16(pcm),reference_track=track),
            voice_score=objective(pcm),voice_components=objective.components(pcm),
            pcm16_sha256=sha(pcm.astype('<i2').tobytes()),pwm_sha256=sha(C.pwm_duties(pcm).tobytes()))
        for key,value in actual.items():
            assert_close(value,saved[key])
        rows.append(actual)
    before, after = rows
    if (not C.no_regression(after['metrics'],before['metrics']) or
            not C._voice_gate(after['voice'],before['voice']) or
            not C._voice_gate(after['pwm_voice'],before['pwm_voice']) or
            after['voice_score'] > before['voice_score']+1e-12 or
            chain['stream_bytes'] > record['baseline_bytes']):
        raise ValueError('The audited V1 rollback no longer satisfies its whole admission')


def validate_pool(captured, report, target, speech, C, common, only, counters):
    if len(captured) != len(report['candidates']) or len(set(captured)) != len(captured):
        raise ValueError('Candidate sink/order/dedup differs from reported measured pool')
    evaluator = evaluators(target,C)
    measured = []
    for index,(blob,claimed) in enumerate(zip(captured,report['candidates'])):
        profile = report['profile']
        pcm = V1.verify_chain([blob],[(len(target),profile)],C,common,only,counters)
        actual = measure(target,pcm,speech,evaluator,C)
        for key in ('metrics','voice','pwm_voice','noise','pwm_noise','domain_scores','score','clipped_samples'):
            assert_close(actual[key],claimed[key])
        if (claimed['id'] != index or claimed['file_bytes'] != len(blob) or
                claimed['fits_complete_cap'] != (len(blob) <= report['complete_byte_cap']) or
                claimed['full_flash_bytes'] is not None or not claimed['fits_flash_cap']):
            raise ValueError('Candidate pool size/cap/Flash declaration changed')
        actual['file_bytes'] = len(blob)
        actual['id'] = index
        measured.append(actual)
    base = measured[0]
    feasible, eligible = [], []
    for row,claimed in zip(measured,report['candidates']):
        fits = row['file_bytes'] <= report['complete_byte_cap']
        allowed = fits and all(admission(row,base,C).values())
        if claimed['admissible'] != allowed:
            raise ValueError('Local pool admission does not reproduce')
        if fits:
            feasible.append(row)
        if allowed:
            eligible.append(row)
    key = lambda row: (row['score'],row['file_bytes'],row['id'])
    for label,rows in (('selected',eligible),('raw',feasible)):
        expected = min(rows,key=key)['id'] if rows else None
        if report[label+'_id'] != expected:
            raise ValueError('Local pool ranking does not reproduce')
    frontier,best = [],float('inf')
    for row in sorted(eligible,key=lambda r:(r['file_bytes'],r['score'],r['id'])):
        if row['score'] < best:
            frontier.append(row['id'])
            best = row['score']
    assert_close(frontier,report['frontier'])
    assert_close(dict(voice=evaluator[1].describe(),noise=evaluator[2].describe(),
        domains=['native_pcm16','fixed_pwm8'],aggregation='mean of voice + noise'),report['objective'])
    return measured


def verify_v1_seeds(blobs, anchor, target, saved, C, common, only, counters):
    track = C.track_pitch(target)
    objective = C.VoiceObjective(target,track.period)
    rows = []
    for blob in blobs:
        pcm = V1.verify_chain([blob],[(len(target),saved['profile'])],C,common,only,counters)
        rows.append(dict(file_bytes=len(blob), preQ14=C.compact.unpack(blob)[5],
            metrics=C._quality(target,pcm,True), voice=C.compare_voice(target,pcm,reference_track=track),
            pwm_voice=C.compare_voice(target,C.pwm_pcm16(pcm),reference_track=track),
            voice_score=objective(pcm),components=objective.components(pcm)))
    first = rows[0]
    for actual_key,saved_key in (('file_bytes','control_bytes'),('metrics','baseline_metrics'),
            ('voice','baseline_voice'),('pwm_voice','baseline_pwm_voice'),('voice_score','baseline_voice_score')):
        assert_close(first[actual_key],saved[saved_key])
    for trial in saved['trials']:
        matches = []
        for row in rows:
            if row['preQ14'] != trial['preQ14']:
                continue
            try:
                for key in ('file_bytes','metrics','voice','pwm_voice','voice_score','components'):
                    assert_close(row[key],trial[key])
                matches.append(row)
            except AssertionError:
                pass
        if not matches:
            raise ValueError('A saved V1 trial is not reproduced by any actual captured seed')
        row = matches[0]
        expected = dict(fits_complete_cap=row['file_bytes'] <= saved['complete_byte_cap'],
            old_pcm_pwm_floors_passed=bool(C.no_regression(row['metrics'],first['metrics'])),
            pcm_voice_proxy_floors_passed=bool(C._voice_gate(row['voice'],first['voice'])),
            pwm_voice_proxy_floors_passed=bool(C._voice_gate(row['pwm_voice'],first['pwm_voice'])))
        expected['voice_proxy_floors_passed'] = expected['pcm_voice_proxy_floors_passed'] and expected['pwm_voice_proxy_floors_passed']
        for key,value in expected.items():
            assert_close(value,trial[key])
    if anchor not in blobs:
        raise ValueError('The local admission anchor is not one of the actual V1 seeds')
    if saved['selected_bytes'] is not None:
        row = rows[blobs.index(anchor)]
        assert_close(row['file_bytes'],saved['selected_bytes'])
        assert_close(row['voice_score'],saved['selected_voice_score'])
        for key in ('metrics','voice','pwm_voice'):
            assert_close(row[key],saved['selected'][key])


def start_attempt(folder, identity):
    attempts = folder/'attempts'
    attempts.mkdir(parents=True,exist_ok=True)
    prior = [json.loads(p.read_text()) for p in sorted(attempts.glob('attempt-*-private.json'))]
    if any(a['identity'] != identity for a in prior):
        raise ValueError('An incomplete attempt belongs to another prepared epoch')
    number = len(prior)
    path = attempts/('attempt-%03d-private.json' % number)
    artifacts = attempts/('attempt-%03d' % number)
    state = dict(identity=identity,status='running',active_segment=None,
        new_seed_fit_attempts=0,operator_events=[],started_unix_ns=time.time_ns())
    save(path,state)
    return path,artifacts,state,prior


def operator_context(C, attempt, path):
    stack = ExitStack()
    def forbidden(*args,**kwargs):
        attempt['new_seed_fit_attempts'] += 1
        save(path,attempt)
        raise AssertionError('A new seed fit is forbidden by the frozen reuse protocol')
    stack.enter_context(patch.object(C.speech_v4,'encode',forbidden))
    for attribute,name in (('enhance','extras'),('refine_header','header_filters'),('refine','joint_lpc_excitation')):
        original = getattr(C.adaptive,attribute)
        def wrapper(*args,_original=original,_name=name,**kwargs):
            event = dict(segment=attempt['active_segment'],operator=_name,status='started')
            attempt['operator_events'].append(event)
            save(path,attempt)
            wall,cpu = time.perf_counter(),time.process_time()
            result = _original(*args,**kwargs)
            event.update(status='complete',wall_seconds=time.perf_counter()-wall,cpu_seconds=time.process_time()-cpu)
            save(path,attempt)
            return result
        stack.enter_context(patch.object(C.adaptive,attribute,wrapper))
    return stack


def job_inputs(record, previous, v1_folder):
    paths = [record['reference']['path'],*[s['path'] for s in record['segments']]]
    if previous is not None:
        paths += [v1_folder/'record-private.json',v1_folder/'complete-private.json']
        paths += [c['path'] for c in previous['captured_streams']]
    return paths


def run_record(job, binding, args, C, common, only):
    records = binding['speech_records'] if job['speech'] else binding['nonspeech_records']
    record = records[job['record_index']]
    folder = args.output/'records'/job['phase']/('source-%03d'%job['source_ordinal'])/('profile-%d'%record['profile'])
    identity = sha(canonical([binding['identity'],job]))
    if (folder/'complete-private.json').exists():
        return V1.inspect_cache(folder,identity),True
    path,artifacts,attempt,prior = start_attempt(folder,identity)
    started_wall,started_cpu = time.perf_counter(),time.process_time()
    counters = dict(native_output_domain_comparisons=0,model_samples=0)
    try:
        reference,original = V1.load_reference(record,C)
        original_pcm = V1.verify_chain(original,geometry(record),C,common,only,counters)
        assert_close(sha(original_pcm.astype('<i2').tobytes()),record['baseline_pcm16_sha256'])
        assert_close(sha(C.pwm_duties(original_pcm).tobytes()),record['baseline_pwm_sha256'])
        assert_close(C._quality(reference,original_pcm,job['speech']),record['baseline_metrics'])
        target,level = C.prepare_level(reference,job['mode']) if len(reference) <= 64000 else (reference.copy(),None)
        if level is None:
            if job['mode'] != 'preserve':
                raise ValueError('Long sources require one whole-source unchanged level')
            level = dict(policy='preserve',gain=1,gain_power2_exponent=0,gain_db=0.,output_level_matches_original=True)
        previous = v1_folder = None
        if job['speech']:
            previous,v1_folder = load_v1_record(Path(binding['v1_root']),binding['v1_binding'],job['v1_job'])
            if sha(target.astype('<i2').tobytes()) != previous['target_reference_pcm16_sha256']:
                raise ValueError('V2 evaluation target differs from its declared V1 level')
            legacy = next(c for c in previous['chains'] if c and c['role'] == 'control')
            selected_role = next(b['selected'] for b in previous['budgets'] if b['percent'] == 100)
            rollback = next(c for c in previous['chains'] if c and c['role'] == selected_role)
            verify_v1_chain(rollback,legacy,target,record,C,common,only,counters)
            control,control_paths = read_chain(rollback)
            legacy_blobs,legacy_paths = read_chain(legacy)
            local_selected = next((c for c in previous['chains'] if c and c['role'] == 'concat-selected'),None)
            local_selected_blobs = None if local_selected is None else read_chain(local_selected)[0]
        else:
            control,control_paths = original,[Path(s['path']) for s in record['segments']]
            legacy_blobs,legacy_paths = control,control_paths
            edited,errors = worst_and_tail(reference,original,record,C)
            assert_close(edited,job['edited_segments'])
            assert_close(errors,job['original_segment_pcm_sse'])
        paths_to_guard = job_inputs(record,previous,v1_folder)
        guard(binding,args,extra_paths=paths_to_guard)
        choices = {'concat-selected':list(control),'concat-raw':list(control)}
        choice_paths = {'concat-selected':list(control_paths),'concat-raw':list(control_paths)}
        segment_reports = []
        with operator_context(C,attempt,path):
            for index in job['edited_segments']:
                segment = record['segments'][index]
                at,n = segment['start'],segment['samples']
                local_target = target[at:at+n]
                if previous is not None:
                    captures = sorted((c for c in previous['captured_streams'] if c['segment'] == index),key=lambda c:c['capture_order'])
                    if [c['capture_order'] for c in captures] != list(range(len(captures))):
                        raise ValueError('V1 seed order changed')
                    seeds = []
                    for capture in captures:
                        blob = Path(capture['path']).read_bytes()
                        if len(blob) != capture['file_bytes'] or sha(blob) != capture['stream_sha256']:
                            raise ValueError('A source-bound V1 seed changed')
                        seeds.append(blob)
                    saved = previous['segment_searches'][index]['report']
                    if local_selected_blobs is None and saved['selected_bytes'] is not None:
                        raise ValueError('A local accepted V1 anchor lacks an actual saved stream')
                    anchor = seeds[0] if saved['selected_bytes'] is None else local_selected_blobs[index]
                    verify_v1_seeds(seeds,anchor,local_target,saved,C,common,only,counters)
                else:
                    seeds,anchor = [original[index]],original[index]
                attempt['active_segment'] = index
                save(path,attempt)
                captured,captured_paths = [],[]
                def sink(blob):
                    blob = bytes(blob)
                    output = artifacts/('segment-%03d'%index)/('pool-%04d.l4hy'%len(captured))
                    immutable_bytes(output,blob)
                    captured.append(blob)
                    captured_paths.append(output)
                event_start = len(attempt['operator_events'])
                selected,pcm,report,raw = C.adaptive.refine_candidates(local_target,anchor,seeds,common,
                    max_bytes=local_cap(record['baseline_bytes']),compact_decoder=only,speech=job['speech'],
                    max_refinement_calls=job['max_refinement_calls'],lpc_preset='expanded',
                    extra_full_evaluations=128,candidate_sink=sink)
                measured = validate_pool(captured,report,local_target,job['speech'],C,common,only,counters)
                events = attempt['operator_events'][event_start:]
                if ([e['operator'] for e in events] != [s['operator'] for s in report['stages']] or
                        any(e['status'] != 'complete' for e in events) or
                        len(events) != report['refinement_calls'] or len(events) > job['max_refinement_calls']):
                    raise ValueError('Actual operator calls do not reproduce the bounded controller stages')
                pool_meta = [dict(id=i,path=str(p.resolve()),stream_sha256=sha(b),file_bytes=len(b)) for i,(p,b) in enumerate(zip(captured_paths,captured))]
                for role,label,blob in (('concat-selected','selected',selected),('concat-raw','raw',raw)):
                    identifier = report[label+'_id']
                    if (identifier is None) != (blob is None) or identifier is not None and captured[identifier] != blob:
                        raise ValueError('Returned stream differs from the independently ranked actual pool')
                    choices[role][index] = blob
                    choice_paths[role][index] = None if blob is None else captured_paths[identifier]
                if selected is not None and not C.np.array_equal(pcm,C.compact.decode_model(selected)):
                    raise ValueError('Returned selected PCM differs from actual serialized output')
                segment_reports.append(dict(index=index,start=at,samples=n,seed_count=len(seeds),
                    anchor_stream_sha256=sha(anchor),seed_stream_sha256=[sha(b) for b in seeds],
                    pool=pool_meta,report=report,independent_pool_rows_recomputed=len(measured)))
        evaluator = evaluators(target,C)
        whole_control = chain_entry('control',control,control_paths,record,target,job['speech'],evaluator,None,C,common,only,counters)
        entries = [whole_control]+[chain_entry(role,choices[role],choice_paths[role],record,target,
            job['speech'],evaluator,whole_control,C,common,only,counters) for role in ('concat-selected','concat-raw')]
        legacy_comparison = chain_entry('legacy-comparison',legacy_blobs,legacy_paths,record,target,
            job['speech'],evaluator,whole_control,C,common,only,counters)
        budgets = [choose_budget(entries,record['baseline_bytes'],percent) for percent in (100,95,90)]
        if budgets[0]['selected'] is None or attempt['new_seed_fit_attempts']:
            raise ValueError('The whole rollback vanished or a new seed fit was attempted')
        guard(binding,args,extra_paths=paths_to_guard)
        V1.load_reference(record,C)
        if previous is not None:
            load_v1_record(Path(binding['v1_root']),binding['v1_binding'],job['v1_job'])
        result = dict(schema='lpx-adaptive-voice-record-private-v2',identity=identity,**job,
            profile=record['profile'],samples=len(reference),split=record['split'],cohort=record['cohort'],
            targeted_not_independent_heldout=record['reference']['pcm16_sha256'] == binding['targeted_reference_pcm16_sha256'],
            level=level,original_complete_bytes=record['baseline_bytes'],local_complete_cap=local_cap(record['baseline_bytes']),
            original_reference_pcm16_sha256=sha(reference.astype('<i2').tobytes()),
            target_reference_pcm16_sha256=sha(target.astype('<i2').tobytes()),
            target_pwm_voice=C.compare_voice(target,C.pwm_pcm16(target),reference_track=evaluator[0]),
            original_level_control=dict(segments=record['segments'],metrics=record['baseline_metrics'],
                pcm16_sha256=record['baseline_pcm16_sha256'],pwm_sha256=record['baseline_pwm_sha256']),
            declared_level_legacy_comparison=legacy_comparison,
            objective=dict(voice=evaluator[1].describe(),noise=evaluator[2].describe(),
                domains=['native_pcm16','fixed_pwm8'],aggregation='mean of voice + noise'),
            chains=entries,budgets=budgets,segment_searches=segment_reports,
            actual_refinement_calls=len(attempt['operator_events']),new_seed_fit_attempts=0,
            prior_attempts=prior,prior_incomplete_attempts=sum(a['status'] != 'complete' for a in prior),
            all_attempts_started_refinement_calls=len(attempt['operator_events'])+sum(len(a['operator_events']) for a in prior),
            all_attempts_completed_refinement_calls=len(attempt['operator_events'])+sum(sum(e['status']=='complete' for e in a['operator_events']) for a in prior),
            validation=counters,wall_seconds=time.perf_counter()-started_wall,cpu_seconds=time.process_time()-started_cpu,
            source_module_origins=assert_origins(args.source_root),
            scope='Three full measured chains; reusable V1 seeds; no cap refit/segment mixture/new seed fit; levels remain separate.')
        save(folder/'record-private.json',result)
        attempt.update(status='complete',active_segment=None,wall_seconds=result['wall_seconds'],cpu_seconds=result['cpu_seconds'])
        save(path,attempt)
        artifact_files = [*folder.rglob('*.l4hy'),*folder.joinpath('attempts').glob('attempt-*-private.json')]
        artifact_hashes = {p.relative_to(folder).as_posix():sha(p.read_bytes()) for p in artifact_files}
        save(folder/'complete-private.json',dict(identity=identity,report_sha256=sha((folder/'record-private.json').read_bytes()),artifacts_sha256=artifact_hashes))
        return result,False
    except BaseException as exc:
        attempt.update(status='failed',exception_type=type(exc).__name__,wall_seconds=time.perf_counter()-started_wall,cpu_seconds=time.process_time()-started_cpu)
        save(path,attempt)
        raise


def worker(args,C):
    binding_path = args.output/'binding-private.json'
    raw = binding_path.read_bytes()
    binding = json.loads(raw)
    V1.validate_binding(binding)
    if binding['source_root'] != str(args.source_root):
        raise ValueError('Worker source root differs from the prepared implementation')
    guard(binding,args,all_inputs=True)
    jobs = [j for j in binding['jobs'] if j['phase'] == args.phase and j['source_ordinal']%2 == args.shard]
    report = dict(schema='lpx-adaptive-voice-worker-private-v2',status='running',identity=binding['identity'],
        binding_sha256=sha(raw),phase=args.phase,shard=args.shard,records=[],executed_records=0,reused_records=0,
        new_seed_fit_attempts=0,executed_refinement_calls=0)
    output = args.output/'workers'/(args.phase+'-shard-%d-private.json'%args.shard)
    started_wall,started_cpu = time.perf_counter(),time.process_time()
    save(output,report)
    with C.BatchSession('batch',prebuilt=args.output/'native/common.so') as common, C.BatchSession('batch',prebuilt=args.output/'native/v5-only.so') as only:
        for number,job in enumerate(jobs,1):
            if binding_path.read_bytes() != raw:
                raise ValueError('The prepared binding changed during worker execution')
            guard(binding,args)
            row,reused = run_record(job,binding,args,C,common,only)
            report['records'].append(row)
            report['reused_records' if reused else 'executed_records'] += 1
            if not reused:
                report['executed_refinement_calls'] += row['actual_refinement_calls']
            report.update(wall_seconds=time.perf_counter()-started_wall,cpu_seconds=time.process_time()-started_cpu)
            save(output,report)
            print(json.dumps(dict(phase=args.phase,shard=args.shard,completed_groups=number,total_groups=len(jobs),reused=reused)),flush=True)
    guard(binding,args,all_inputs=True)
    if binding_path.read_bytes() != raw:
        raise ValueError('The prepared binding changed at worker completion')
    report.update(status='complete',wall_seconds=time.perf_counter()-started_wall,cpu_seconds=time.process_time()-started_cpu,
        recorded_refinement_calls=sum(r['actual_refinement_calls'] for r in report['records']),
        recorded_all_attempt_started_refinement_calls=sum(r['all_attempts_started_refinement_calls'] for r in report['records']))
    save(output,report)
    print(json.dumps(dict(phase=args.phase,status='complete',shard=args.shard,groups=len(jobs),
        new_seed_fit_attempts=0,executed_refinement_calls=report['executed_refinement_calls'],reused_records=report['reused_records'])),flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--core-commit')
    parser.add_argument('--v1-root',type=Path)
    parser.add_argument('--v1-audit',type=Path)
    parser.add_argument('--nonspeech-manifest',type=Path)
    parser.add_argument('--phase',choices=PHASES)
    parser.add_argument('--shard',type=int,choices=(0,1))
    args = parser.parse_args()
    for name in ('source_root','output','v1_root','v1_audit','nonspeech_manifest'):
        if getattr(args,name) is not None:
            setattr(args,name,getattr(args,name).resolve())
    if not args.output.is_relative_to((args.source_root/'build').resolve()):
        parser.error('Private output must stay under source-root/build')
    if args.prepare:
        if (any(getattr(args,k) is None for k in ('core_commit','v1_root','v1_audit','nonspeech_manifest')) or
                args.phase is not None or args.shard is not None or args.output.exists()):
            parser.error('Prepare requires a fresh output, explicit commit and V1/nonspeech inputs only')
    elif (args.phase is None or args.shard is None or
            any(getattr(args,k) is not None for k in ('core_commit','v1_root','v1_audit','nonspeech_manifest'))):
        parser.error('A worker requires only its prepared binding, phase and shard')
    temporary = args.output/'tmp'/('prepare' if args.prepare else args.phase+'-shard-'+str(args.shard))
    temporary.mkdir(parents=True,exist_ok=True)
    tempfile.tempdir = str(temporary)
    os.environ['TMP'] = os.environ['TEMP'] = str(temporary)
    os.environ['NUMBA_CACHE_DIR'] = str(temporary/'numba-cache')
    try:
        C = load_core(args.source_root)
        if args.prepare:
            prepare(args,C)
        else:
            worker(args,C)
    except Exception as exc:
        phase = 'prepare' if args.prepare else args.phase+'-shard-'+str(args.shard)
        failures = args.output/'failures'/phase
        failures.mkdir(parents=True,exist_ok=True)
        number = len(list(failures.glob('failure-*-private.json')))
        save(failures/('failure-%03d-private.json'%number),dict(exception_type=type(exc).__name__,
            traceback=traceback.format_exc(),phase=phase))
        print(json.dumps(dict(status='failed',phase=phase,exception_type=type(exc).__name__)),flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Independent read-only audit of completed, source-bound V2 saved streams.

Never imports the study driver or invokes an encoder/refinement/selection API.
Only decoding and source-feature/metric primitives are reused. Private paths,
audio/stream/native fingerprints and exception details remain in build output.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace

PREFIX = 'Codecs/LPX/01_ACTIVE_Q0_CODEC/'
PHASES = ('speech-screen', 'speech-default', 'nonspeech-default')
PRIORITY = {'control': 0, 'concat-selected': 1, 'concat-raw': 2}


def sha(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.exists() and path.stat().st_nlink > 1:
        raise ValueError('Audit output aliases are forbidden')
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def equal(actual, claimed, context='value'):
    if isinstance(claimed, dict):
        if not isinstance(actual, dict) or actual.keys() != claimed.keys():
            raise AssertionError('Dictionary shape mismatch: '+context)
        for name in claimed:
            equal(actual[name], claimed[name], context+'.'+name)
    elif isinstance(claimed, list):
        if not isinstance(actual, list) or len(actual) != len(claimed):
            raise AssertionError('List shape mismatch: '+context)
        for a, b in zip(actual, claimed):
            equal(a, b, context)
    elif isinstance(claimed, (int, float)) and not isinstance(claimed, bool):
        if (not isinstance(actual, (int, float)) or isinstance(actual, bool)
                or not math.isfinite(actual) or abs(actual-claimed) > 1e-12):
            raise AssertionError('Numerical mismatch: '+context)
    elif type(actual) != type(claimed) or actual != claimed:
        raise AssertionError('Value mismatch: '+context)


def metric_floor(candidate, anchor):
    metric = True
    for domain in ('pcm16', 'pwm8'):
        new, old = candidate[domain], anchor[domain]
        metric &= new['error_energy'] <= old['error_energy']
        if old['stoi'] is not None:
            metric &= new['stoi'] is not None and new['stoi'] >= old['stoi']-1e-12
    return bool(metric)


def floors(candidate, anchor):
    return dict(old_pcm_pwm_floors_passed=metric_floor(candidate['metrics'], anchor['metrics']),
        clipped_sample_floor_passed=candidate['clipped_samples'] <= anchor['clipped_samples'],
        pcm_period_coverage_floor_passed=candidate['voice']['within_tolerance_frames'] >= anchor['voice']['within_tolerance_frames'],
        pwm_period_coverage_floor_passed=candidate['pwm_voice']['within_tolerance_frames'] >= anchor['pwm_voice']['within_tolerance_frames'],
        joint_objective_nonregression=candidate['score'] <= anchor['score']+1e-12)


def old_voice_floor(candidate, anchor):
    if (candidate['within_tolerance_frames'] < anchor['within_tolerance_frames']
            or candidate['decoded_collapsed_active_frames'] > anchor['decoded_collapsed_active_frames']):
        return False
    for name in ('fixed_decoded_period_error_mean','relative_spectral_shape_rms_db_mean'):
        before, after = anchor[name], candidate[name]
        if before is not None and (after is None or after > before+1e-12):
            return False
    return True


def rank_pool(rows, cap):
    good, feasible, allowed = [], [], []
    for row in rows:
        fits = row['file_bytes'] <= cap
        admitted = fits and all(floors(row, rows[0]).values())
        allowed.append(admitted)
        if fits:
            feasible.append(row)
        if admitted:
            good.append(row)
    key = lambda r: (r['score'], r['file_bytes'], r['id'])
    selected = min(good, key=key)['id'] if good else None
    raw = min(feasible, key=key)['id'] if feasible else None
    frontier, loss = [], float('inf')
    for row in sorted(good, key=lambda r: (r['file_bytes'], r['score'], r['id'])):
        if row['score'] < loss:
            loss = row['score']
            frontier.append(row['id'])
    return dict(selected_id=selected, raw_id=raw, frontier=frontier), allowed


def budget_choice(entries, original_bytes, percent):
    if type(original_bytes) is not int or original_bytes < 22 or percent not in (100, 95, 90):
        raise ValueError('Invalid whole byte ceiling')
    cap = original_bytes*percent//100
    fit = [e for e in entries if e is not None and e['stream_bytes'] <= cap]
    good = [e for e in fit if e['automatic_quality_eligible']]
    key = lambda e: (e['score'], e['stream_bytes'], PRIORITY[e['role']])
    return dict(percent=percent, cap=cap,
        selected=min(good, key=key)['role'] if good else None,
        raw_tradeoff=min(fit, key=key)['role'] if fit else None,
        fitting_chain_count=len(fit), eligible_chain_count=len(good),
        distinct_fitting_chain_count=len({tuple(e['identity']) for e in fit}),
        no_fit=not fit, no_automatic_admission=not good)


def groups(records):
    result = {}
    for index, row in enumerate(records):
        result.setdefault(row['private_case_id'], []).append(index)
    output = list(result.values())
    for pair in output:
        rows = [records[i] for i in pair]
        if (len(pair) != 2 or {r['profile'] for r in rows} != {4, 6}
                or len({r['samples'] for r in rows}) != 1
                or len({r['reference']['pcm16_sha256'] for r in rows}) != 1):
            raise AssertionError('Paired source/profile geometry changed')
    return output


def representatives(records, paired, excluded=()):
    ordered = sorted((i for i in range(len(paired)) if i not in excluded),
        key=lambda i: (records[paired[i][0]]['samples'], i))
    return [ordered[0], ordered[len(ordered)//2], ordered[-1]]


def load_primitives(root):
    sys.path.insert(0, str(root/PREFIX/'tools'))
    import numpy as np
    import soundfile as sf
    import speech_compact as compact
    from batch_decoder import BatchSession
    from standard_metrics import error_metrics, pwm_duties, pwm_pcm16
    from voice_character import track_pitch, compare_voice
    from voice_input import plan_level, quantize_target
    from speech_noise_objective import NoiseObjective
    # Import the same modules solely for strict source-origin attestation.
    import adaptive_speech_voice
    import benchmark_speech_flash
    origins = {}
    tools = (root/PREFIX/'tools').resolve()
    for name, module in list(sys.modules.items()):
        path = getattr(module, '__file__', None)
        if path is not None and ('/'+PREFIX+'tools/').casefold() in Path(path).as_posix().casefold():
            if Path(path).resolve().parent != tools:
                raise AssertionError('A cached primitive belongs to another checkout')
            origins[name] = Path(path).resolve().relative_to(root).as_posix()
    return SimpleNamespace(**locals())


def runtime():
    compiler = shutil.which('g++')
    if compiler is None:
        raise ValueError('Pinned compiler runtime is missing')
    return dict(python=sys.version, executable_sha256=sha(Path(sys.executable).read_bytes()),
        platform=platform.platform(),
        packages={n: version(n) for n in ('numpy', 'numba', 'scipy', 'pystoi', 'soundfile')},
        compiler_file_sha256=sha(Path(compiler).read_bytes()),
        compiler_version=subprocess.check_output([compiler, '--version'], encoding='utf-8', errors='replace').splitlines()[0],
        threads={k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS')})


class Auditor:
    def __init__(self, root, study, output):
        self.root, self.study, self.output = root, study, output
        self.binding_raw = (study/'binding-private.json').read_bytes()
        self.binding = json.loads(self.binding_raw)
        self.auditor_source = sha(Path(__file__).read_bytes())
        self.C = load_primitives(root)
        self.decoded, self.features, self.measures = {}, {}, {}
        self.counts = Counter()
        self.rows = []

    def context(self):
        b = self.binding
        equal(sha(Path(__file__).read_bytes()),self.auditor_source,'executing-auditor-source')
        if b['identity'] != sha(canonical({k: v for k, v in b.items() if k != 'identity'})):
            raise AssertionError('Prepared binding identity changed')
        if b['source_root'] != str(self.root) or b['schema'] != 'lpx-adaptive-voice-binding-private-v2':
            raise AssertionError('Wrong source root or binding schema')
        active = self.root/PREFIX
        files = [*(active/'tools').glob('*.py'), *(active/'tests').glob('test_*.py'),
                 *(p for p in (active/'src').rglob('*') if p.is_file())]
        actual = {p.relative_to(self.root).as_posix(): sha(p.read_bytes()) for p in files}
        equal(actual, b['source']['core'], 'frozen-source')
        if not hasattr(self, 'committed_source'):
            names = subprocess.check_output(['git','-C',str(self.root),'ls-tree','-r','--name-only',b['core_commit'],
                '--',PREFIX+'tools',PREFIX+'tests',PREFIX+'src'],text=True).splitlines()
            expected_names = [name for name in names if name.startswith(PREFIX+'src/') or
                name.startswith(PREFIX+'tools/') and name.endswith('.py') and '/' not in name[len(PREFIX+'tools/'):] or
                name.startswith(PREFIX+'tests/test_') and name.endswith('.py') and '/' not in name[len(PREFIX+'tests/'):]]
            self.committed_source = {name:sha(subprocess.check_output(['git','-C',str(self.root),'show',b['core_commit']+':'+name]))
                                     for name in expected_names}
        equal(actual, self.committed_source, 'explicit-core-commit')
        for path, digest in b['source']['research'].items():
            equal(sha(Path(path).read_bytes()), digest, 'research-source')
        equal(runtime(), b['environment'], 'runtime')
        for name, origin in b['module_origins'].items():
            if self.C.origins.get(name) != origin:
                raise AssertionError('Prepared primitive origin differs')
        for name, digest in b['input_files_sha256'].items():
            equal(sha(Path(name).read_bytes()), digest, 'bound-input')
        for name, digest in b['native_libraries_sha256'].items():
            equal(sha((self.study/'native'/name).read_bytes()), digest, 'native-library')
        equal((self.study/'binding-private.json').read_bytes(), self.binding_raw, 'binding-during-audit')

    def reference(self, record):
        descriptor = record['reference']
        raw = Path(descriptor['path']).read_bytes()
        equal(len(raw), descriptor['file_bytes'], 'reference-length')
        equal(sha(raw), descriptor['file_sha256'], 'reference-file')
        pcm, rate = self.C.sf.read(descriptor['path'], dtype='int16')
        if rate != 8000 or pcm.ndim != 1 or len(pcm) != record['samples']:
            raise AssertionError('Full source PCM geometry changed')
        equal(sha(pcm.astype('<i2').tobytes()), descriptor['pcm16_sha256'], 'reference-pcm')
        return pcm

    def stream(self, descriptor, expected=None):
        blob = Path(descriptor['path']).read_bytes()
        equal(len(blob), descriptor['file_bytes'], 'stream-length')
        equal(sha(blob), descriptor['stream_sha256'], 'stream-content')
        if expected is not None:
            n, profile = self.C.compact.unpack(blob)[:2]
            if (n, profile) != expected:
                raise AssertionError('Actual reset length/profile changed')
        return blob

    def decode(self, blob, geometry):
        if self.C.compact.unpack(blob)[:2] != geometry:
            raise AssertionError('Decoder geometry changed')
        key = sha(blob)
        if key not in self.decoded:
            pcm = self.C.compact.decode_model(blob)
            duty = self.C.pwm_duties(pcm)
            for receiver in (self.common, self.only):
                actual = receiver.decode_one_s16(blob, geometry[0])
                pwm = receiver.decode_one(blob, geometry[0])
                if (actual is None or pwm is None or not self.C.np.array_equal(actual, pcm)
                        or not self.C.np.array_equal(pwm, duty)):
                    raise AssertionError('Native/model PCM or PWM differs')
                self.counts['unique_native_domain_comparisons'] += 2
            self.decoded[key] = pcm
            self.counts['unique_streams'] += 1
            self.counts['unique_model_samples'] += len(pcm)
        else:
            self.counts['decoded_cache_hits'] += 1
        return self.decoded[key]

    def evaluate(self, target, pcm, speech):
        c = self.C
        ref_key = sha(target.astype('<i2').tobytes())
        key = (ref_key, sha(pcm.astype('<i2').tobytes()), bool(speech))
        if key in self.measures:
            self.counts['metric_cache_hits'] += 1
            return self.measures[key]
        if ref_key not in self.features:
            track = c.track_pitch(target)
            noise = c.NoiseObjective(target, track.period)
            self.features[ref_key] = (track, noise.voice_objective, noise)
        track, voice, noise = self.features[ref_key]
        pwm = c.pwm_pcm16(pcm)
        metrics = {domain: c.error_metrics(target, data, bool(speech))
                   for domain, data in (('pcm16', pcm), ('pwm8', pwm))}
        for row in metrics.values():
            if row['stoi'] is not None and not math.isfinite(row['stoi']):
                row['stoi'] = None
        n = [noise.summary(data) for data in (pcm, pwm)]
        scores = [float(voice(data)+entry['score']) for data, entry in zip((pcm, pwm), n)]
        if any(not math.isfinite(s) for s in scores):
            raise AssertionError('Nonfinite objective')
        value = dict(metrics=metrics,
            voice=c.compare_voice(target, pcm, reference_track=track),
            pwm_voice=c.compare_voice(target, pwm, reference_track=track),
            noise=n[0], pwm_noise=n[1], domain_scores=scores, score=float(c.np.mean(scores)),
            clipped_samples=int(c.np.count_nonzero((pcm <= -32768) | (pcm >= 32767))),
            voice_components=voice.components(pcm), pwm_voice_components=voice.components(pwm))
        self.measures[key] = value
        self.counts['unique_metric_rows'] += 1
        return value

    def chain(self, chain, record, target, speech, anchor=None):
        if chain is None:
            return None
        if len(chain['segments']) != len(record['segments']):
            raise AssertionError('Chain reset count changed')
        parts, blobs = [], []
        offset = 0
        for index, (stored, original) in enumerate(zip(chain['segments'], record['segments'])):
            expected = (original['samples'], record['profile'])
            for key, value in dict(index=index, start=offset, samples=expected[0], profile=expected[1]).items():
                equal(stored[key], value, 'chain-reset-'+key)
            blob = self.stream(stored, expected)
            parts.append(self.decode(blob, expected))
            blobs.append(blob)
            offset += expected[0]
        pcm = self.C.np.concatenate(parts)
        if len(pcm) != len(target) or offset != record['samples']:
            raise AssertionError('Full chain/source coverage differs')
        value = self.evaluate(target, pcm, speech)
        for key, actual in value.items():
            equal(actual, chain[key], 'whole-'+key)
        equal(sha(pcm.astype('<i2').tobytes()), chain['pcm16_sha256'], 'whole-pcm')
        equal(sha(self.C.pwm_duties(pcm).tobytes()), chain['pwm_sha256'], 'whole-pwm')
        equal(sum(map(len, blobs)), chain['stream_bytes'], 'whole-byte-cost')
        equal(len(target), chain['samples'], 'whole-samples')
        flags = floors(value, value if anchor is None else anchor)
        for name, flag in flags.items():
            equal(flag, chain[name], 'whole-'+name)
        equal(all(flags.values()), chain['automatic_quality_eligible'], 'whole-admission')
        return dict(role=chain['role'], stream_bytes=sum(map(len, blobs)), identity=[sha(b) for b in blobs],
                    automatic_quality_eligible=all(flags.values()), **value)

    def pool(self, segment, local, speech, profile, limit, events):
        report = segment['report']
        equal(report['samples'], len(local), 'local-samples')
        equal(report['profile'], profile, 'local-profile')
        equal(report['max_refinement_calls'], limit, 'local-call-limit')
        if (report['full_flash_cap'] is not None or report['full_flash_measured']
                or report['native_v5_only_checked'] is not True or report['native_common_and_model_exact'] is not True):
            raise AssertionError('Local measurement scope changed')
        if len(segment['pool']) != len(report['candidates']):
            raise AssertionError('Candidate sink count differs')
        measured, blobs = [], []
        for index, (meta, claimed) in enumerate(zip(segment['pool'], report['candidates'])):
            equal(index, meta['id'], 'sink-order')
            blob = self.stream(meta, (len(local), profile))
            if blob in blobs:
                raise AssertionError('Duplicate actual stream in deduplicated pool')
            blobs.append(blob)
            value = self.evaluate(local, self.decode(blob, (len(local), profile)), speech)
            for key in ('metrics','voice','pwm_voice','noise','pwm_noise','domain_scores','score','clipped_samples'):
                equal(value[key], claimed[key], 'pool-'+key)
            for key, expected in dict(id=index, file_bytes=len(blob), full_flash_bytes=None,
                    fits_complete_cap=len(blob) <= report['complete_byte_cap'], fits_flash_cap=True).items():
                equal(expected, claimed[key], 'pool-'+key)
            measured.append(dict(id=index, file_bytes=len(blob), **value))
        equal(sha(blobs[0]), segment['anchor_stream_sha256'], 'local-anchor')
        ranking, allowed = rank_pool(measured, report['complete_byte_cap'])
        for key, value in ranking.items():
            equal(value, report[key], 'pool-'+key)
        for row, flag in zip(report['candidates'], allowed):
            equal(flag, row['admissible'], 'pool-admission')
        for label in ('selected', 'raw'):
            identifier = ranking[label+'_id']
            equal(None if identifier is None else len(blobs[identifier]), report[label+'_bytes'], 'returned-'+label)
        equal(report['selected_id'] is not None and blobs[report['selected_id']] != blobs[0],
              report['selected_differs_from_control'], 'local-change')
        stages = report['stages']
        equal(len(stages), report['refinement_calls'], 'local-stage-count')
        if len(stages) > limit or len(events) != len(stages):
            raise AssertionError('Actual work exceeds declared refinement budget')
        for stage, event in zip(stages, events):
            equal(stage['operator'], event['operator'], 'actual-operator')
            if event['status'] != 'complete' or event['segment'] != segment['index']:
                raise AssertionError('Incomplete or wrong-segment operator event')
            if not 0 <= stage['parent'] < len(blobs) or any(not 0 <= i < len(blobs) for i in stage['outputs']):
                raise AssertionError('Stage refers to absent pool bytes')
        self.counts['local_pool_rows'] += len(blobs)
        self.counts['local_searches'] += 1
        self.counts['actual_refinement_calls'] += len(stages)
        return blobs, ranking

    def v1_context(self, job, record, target):
        previous_binding = self.binding['v1_binding']
        folder = Path(self.binding['v1_root'])/'records'/('source-%03d'%job['source_ordinal'])/('profile-%d'%record['profile'])/job['mode']
        marker = json.loads((folder/'complete-private.json').read_text())
        identity = sha(canonical([previous_binding['identity'],job['v1_job']]))
        equal(identity,marker['identity'],'v1-cache-identity')
        raw = (folder/'record-private.json').read_bytes()
        equal(sha(raw),marker['report_sha256'],'v1-record')
        for name, digest in marker['artifacts_sha256'].items():
            path = (folder/name).resolve()
            if not path.is_relative_to(folder.resolve()):
                raise AssertionError('V1 artifact escapes its record')
            equal(sha(path.read_bytes()),digest,'v1-artifact')
        previous = json.loads(raw)
        equal(sha(target.astype('<i2').tobytes()),previous['target_reference_pcm16_sha256'],'v1-target-level')
        values = []
        identities = {}
        base = None
        for chain in previous['chains']:
            if chain is None:
                values.append(None)
                continue
            if len(chain['segments']) != len(record['segments']):
                raise AssertionError('V1 reset chain differs')
            blobs = [self.stream(meta,(segment['samples'],record['profile']))
                     for meta, segment in zip(chain['segments'],record['segments'])]
            pcm = self.C.np.concatenate([self.decode(blob,(segment['samples'],record['profile']))
                                        for blob,segment in zip(blobs,record['segments'])])
            measured = self.evaluate(target,pcm,True)
            equal(measured['metrics'],chain['metrics'],'v1-whole-metrics')
            equal(measured['voice'],chain['voice'],'v1-whole-voice')
            equal(measured['pwm_voice'],chain['pwm_voice'],'v1-whole-pwm-voice')
            noise = self.features[sha(target.astype('<i2').tobytes())][2]
            score = noise.voice_objective(pcm)
            equal(score,chain['voice_score'],'v1-whole-objective')
            equal(noise.voice_objective.components(pcm),chain['voice_components'],'v1-whole-objective-components')
            equal(sha(pcm.astype('<i2').tobytes()),chain['pcm16_sha256'],'v1-whole-pcm')
            equal(sha(self.C.pwm_duties(pcm).tobytes()),chain['pwm_sha256'],'v1-whole-pwm')
            equal(sum(map(len,blobs)),chain['stream_bytes'],'v1-whole-bytes')
            if base is None:
                if chain['role'] != 'control':
                    raise AssertionError('V1 legacy control is not first')
                base = (measured,score)
            anchor,anchor_score = base
            flags = dict(old_pcm_pwm_floors_passed=metric_floor(measured['metrics'],anchor['metrics']),
                pcm_voice_proxy_floors_passed=old_voice_floor(measured['voice'],anchor['voice']),
                pwm_voice_proxy_floors_passed=old_voice_floor(measured['pwm_voice'],anchor['pwm_voice']),
                voice_objective_nonregression=score <= anchor_score+1e-12)
            for name, flag in flags.items():
                equal(flag,chain[name],'v1-whole-'+name)
            equal(all(flags.values()),chain['automatic_quality_eligible'],'v1-whole-admission')
            row = dict(role=chain['role'],score=score,stream_bytes=sum(map(len,blobs)),
                identity=[sha(blob) for blob in blobs],automatic_quality_eligible=all(flags.values()))
            values.append(row)
            identities[chain['role']] = row['identity']
        decisions = [budget_choice(values,record['baseline_bytes'],p) for p in (100,95,90)]
        equal(decisions,previous['budgets'],'v1-whole-decisions')
        if decisions[0]['selected'] is None:
            raise AssertionError('V1 full rollback is absent')
        return previous, identities[decisions[0]['selected']], identities['control']

    def completed_record(self, job):
        b, c = self.binding, self.C
        records = b['speech_records'] if job['speech'] else b['nonspeech_records']
        record = records[job['record_index']]
        folder = self.study/'records'/job['phase']/('source-%03d'%job['source_ordinal'])/('profile-%d'%record['profile'])
        marker = json.loads((folder/'complete-private.json').read_text())
        identity = sha(canonical([b['identity'], job]))
        equal(identity, marker['identity'], 'completion-identity')
        report_raw = (folder/'record-private.json').read_bytes()
        equal(sha(report_raw), marker['report_sha256'], 'record-content')
        for name, digest in marker['artifacts_sha256'].items():
            path = (folder/name).resolve()
            if not path.is_relative_to(folder.resolve()):
                raise AssertionError('Recorded artifact escapes its record')
            equal(sha(path.read_bytes()), digest, 'record-artifact')
        row = json.loads(report_raw)
        for key, value in job.items():
            equal(value, row[key], 'job-'+key)
        reference = self.reference(record)
        originals = [self.stream(s, (s['samples'], record['profile'])) for s in record['segments']]
        original_pcm = c.np.concatenate([self.decode(blob, (s['samples'], record['profile'])) for blob, s in zip(originals, record['segments'])])
        equal(sha(original_pcm.astype('<i2').tobytes()), record['baseline_pcm16_sha256'], 'original-pcm')
        equal(sha(c.pwm_duties(original_pcm).tobytes()), record['baseline_pwm_sha256'], 'original-pwm')
        original_metrics = self.evaluate(reference, original_pcm, job['speech'])['metrics']
        equal(original_metrics, record['baseline_metrics'], 'original-metrics')
        plan = c.plan_level(reference, job['mode'])
        target, clips = c.quantize_target(reference, plan)
        if clips:
            raise AssertionError('Declared target gain clipped')
        for key in ('policy','gain','gain_db','output_level_matches_original'):
            equal(plan[key], row['level'][key], 'declared-level-'+key)
        equal(sha(reference.astype('<i2').tobytes()), row['original_reference_pcm16_sha256'], 'record-original-reference')
        equal(sha(target.astype('<i2').tobytes()), row['target_reference_pcm16_sha256'], 'record-target-reference')
        equal(row['targeted_not_independent_heldout'], record['reference']['pcm16_sha256'] == b['targeted_reference_pcm16_sha256'], 'targeted-marker')
        if not job['speech']:
            errors = [int(c.np.sum((reference[s['start']:s['start']+s['samples']].astype(c.np.int64)
                       - self.decode(blob, (s['samples'],record['profile'])).astype(c.np.int64))**2))
                      for blob, s in zip(originals, record['segments'])]
            worst = max(range(len(errors)), key=lambda i: (Fraction(errors[i], record['segments'][i]['samples']), -i))
            equal(errors, job['original_segment_pcm_sse'], 'nonspeech-original-segment-error')
            equal(list(dict.fromkeys([worst,len(errors)-1])), job['edited_segments'], 'nonspeech-bounded-segments')
        previous = None
        if job['speech']:
            previous,v1_rollback_identity,v1_legacy_identity = self.v1_context(job,record,target)
        attempts = [json.loads(p.read_text()) for p in sorted((folder/'attempts').glob('attempt-*-private.json'))]
        if not attempts or attempts[-1]['status'] != 'complete':
            raise AssertionError('Final actual attempt is not complete')
        equal(attempts[:-1], row['prior_attempts'], 'prior-attempts')
        if any(a['identity'] != identity or a['new_seed_fit_attempts'] != 0 for a in attempts):
            raise AssertionError('Wrong epoch or fresh seed fit in actual journal')
        started = sum(len(a['operator_events']) for a in attempts)
        finished = sum(sum(e['status']=='complete' for e in a['operator_events']) for a in attempts)
        equal(started, row['all_attempts_started_refinement_calls'], 'all-started-work')
        equal(finished, row['all_attempts_completed_refinement_calls'], 'all-completed-work')
        equal(len(attempts[-1]['operator_events']), row['actual_refinement_calls'], 'current-work')
        equal(sum(a['status']!='complete' for a in attempts[:-1]), row['prior_incomplete_attempts'], 'failed-attempt-count')
        self.counts['all_attempt_started_calls'] += started
        self.counts['all_attempt_completed_calls'] += finished
        self.counts['prior_incomplete_attempts'] += row['prior_incomplete_attempts']
        searches = row['segment_searches']
        equal([s['index'] for s in searches], job['edited_segments'], 'actual-edited-segments')
        local_results = {}
        for search in searches:
            index = search['index']
            segment = record['segments'][index]
            equal(search['start'], segment['start'], 'local-start')
            equal(search['samples'], segment['samples'], 'local-length')
            equal(min(record['baseline_bytes'],65535), search['report']['complete_byte_cap'], 'local-cap')
            events = [e for e in attempts[-1]['operator_events'] if e['segment'] == index]
            blobs, ranking = self.pool(search,target[segment['start']:segment['start']+segment['samples']],
                job['speech'],record['profile'],job['max_refinement_calls'],events)
            if previous is not None:
                captures = sorted((s for s in previous['captured_streams'] if s['segment']==index),key=lambda s:s['capture_order'])
                equal([s['capture_order'] for s in captures],list(range(len(captures))),'v1-capture-order')
                seeds = [self.stream(s,(segment['samples'],record['profile'])) for s in captures]
                saved = previous['segment_searches'][index]['report']
                selected = next((chain for chain in previous['chains'] if chain is not None and chain['role']=='concat-selected'),None)
                anchor = seeds[0] if saved['selected_bytes'] is None else self.stream(selected['segments'][index],(segment['samples'],record['profile']))
            else:
                seeds,anchor = [originals[index]],originals[index]
            equal(len(seeds),search['seed_count'],'seed-count')
            equal([sha(seed) for seed in seeds],search['seed_stream_sha256'],'seed-origin')
            equal(sha(anchor),search['anchor_stream_sha256'],'local-accepted-anchor')
            prefix = list(dict.fromkeys([anchor]+seeds))
            equal(blobs[:len(prefix)],prefix,'source-bound-pool-prefix')
            for pool_index, claimed in enumerate(search['report']['candidates']):
                if pool_index < len(prefix):
                    origin = 'control' if pool_index==0 else 'seed'
                else:
                    producing = [stage['operator'] for stage in search['report']['stages'] if pool_index in stage['outputs']]
                    if not producing:
                        raise AssertionError('New pool byte stream lacks a producing stage')
                    origin = producing[0]
                equal(origin,claimed['origin'],'pool-provenance')
            local_results[index] = (blobs, ranking)
        control = self.chain(row['chains'][0],record,target,job['speech'])
        if control['role'] != 'control':
            raise AssertionError('Rollback anchor is absent')
        chains = [control]+[self.chain(saved,record,target,job['speech'],control) for saved in row['chains'][1:]]
        for expected, actual in zip(('control','concat-selected','concat-raw'),chains):
            if actual is not None:
                equal(expected,actual['role'],'chain-role-order')
        for chain, label in zip(chains[1:], ('selected','raw')):
            if chain is None:
                if all(rank[label+'_id'] is not None for _, rank in local_results.values()):
                    raise AssertionError('Complete returned chain is unexpectedly absent')
                continue
            wanted = list(control['identity'])
            for index, (blobs, rank) in local_results.items():
                selected = rank[label+'_id']
                if selected is None:
                    raise AssertionError('Absent local result used in complete chain')
                wanted[index] = sha(blobs[selected])
            equal(wanted, chain['identity'], 'actual-returned-chain')
        legacy = self.chain(row['declared_level_legacy_comparison'],record,target,job['speech'],control)
        if job['speech']:
            equal(control['identity'],v1_rollback_identity,'whole-accepted-v1-rollback')
            equal(legacy['identity'],v1_legacy_identity,'whole-v1-legacy-comparison')
        else:
            equal(control['identity'],[sha(blob) for blob in originals],'nonspeech-rollback')
        decisions = [budget_choice(chains,record['baseline_bytes'],p) for p in (100,95,90)]
        equal(decisions,row['budgets'],'whole-decisions')
        if decisions[0]['selected'] is None:
            raise AssertionError('Full-cap rollback vanished')
        selected = {e['role']:e for e in chains if e is not None}
        projection = dict(phase=job['phase'], source_ordinal=job['source_ordinal'], profile=record['profile'],
            samples=record['samples'], reset_segments=len(record['segments']), mode=job['mode'],
            targeted_not_independent_heldout=row['targeted_not_independent_heldout'], gain=row['level']['gain'],
            edited_segments=job['edited_segments'], max_refinement_calls_per_segment=job['max_refinement_calls'],
            actual_refinement_calls=row['actual_refinement_calls'], measured_pool_rows=sum(len(s['pool']) for s in searches),
            original_complete_bytes=record['baseline_bytes'], rollback_bytes=control['stream_bytes'],
            rollback_source_periods=control['voice']['reference_period_frames'],
            rollback_within_tolerance_pcm=control['voice']['within_tolerance_frames'],
            rollback_within_tolerance_pwm=control['pwm_voice']['within_tolerance_frames'],
            decisions=[])
        for decision in decisions:
            chosen = None if decision['selected'] is None else selected[decision['selected']]
            projection['decisions'].append(dict(percent=decision['percent'],cap=decision['cap'],role=decision['selected'],
                raw_tradeoff=decision['raw_tradeoff'], no_fit=decision['no_fit'],
                bytes=None if chosen is None else chosen['stream_bytes'],
                changed_vs_rollback=None if chosen is None else chosen['identity'] != control['identity'],
                changed_vs_declared_legacy=None if chosen is None else chosen['identity'] != legacy['identity'],
                changed_vs_original=None if chosen is None else chosen['identity'] != [sha(b) for b in originals],
                score=None if chosen is None else chosen['score'], rollback_score=control['score'],
                pcm_sse=None if chosen is None else chosen['metrics']['pcm16']['error_energy'],
                rollback_pcm_sse=control['metrics']['pcm16']['error_energy'],
                pwm_sse=None if chosen is None else chosen['metrics']['pwm8']['error_energy'],
                rollback_pwm_sse=control['metrics']['pwm8']['error_energy'],
                pcm_stoi=None if chosen is None else chosen['metrics']['pcm16']['stoi'],
                pwm_stoi=None if chosen is None else chosen['metrics']['pwm8']['stoi'],
                within_tolerance_pcm=None if chosen is None else chosen['voice']['within_tolerance_frames'],
                within_tolerance_pwm=None if chosen is None else chosen['pwm_voice']['within_tolerance_frames'],
                source_periods=control['voice']['reference_period_frames']))
        self.rows.append(projection)
        self.counts['completed_records'] += 1
        return row

    def run(self, partial=False):
        self.context()
        b = self.binding
        speech_pairs, other_pairs = groups(b['speech_records']), groups(b['nonspeech_records'])
        if len(speech_pairs) != 49 or len(other_pairs) != 132:
            raise AssertionError('Original corpus scope changed')
        quiet = b['quiet_source_ordinals']
        equal(sorted(set(quiet+representatives(b['speech_records'],speech_pairs,quiet))), b['selected_default_speech_ordinals'],'default-speech-selection')
        equal(representatives(b['nonspeech_records'],other_pairs),b['selected_nonspeech_ordinals'],'default-nonspeech-selection')
        if [sum(j['phase']==p for j in b['jobs']) for p in PHASES] != [98,14,6]:
            raise AssertionError('Prepared phase counts differ')
        expected_jobs = []
        v1_jobs = {(j['record_index'],j['mode']):j for j in b['v1_binding']['jobs']}
        for ordinal,pair in enumerate(speech_pairs):
            mode = 'auto-quiet' if ordinal in quiet else 'preserve'
            for index in pair:
                for phase,limit in [('speech-screen',1)]+([('speech-default',4)] if ordinal in b['selected_default_speech_ordinals'] else []):
                    expected_jobs.append(dict(phase=phase,source_ordinal=ordinal,record_index=index,speech=True,
                        mode=mode,max_refinement_calls=limit,edited_segments=list(range(len(b['speech_records'][index]['segments']))),
                        v1_job=v1_jobs[(index,mode)]))
        for ordinal in b['selected_nonspeech_ordinals']:
            for index in other_pairs[ordinal]:
                expected_jobs.append(dict(phase='nonspeech-default',source_ordinal=ordinal,record_index=index,speech=False,
                    mode='preserve',max_refinement_calls=4))
        if len(expected_jobs) != len(b['jobs']):
            raise AssertionError('Prepared job inventory size changed')
        for expected,actual in zip(expected_jobs,b['jobs']):
            for name,value in expected.items():
                equal(value,actual[name],'predeclared-job-'+name)
        if len({(j['phase'],j['source_ordinal'],(b['speech_records'] if j['speech'] else b['nonspeech_records'])[j['record_index']]['profile']) for j in b['jobs']}) != len(b['jobs']):
            raise AssertionError('Duplicate source/profile/phase job')
        todo, missing = [], []
        for job in b['jobs']:
            records = b['speech_records'] if job['speech'] else b['nonspeech_records']
            profile = records[job['record_index']]['profile']
            folder = self.study/'records'/job['phase']/('source-%03d'%job['source_ordinal'])/('profile-%d'%profile)
            (todo if (folder/'complete-private.json').exists() else missing).append(job)
        if missing and not partial:
            raise AssertionError('Not all predeclared records are complete')
        if not partial:
            self.workers()
        with self.C.BatchSession('batch',prebuilt=self.study/'native/common.so') as self.common, self.C.BatchSession('batch',prebuilt=self.study/'native/v5-only.so') as self.only:
            for number, job in enumerate(todo,1):
                self.completed_record(job)
                print(json.dumps(dict(status='audited',completed=number,available=len(todo),phase=job['phase'],source_ordinal=job['source_ordinal'])),flush=True)
        self.context()
        phase_summaries = {}
        for phase in PHASES:
            cohort = [r for r in self.rows if r['phase']==phase]
            views = {}
            for mode in ('preserve','auto-quiet'):
                subset = [r for r in cohort if r['mode']==mode]
                if not subset:
                    continue
                views[mode] = dict(groups=len(subset),sources=len({r['source_ordinal'] for r in subset}),
                    targeted_groups=sum(r['targeted_not_independent_heldout'] for r in subset),
                    budgets={str(p):dict(admissions=sum(r['decisions'][i]['role'] is not None for r in subset),
                        changed_vs_rollback=sum(r['decisions'][i]['changed_vs_rollback'] is True for r in subset),
                        no_fit=sum(r['decisions'][i]['no_fit'] for r in subset)) for i,p in enumerate((100,95,90))})
            phase_summaries[phase] = dict(groups=len(cohort),views=views,
                actual_refinement_calls=sum(r['actual_refinement_calls'] for r in cohort),
                measured_pool_rows=sum(r['measured_pool_rows'] for r in cohort))
        result = dict(schema='lpx-adaptive-independent-audit-v1',status='partial' if missing else 'passed',
            completed_records=len(todo),expected_records=len(b['jobs']),missing_records=len(missing),
            counters=dict(self.counts),phases=phase_summaries,source_core_commit=b['core_commit'],
            scope='Independent saved-byte selection audit; primitive source features/metrics reused. No new fitting, refinement, perceptual or firmware admission.')
        save(self.output/'audit.json',result)
        save(self.output/'groups.json',self.rows)
        save(self.output/'audit-private.json',dict(binding_sha256=sha(self.binding_raw),auditor_sha256=sha(Path(__file__).read_bytes()),**result))
        return result

    def workers(self):
        b = self.binding
        expected_names = {phase+'-shard-%d-private.json'%shard for phase in PHASES for shard in (0,1)}
        actual_names = {path.name for path in (self.study/'workers').glob('*-private.json')}
        equal(actual_names,expected_names,'worker-file-inventory')
        for phase in PHASES:
            for shard in (0,1):
                worker = json.loads((self.study/'workers'/(phase+'-shard-%d-private.json'%shard)).read_text())
                expected = [j for j in b['jobs'] if j['phase']==phase and j['source_ordinal']%2==shard]
                if worker['status']!='complete' or worker['phase']!=phase or worker['shard']!=shard:
                    raise AssertionError('Prepared worker is not terminal complete')
                equal(worker['identity'],b['identity'],'worker-identity')
                equal(worker['binding_sha256'],sha(self.binding_raw),'worker-binding')
                equal(len(worker['records']),len(expected),'worker-record-count')
                equal(worker['executed_records']+worker['reused_records'],len(expected),'worker-cache-count')
                equal(worker['new_seed_fit_attempts'],0,'worker-no-new-fits')
                for job,row in zip(expected,worker['records']):
                    for name,value in job.items():
                        equal(value,row[name],'worker-record-job')
                    records = b['speech_records'] if job['speech'] else b['nonspeech_records']
                    profile = records[job['record_index']]['profile']
                    folder = self.study/'records'/phase/('source-%03d'%job['source_ordinal'])/('profile-%d'%profile)
                    equal(json.loads((folder/'record-private.json').read_text()),row,'worker-authoritative-record')
                equal(sum(r['actual_refinement_calls'] for r in worker['records']),worker['recorded_refinement_calls'],'worker-recorded-work')
                equal(sum(r['all_attempts_started_refinement_calls'] for r in worker['records']),worker['recorded_all_attempt_started_refinement_calls'],'worker-all-attempt-work')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',required=True,type=Path)
    parser.add_argument('--study',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--partial',action='store_true')
    args = parser.parse_args()
    root,study,output = [p.resolve() for p in (args.source_root,args.study,args.output)]
    if not output.is_relative_to((root/'build').resolve()) and not output.is_relative_to((Path.cwd()/'build').resolve()):
        parser.error('Audit output must stay in owned ignored build storage')
    if output.exists():
        parser.error('Use a fresh immutable audit output directory')
    output.mkdir(parents=True)
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS'):
        os.environ[name] = '1'
    started = time.perf_counter()
    try:
        result = Auditor(root,study,output).run(args.partial)
        result['audit_wall_seconds'] = time.perf_counter()-started
        save(output/'audit.json',result)
        print(json.dumps(dict(status=result['status'],completed_records=result['completed_records'],missing_records=result['missing_records'])),flush=True)
    except Exception as exc:
        save(output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Frozen joint-path/perceptual/swap study against completed expanded controls.

All media, references, paths and per-recording fingerprints are private build
artifacts. This runner changes no frozen predecessor source or decoder code.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tempfile
import time

REPOSITORY = Path(__file__).resolve().parents[5]
ACTIVE = REPOSITORY / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
sys.path.insert(0, str(ACTIVE / 'tools'))
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession, build_library
from benchmark_speech_flash import source_hashes
from measure_speech_firmware import checked_output
from refine_speech_compact import no_regression, quality
from refine_speech_trajectory import refine as path_refine
from select_speech_budget import quality_source_fingerprint
from speech_chain_frontier import assemble
import speech_compact as compact
from speech_objective import SpeechObjective
from speech_rate_allocation import improve_extras
from standard_metrics import pwm_duties

SETTINGS = dict(frame_limit=2, window_frames=2, beam_width=2,
                spectral_candidates=2, excitation_candidates=1,
                excitation_horizon=80, max_evaluations=128,
                allocation_evaluations=64, candidate_batch=32,
                screening='local', screening_horizon=640, rate_lambda=0.0,
                chain_beam_width=32, chain_max_evaluations=4096)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def save(path, value):
    path = checked_output(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.writing')
    for target in (path, temporary):
        checked_output(target)
        if target.is_symlink() or target.exists() and target.stat().st_nlink > 1:
            raise ValueError('Output aliases are not allowed')
    temporary.write_bytes(json.dumps(value, indent=2, allow_nan=False).encode() + b'\n')
    temporary.replace(path)


def write_stream(path, data):
    path = checked_output(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.exists() and path.stat().st_nlink > 1:
        raise ValueError('Stream output aliases are not allowed')
    path.write_bytes(data)


def sources():
    return dict(decoder=source_hashes(ACTIVE / 'src'),
                tools={p.name: sha(p.read_bytes()) for p in sorted((ACTIVE / 'tools').glob('*.py'))},
                runner=sha(Path(__file__).read_bytes()),
                protocol=sha((Path(__file__).resolve().parents[1] / 'PROTOCOL.md').read_bytes()),
                protocol_tests=sha(Path(__file__).with_name('test_protocol.py').read_bytes()))


def environment():
    compiler = shutil.which('g++')
    if compiler is None:
        raise ValueError('Native compiler is required')
    return dict(python=sys.version, platform=platform.platform(),
                packages={name: version(name) for name in ('numpy', 'numba', 'scipy', 'pystoi', 'soundfile')},
                native_compiler_sha256=sha(Path(compiler).read_bytes()),
                threads={name: os.environ.get(name) for name in
                         ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS')})


def prepare_native(output):
    folder = checked_output(Path(output) / 'native')
    folder.mkdir(parents=True, exist_ok=True)
    identity = sha(canonical([sources()['decoder'], environment()]))
    receipt = folder / 'binding.json'
    if receipt.is_file():
        old = json.loads(receipt.read_text())
        if old['identity'] != identity:
            raise ValueError('Use a fresh study output after changing native build inputs')
        if all(sha((folder / name).read_bytes()) == digest for name, digest in old['libraries'].items()):
            return old
        raise ValueError('Prepared native artifact changed; use a fresh output directory')
    libraries = {}
    for label, only in (('common', False), ('v5-only', True)):
        path = folder / (label + '.so')
        build_library(path, v3_features=124, speech=True, speech_compact=True, compact_only=only)
        libraries[path.name] = sha(path.read_bytes())
    result = dict(identity=identity, libraries=libraries, environment=environment())
    save(receipt, result)
    return result


def complete_cap(original_bytes, percent):
    if type(original_bytes) is not int or original_bytes < 22 or percent not in (100, 95, 90):
        raise ValueError('Expected original complete bytes and a declared percentage')
    return original_bytes * percent // 100


def reset_geometry(record):
    position = 0
    result = []
    for index, segment in enumerate(record['segments']):
        if (segment['index'] != index or segment['start'] != position
                or segment['profile'] != record['profile'] or segment['samples'] <= 0):
            raise ValueError('Original reset offsets/order/profile changed')
        result.append((segment['samples'], record['profile']))
        position += segment['samples']
    if position != record['samples']:
        raise ValueError('Original reset segments do not cover the complete recording')
    return result


def generation_caps(total_caps, frozen_pools, index):
    """Candidate-generation room with the cheapest fixed old-pool completion.

    These per-segment search limits never replace the final complete-chain
    caps. A clamped 22-byte limit remains merely a finite generation attempt.
    """
    other_minimum = sum(min(map(len, pool)) for i, pool in enumerate(frozen_pools) if i != index)
    result = {}
    for percent, total in total_caps.items():
        room = total - other_minimum
        cap = max(22, min(65535, room))
        result.setdefault(cap, []).append(dict(percent=percent, complete_cap=total,
                                              other_minimum_bytes=other_minimum, actual_room=room))
    return [(cap, result[cap]) for cap in sorted(result, reverse=True)]


def floor_flags(metrics, original, accepted_control=None, tradeoff_control=None):
    original_ok = bool(no_regression(metrics, original))
    accepted_ok = None if accepted_control is None else bool(no_regression(metrics, accepted_control))
    tradeoff_ok = None if tradeoff_control is None else bool(no_regression(metrics, tradeoff_control))
    return dict(original_floors_passed=original_ok, accepted_control_floors_passed=accepted_ok,
                tradeoff_control_floors_passed=tradeoff_ok,
                automatic_floors_passed=original_ok and accepted_ok is not False)


def capacity_callback(stop, emitted):
    statistics = dict(calls=0, evaluations=0, candidate_evaluations=0,
                      confirmation_evaluations=0, accepted_swaps=0)
    def callback(spectra, profile, extras, max_bytes, *, render, objective, start,
                 max_evaluations, rate_lambda, serialize):
        if rate_lambda != 0:
            raise ValueError('This frozen campaign uses lambda zero')
        result = improve_extras(spectra, profile, extras, max_bytes, render=render,
            objective=objective, serialize=serialize, stop=stop, start=start,
            max_evaluations=max_evaluations, candidate_batch=SETTINGS['candidate_batch'],
            admissible=None)
        statistics['calls'] += 1
        for name in ('evaluations', 'candidate_evaluations', 'confirmation_evaluations', 'accepted_swaps'):
            statistics[name] += getattr(result, name)
        if result.feasible:
            # Preserve a measured capacity result even if subsequent branch
            # reconstruction reaches the shared full-synthesis limit.
            emitted.append(bytes(result.stream))
        return result
    callback.statistics = statistics
    return callback


def load_inputs(manifest_path, expanded_paths):
    paths = [Path(manifest_path).resolve(), *map(lambda p: Path(p).resolve(), expanded_paths)]
    if len(paths) != 4:
        raise ValueError('Expected baseline plus tuning/evaluation/additional completed expanded runs')
    blobs = [p.read_bytes() for p in paths]
    manifest, *runs = map(json.loads, blobs)
    if manifest['schema'] != 'lpx-v5-encoder-quality-study-v1':
        raise ValueError('Expected immutable original baseline-v2 manifest')
    if any(r['status'] != 'complete' or r['manifest_sha256'] != sha(blobs[0])
           or r['source_sha256'] != manifest['source_sha256']
           or r['quality_source_fingerprint'] != manifest['quality_source_fingerprint'] for r in runs):
        raise ValueError('Completed expanded campaigns do not bind the original manifest')
    if any(r['encoder_source_sha256'] != runs[0]['encoder_source_sha256'] for r in runs):
        raise ValueError('Expanded controls used different encoder sources')
    controls = {r['id']: r for run in runs for r in run['records']}
    if len(controls) != 98 or len(manifest['records']) != 98 or set(controls) != {r['id'] for r in manifest['records']}:
        raise ValueError('Expected all 98 original/expanded profile groups')
    return manifest, controls, {str(p): sha(b) for p, b in zip(paths, blobs)}


def warmup(decoder, mode):
    blob = compact.pack(640, 6, [[3 + 6 * i for i in range(10)]] * 2,
        [(20, 60, 8)] * 4, [(i % 20, i % 16 - 8) for i in range(32)],
        pre=0, bright=0, extras=[(i % 40, 2) for i in range(16)])[0]
    ref = np.zeros(640, np.int16)
    objective = SpeechObjective.from_v5(ref, blob, mode=mode)
    emitted = []
    path_refine(ref, blob, decoder, len(blob) - 2, frame_limit=2, window_frames=2,
        beam_width=2, spectral_candidates=2, excitation_candidates=1, excitation_horizon=80,
        max_evaluations=128, allocation_evaluations=64, objective=objective,
        capacity_policy=capacity_callback(640, emitted), selection='objective')


def run(manifest_path, expanded_paths, output, *, mode, shard=0, shards=1, limit=0, split='all', label=None):
    output = checked_output(output)
    output.mkdir(parents=True, exist_ok=True)
    source = sources(); runtime = environment()
    if any(value != '1' for value in runtime['threads'].values()):
        raise ValueError('Run with explicit single-thread numeric-library settings')
    manifest, old, input_files = load_inputs(manifest_path, expanded_paths)
    for filename in input_files:
        source_path = Path(filename)
        if output == source_path.parent or output in source_path.parents or source_path in output.parents:
            raise ValueError('Study output must be separate from immutable inputs')
    assets = [record['reference']['path'] for record in manifest['records']]
    assets.extend(segment['path'] for record in manifest['records'] for segment in record['segments'])
    assets.extend(segment['path'] for control in old.values() for budget in control['budgets']
                  for role in ('selected', 'tradeoff') if budget[role] is not None
                  for segment in budget[role]['segments'])
    if any(Path(filename).resolve().is_relative_to(output) for filename in assets):
        raise ValueError('Immutable source media must be outside the new study output')
    if source['decoder'] != manifest['source_sha256'] or quality_source_fingerprint() != manifest['quality_source_fingerprint']:
        raise ValueError('Original decoder or metric sources changed')
    if mode not in ('sse', 'perceptual') or not 0 <= shard < shards or shards < 1:
        raise ValueError('Invalid objective/shard')
    native = json.loads((output / 'native/binding.json').read_text())
    if native['identity'] != sha(canonical([source['decoder'], runtime])):
        raise ValueError('Native libraries do not match the current source/runtime')
    for name, digest in native['libraries'].items():
        if sha((output / 'native' / name).read_bytes()) != digest:
            raise ValueError('Prepared native library changed')
    identity = sha(canonical([source, runtime, native, input_files, SETTINGS, mode]))
    records = [r for r in manifest['records'] if split == 'all' or r['split'] == split]
    if limit:
        records = records[:limit]
    records = [r for i, r in enumerate(records) if i % shards == shard]
    worker = label or f'{mode}-shard-{shard}'
    if not re.fullmatch(r'[a-z0-9-]{1,64}', worker):
        raise ValueError('Invalid worker label')
    tempfile.tempdir = str(output / 'tmp' / worker)
    Path(tempfile.tempdir).mkdir(parents=True, exist_ok=True)
    begun = time.perf_counter(); cpu_begun = time.process_time(); verified = set(); guards = dict(input_files)
    result = dict(schema='lpx-v5-combined-study-private-v1', status='running',
        source=source, runtime=runtime, native=native, input_files_sha256=input_files,
        identity=identity, settings=SETTINGS, mode=mode, split=split, shard=shard, shards=shards,
        expected_records=len(records), records=[], records_executed=0, records_reused=0)
    receipt = output / 'workers' / (worker + '.json')
    save(receipt, result)
    with BatchSession('batch', prebuilt=output / 'native/common.so') as common, \
         BatchSession('batch', prebuilt=output / 'native/v5-only.so') as decoder:
        t = time.perf_counter(); warmup(decoder, mode); result['warmup_wall_seconds'] = time.perf_counter() - t
        for ordinal, record in enumerate(records, 1):
            if not re.fullmatch(r'speech-profile-\d{3}', record['id']):
                raise ValueError('Invalid anonymous record identifier')
            started = time.perf_counter(); started_cpu = time.process_time()
            raw_reference = Path(record['reference']['path']).read_bytes()
            if sha(raw_reference) != record['reference']['file_sha256']:
                raise ValueError('Original reference changed')
            guards[record['reference']['path']] = sha(raw_reference)
            reference, rate = sf.read(record['reference']['path'], dtype='int16')
            if rate != 8000 or reference.ndim != 1 or len(reference) != record['samples'] or sha(reference.astype('<i2').tobytes()) != record['reference']['pcm16_sha256']:
                raise ValueError('Original reference PCM/geometry changed')
            pcm_cache = {}; chains = {}; geometry = reset_geometry(record)
            def decode(blob):
                key = sha(blob)
                if key not in pcm_cache:
                    pcm = compact.decode_model(blob); n = len(pcm)
                    if key not in verified:
                        pwm = pwm_duties(pcm)
                        for receiver in (common, decoder):
                            if not np.array_equal(receiver.decode_one_s16(blob, n), pcm) or not np.array_equal(receiver.decode_one(blob, n), pwm):
                                raise AssertionError('Complete common/v5/model PCM/PWM mismatch')
                        verified.add(key)
                    pcm.flags.writeable = False; pcm_cache[key] = pcm
                return pcm_cache[key]
            def candidate(blobs, expected=None, origin='new'):
                blobs = tuple(map(bytes, blobs)); key = tuple(sha(b) for b in blobs)
                if len(blobs) != len(geometry) or any(compact.unpack(b)[:2] != tuple(g) for b, g in zip(blobs, geometry)):
                    raise ValueError('Alternative changed actual reset geometry/profile')
                if key not in chains:
                    pcm = np.concatenate([decode(b) for b in blobs]); met = quality(reference, pcm)
                    chains[key] = dict(streams=blobs, pcm=pcm, metrics=met,
                                       stream_bytes=sum(map(len, blobs)), key=key, origin=origin)
                item = chains[key]
                if expected is not None and (item['metrics'] != expected['metrics'] or item['stream_bytes'] != expected['stream_bytes']):
                    raise ValueError('Frozen whole-chain metrics or byte count changed')
                return item
            def load_chain(item, origin):
                blobs = []
                for s in item['segments']:
                    data = Path(s['path']).read_bytes()
                    if sha(data) != s['stream_sha256'] or len(data) != s['file_bytes']:
                        raise ValueError('Frozen segment changed')
                    guards[s['path']] = sha(data); blobs.append(data)
                return candidate(blobs, item, origin)
            original = load_chain(dict(segments=record['segments'], metrics=record['baseline_metrics'],
                                       stream_bytes=record['baseline_bytes']), 'original')
            if sha(original['pcm'].astype('<i2').tobytes()) != record['baseline_pcm16_sha256'] or sha(pwm_duties(original['pcm']).tobytes()) != record['baseline_pwm_sha256']:
                raise ValueError('Frozen original whole PCM/PWM changed')
            controls = {}
            for b in old[record['id']]['budgets']:
                if b['cap'] != complete_cap(record['baseline_bytes'], b['percent']):
                    raise ValueError('Old run used another complete-chain budget')
                controls[b['percent']] = {name: None if b[name] is None else load_chain(b[name], f'old{b["percent"]}-{name}')
                                          for name in ('selected', 'tradeoff')}
            seed = controls[100]['selected']
            if seed is None or not no_regression(seed['metrics'], original['metrics']):
                raise ValueError('Expected accepted expanded100 seed')
            for pair in controls.values():
                if pair['selected'] is not None and not no_regression(pair['selected']['metrics'], original['metrics']):
                    raise ValueError('Old accepted control violates original floors')
            objective = SpeechObjective.from_chain(reference, seed['streams'], mode=mode)
            for item in chains.values():
                item['objective'] = objective(item['pcm'])
            folder = output / 'records' / mode / record['id']; folder.mkdir(parents=True, exist_ok=True)
            cached_path = folder / 'cache.json'
            if cached_path.is_file():
                cached = json.loads(cached_path.read_text())
                if cached['identity'] != identity or cached['record_sha256'] != sha(canonical(cached['record'])):
                    raise ValueError('Changed experiment/cache; use a fresh output directory')
                for filename, digest in cached['outputs'].items():
                    path = Path(filename).resolve()
                    if not path.is_relative_to(folder.resolve()) or sha(path.read_bytes()) != digest:
                        raise ValueError('Cached candidate artifact changed')
                item = cached['record']; result['records_reused'] += 1
            else:
                pools = [{original['streams'][i]} for i in range(len(geometry))]
                for old_chain in chains.values():
                    for i, blob in enumerate(old_chain['streams']): pools[i].add(blob)
                frozen_pools = [set(pool) for pool in pools]
                caps = {b['percent']: complete_cap(record['baseline_bytes'], b['percent']) for b in record['budgets']}
                if any(caps[b['percent']] != b['max_complete_stream_bytes'] for b in record['budgets']):
                    raise ValueError('Original hard complete-chain cap changed')
                searches = []; position = 0
                for index, blob in enumerate(seed['streams']):
                    n = geometry[index][0]; section = reference[position:position + n]
                    def context(pcm, start=position, stop=position + n):
                        joined = seed['pcm'].copy(); joined[start:stop] = pcm
                        return objective(joined)
                    for cap, cap_origins in generation_caps(caps, frozen_pools, index):
                        frontier = []; emitted = []; capacity = capacity_callback(n, emitted)
                        t = time.perf_counter(); c = time.process_time()
                        selected, _, report, raw = path_refine(section, blob, decoder, cap,
                            **{k: SETTINGS[k] for k in ('frame_limit','window_frames','beam_width','spectral_candidates',
                                'excitation_candidates','excitation_horizon','max_evaluations','allocation_evaluations',
                                'screening','screening_horizon','rate_lambda')},
                            objective=context, objective_name=objective.name, selection='objective',
                            capacity_policy=capacity, frontier=frontier)
                        proposals = [selected, raw, *(p['stream'] for p in frontier), *emitted]
                        for proposal in proposals:
                            if proposal is not None:
                                if len(proposal) > cap or compact.unpack(proposal)[:2] != geometry[index]:
                                    raise AssertionError('New segment cap or geometry mismatch')
                                decode(proposal); pools[index].add(bytes(proposal))
                        if report['full_synthesis_evaluations'] > 128 or report['allocation_evaluations'] != capacity.statistics['evaluations']:
                            raise AssertionError('Shared full-render accounting differs')
                        searches.append(dict(segment=index, generation_cap=cap, complete_budget_origins=cap_origins,
                                             report=report, capacity_statistics=capacity.statistics,
                                             emitted_feasible=len(set(emitted)), wall_seconds=time.perf_counter()-t,
                                             cpu_seconds=time.process_time()-c))
                    position += n
                budgets = []; outputs = {}
                for percent, cap in caps.items():
                    accepted = controls[percent]['selected']; tradeoff_control = controls[percent]['tradeoff']
                    anchor = accepted if accepted is not None else original
                    assembled = assemble(reference, anchor['streams'], pools, cap, objective=objective,
                                         beam_width=32, max_evaluations=4096)
                    candidates = [c for c in chains.values() if c['stream_bytes'] <= cap]
                    for value in (assembled.selected, assembled.tradeoff, *assembled.frontier):
                        if value is not None:
                            value = candidate(value.streams, origin='combined')
                            value['objective'] = objective(value['pcm']); candidates.append(value)
                    unique = {c['key']: c for c in candidates}
                    ranked = sorted(unique.values(), key=lambda c: (c['objective'], c['stream_bytes'], c['key']))
                    allowed = []
                    for value in ranked:
                        flags = floor_flags(value['metrics'], original['metrics'],
                            None if accepted is None else accepted['metrics'],
                            None if tradeoff_control is None else tradeoff_control['metrics'])
                        if flags['automatic_floors_passed']: allowed.append(value)
                    chosen = allowed[0] if allowed else None
                    raw = ranked[0] if ranked else None
                    if accepted is not None and chosen is None:
                        raise AssertionError('Accepted old rollback was lost')
                    entries = {}
                    for label2, value in (('selected', chosen), ('tradeoff', raw)):
                        if value is None: entries[label2] = None; continue
                        segments = []
                        for index, data in enumerate(value['streams']):
                            path = folder / f'{percent}-{label2}-{index}.l4hy'; write_stream(path, data)
                            outputs[str(path)] = sha(data)
                            segments.append(dict(path=str(path), stream_sha256=sha(data), file_bytes=len(data)))
                        entries[label2] = dict(segments=segments, stream_bytes=value['stream_bytes'], objective=value['objective'],
                            metrics=value['metrics'], **floor_flags(value['metrics'], original['metrics'],
                            None if accepted is None else accepted['metrics'], None if tradeoff_control is None else tradeoff_control['metrics']))
                    budgets.append(dict(percent=percent, cap=cap, assembly=assembled.report,
                        accepted_control_present=accepted is not None, tradeoff_control_present=tradeoff_control is not None,
                        accepted_control_metrics=None if accepted is None else accepted['metrics'],
                        accepted_control_bytes=None if accepted is None else accepted['stream_bytes'],
                        tradeoff_control_metrics=None if tradeoff_control is None else tradeoff_control['metrics'],
                        tradeoff_control_bytes=None if tradeoff_control is None else tradeoff_control['stream_bytes'], **entries))
                item = dict(id=record['id'], profile=record['profile'], split=record['split'], cohort=record['cohort'],
                    samples=len(reference), baseline_bytes=record['baseline_bytes'], baseline_metrics=record['baseline_metrics'],
                    expanded100_metrics=seed['metrics'], expanded100_bytes=seed['stream_bytes'], mode=mode,
                    objective=objective.describe(), reset_segment_samples=[g[0] for g in geometry],
                    old_pool_sizes=[len(p) for p in frozen_pools], combined_pool_sizes=[len(p) for p in pools],
                    searches=searches, budgets=budgets, all_common_v5_model_pcm_pwm_exact=True,
                    wall_seconds=time.perf_counter()-started, cpu_seconds=time.process_time()-started_cpu)
                save(cached_path, dict(identity=identity, record=item, record_sha256=sha(canonical(item)), outputs=outputs))
                result['records_executed'] += 1
            result['records'].append(item)
            if sources() != source or quality_source_fingerprint() != manifest['quality_source_fingerprint']:
                raise ValueError('Sources changed during the frozen study')
            save(receipt, result)
            print(json.dumps(dict(phase='combined-study', mode=mode, shard=shard,
                completed=ordinal, total=len(records), id=record['id'], seconds=time.perf_counter()-started)), flush=True)
        for filename, digest in guards.items():
            if sha(Path(filename).read_bytes()) != digest:
                raise ValueError('Frozen study input changed')
    result.update(status='complete', unique_streams_native_model_pwm_exact=len(verified),
                  wall_seconds=time.perf_counter()-begun, cpu_seconds=time.process_time()-cpu_begun)
    save(receipt, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare-native', action='store_true')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--expanded', type=Path, nargs='+')
    parser.add_argument('--mode', choices=('sse', 'perceptual'), default='sse')
    parser.add_argument('--split', choices=('all','tuning','evaluation','additional'), default='all')
    parser.add_argument('--shard', type=int, default=0); parser.add_argument('--shards', type=int, default=1)
    parser.add_argument('--limit', type=int, default=0); parser.add_argument('--label')
    args = parser.parse_args()
    if args.prepare_native:
        prepare_native(args.output)
        print('Native common/v5 libraries prepared and source-bound')
    else:
        if args.manifest is None or args.expanded is None:
            raise ValueError('Baseline and completed expanded controls are required')
        run(args.manifest, args.expanded, args.output, mode=args.mode, shard=args.shard,
            shards=args.shards, limit=args.limit, split=args.split, label=args.label)


if __name__ == '__main__':
    main()

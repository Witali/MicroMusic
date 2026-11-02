"""Reproduce the frozen 27-clip study without publishing private media or paths.

prepare CORPUS OUTPUT; work OUTPUT --compiler HOST_GXX --worker 0; export OUTPUT
Workers claim jobs atomically. Launch up to four independent worker processes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback

for variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    os.environ[variable] = '1'

ROOT = Path(__file__).resolve().parents[4]
ACTIVE = ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
sys.path.insert(0, str(ACTIVE/'tools'))
ORDER = (0, 8, 16, 19, 4, 12, 17, 18) + tuple(i for i in range(27) if i not in (0, 8, 16, 19, 4, 12, 17, 18))


def save(path, value):
    temporary = path.with_name(path.name+'.partial')
    temporary.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)


def snapshot():
    files = [ACTIVE/'tools'/name for name in ('encode_low_bitrate_speech.py', 'speech_sparse80.py',
        'speech_compact.py', 'q0_model.py', 'speech_voice_objective.py', 'speech_noise_objective.py',
        'voice_character.py', 'voice_input.py', 'speech_v4.py', 'wav_lpc.py')]
    files += sorted(p for p in (ACTIVE/'src').glob('*') if p.is_file())
    return {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


def output_path(path):
    path = path.resolve()
    path.relative_to((ROOT/'build').resolve())
    return path


def prepare(corpus, output):
    output = output_path(output)
    if output.exists():
        raise ValueError('A fresh ignored output directory is required')
    corpus = corpus.resolve()
    manifest = json.loads((corpus/'corpus.json').read_text(encoding='utf-8'))
    if len(manifest['cases']) != 27 or any(case['samples'] != 32000 for case in manifest['cases']):
        raise ValueError('Expected the established 27 complete four-second cases')
    output.mkdir(parents=True)
    (output/'claims').mkdir()
    source = snapshot()
    save(output/'binding-private.json', dict(corpus=str(corpus), cases=manifest['cases'],
        source=source, order=ORDER, kbps=[2, 3], pres=[13926, 11469, 8192],
        bandwidths=[.97, .94], level_policy='auto-quiet', source_frozen_before_corpus=True))
    archive = output/'frozen-active'
    for directory in ('tools', 'src'):
        destination = archive/directory
        destination.mkdir(parents=True)
        for path in (ACTIVE/directory).iterdir():
            if path.is_file() and (directory == 'src' or path.suffix == '.py'):
                shutil.copy2(path, destination/path.name)
    if source != snapshot():
        raise ValueError('The implementation changed while the frozen source was copied')
    save(output/'frozen-archive-private.json', dict(source=source, archive=str(archive.resolve()),
         verified_before_copy=True))


def work(output, compiler, worker):
    import numpy as np
    import soundfile as sf
    from batch_decoder import BatchDecoder, build_library
    import speech_compact as compact
    import speech_sparse80 as sparse
    from encode_low_bitrate_speech import encode
    from standard_metrics import pwm_duties

    output = output_path(output)
    binding = json.loads((output/'binding-private.json').read_text(encoding='utf-8'))
    if binding['source'] != snapshot():
        raise ValueError('The frozen implementation changed')
    worker_dir = output/'workers'/('worker-%03d' % worker)
    worker_dir.mkdir(parents=True, exist_ok=False)
    libraries = []
    for compact_only in (False, True):
        library = worker_dir/('only.so' if compact_only else 'common.so')
        build_library(library, compiler, speech=True, speech_compact=True, compact_only=compact_only)
        libraries.append(BatchDecoder(library))
    common, only = libraries
    for ordinal in binding['order']:
        case = binding['cases'][ordinal]
        for kbps in binding['kbps']:
            claim = output/'claims'/('case-%03d-rate-%d' % (ordinal, kbps))
            try:
                claim.mkdir()
            except FileExistsError:
                continue
            save(claim/'owner-private.json', dict(worker=worker, status='RUNNING'))
            case_dir = output/('case-%03d' % ordinal)
            destination = case_dir/('rate-%d' % kbps)
            started = time.perf_counter()
            try:
                reference, rate = sf.read(Path(binding['corpus'])/case['id']/'reference.wav', dtype='int16')
                digest = hashlib.sha256(reference.astype('<i2').tobytes()).hexdigest()
                if rate != 8000 or reference.shape != (32000,) or digest != case['reference_sha256']:
                    raise ValueError('The full original reference changed')
                blob, pcm, report = encode(reference, kbps, common, output=destination,
                    level_policy=binding['level_policy'], speech=case['kind'] == 'speech',
                    pres=tuple(binding['pres']), bandwidths=tuple(binding['bandwidths']))
                control = (destination/'candidate-000.lpx').read_bytes()
                for candidate in (control, blob):
                    expanded = sparse.expand(candidate) if kbps == 2 else candidate
                    expected = sparse.decode_model(candidate) if kbps == 2 else compact.decode_model(candidate)
                    if (not np.array_equal(only.decode_one_s16(expanded, len(reference)), expected)
                            or not np.array_equal(only.decode_one(expanded, len(reference)), pwm_duties(expected))):
                        raise AssertionError('The v5-only native reference differs')
                if binding['source'] != snapshot():
                    raise ValueError('The frozen implementation changed during search')
                row = dict(ordinal=ordinal, kbps=kbps, status='PASS', kind=case['kind'], group=case['group'],
                    bytes=len(blob), samples=len(reference), selected=report['candidates'][report['selected_id']],
                    baseline=report['candidates'][0], candidate_count=report['candidate_count'],
                    seconds=report['seconds'], level=report['level'],
                    common_and_v5_only_native_exact=True, source_frozen=True)
            except Exception as error:
                destination.parent.mkdir(parents=True, exist_ok=True)
                (claim/'exception-private.log').write_text(traceback.format_exc(), encoding='utf-8')
                row = dict(ordinal=ordinal, kbps=kbps, status='FAIL', exception=type(error).__name__,
                           seconds=time.perf_counter()-started)
            save(case_dir/('rate-%d-complete-private.json' % kbps), row)
            save(claim/'owner-private.json', dict(worker=worker, status=row['status']))
            print(json.dumps({key: row[key] for key in ('ordinal', 'kbps', 'status', 'seconds')}), flush=True)


def export(output):
    output = output_path(output)
    rows = []
    for ordinal in range(27):
        for kbps in (2, 3):
            receipt = output/('case-%03d' % ordinal)/('rate-%d-complete-private.json' % kbps)
            if not receipt.exists():
                raise ValueError('All 54 jobs must finish before final export')
            record = json.loads(receipt.read_text(encoding='utf-8'))
            if record['status'] not in ('PASS', 'FAIL'):
                raise ValueError('A claimed or running job is not complete')
            row = {key: record[key] for key in ('ordinal', 'kbps', 'status', 'seconds')}
            if record['status'] == 'PASS':
                row.update({key: record[key] for key in ('bytes', 'samples',
                    'candidate_count', 'common_and_v5_only_native_exact')})
                row['kind'] = record['kind'] if record['kind'] in ('speech', 'music') else 'unknown'
                row['group'] = record['group'] if record['group'] in ('clean', 'quiet', 'noise15', 'acoustic_music', 'synthetic') else 'unknown'
                for role in ('baseline', 'selected'):
                    source = record[role]
                    row[role] = dict(file_bytes=source['file_bytes'], score=source['score'],
                        pcm_metrics=source['metrics']['pcm16'], pwm_metrics=source['metrics']['pwm8'],
                        source_period_tolerance_frames=source['voice']['within_tolerance_frames'],
                        pwm_source_period_tolerance_frames=source['pwm_voice']['within_tolerance_frames'],
                        clipped_samples=source['clipped_samples'],
                        parameter_trials=source['parameter_trials'])
            rows.append(row)
    result = dict(schema='lpx-low-bitrate-speech-corpus-v1', expected_jobs=54,
        completed_jobs=len(rows), passed_jobs=sum(row['status'] == 'PASS' for row in rows), rows=rows,
        work_counter_scope='Per unique retained candidate; duplicate-output search calls are not included',
        scope='Frozen 27-clip finite search; simulated native arithmetic, not a listening score')
    save(output/'numeric-export.json', result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('prepare')
    create.add_argument('corpus', type=Path)
    create.add_argument('output', type=Path)
    run = commands.add_parser('work')
    run.add_argument('output', type=Path)
    run.add_argument('--compiler', default='g++')
    run.add_argument('--worker', type=int, required=True)
    gather = commands.add_parser('export')
    gather.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.corpus, args.output)
    elif args.command == 'work':
        work(args.output, args.compiler, args.worker)
    else:
        export(args.output)


if __name__ == '__main__':
    main()

"""Time a complete bounded search with identical old/new proposals.

Inputs are supplied locally as a hash-pinned manifest. No encoded-output
cache is used. WAV I/O, native compilation and JIT warmup are outside the
paired warm timing; this is not the duration of the entire WAV encoder CLI.
"""
import argparse
import json
import os
import platform
import statistics
import time
from pathlib import Path

import numba
import numpy as np
import soundfile as sf

from batch_decoder import BatchSession
from benchmark_encoder_speed import baseline, sha
from budget_search import search_budget
import joint_rate
from output_paths import protect_outputs
from standard_metrics import pwm_duties


def run(baseline_source, baseline_sha256, inputs, output, repeats=2):
    if not 2 <= repeats <= 9:
        raise ValueError('Use 2..9 paired repeats')
    case = json.loads(Path(inputs).read_text(encoding='utf-8'))
    paths = [Path(case['reference']), *[Path(s['path']) for s in case['seeds']]]
    if not case['seeds']:
        raise ValueError('At least one seed is required')
    protect_outputs([baseline_source, inputs, *paths], [output])
    ref, rate = sf.read(paths[0], dtype='int16')
    if rate != 8000 or ref.ndim != 1 or not 1 <= len(ref) <= 64000:
        raise ValueError('Expected complete mono PCM16/8kHz reference')
    if sha(ref.astype('<i2').tobytes()) != case['reference_sha256']:
        raise ValueError('Reference hash changed')
    seeds = [p.read_bytes() for p in paths[1:]]
    if any(sha(b) != s['sha256'] for b, s in zip(seeds, case['seeds'])):
        raise ValueError('Seed hash changed')
    old = baseline(baseline_source, baseline_sha256)
    times = {'before': [], 'after': []}
    warmup = {}
    expected = None
    with BatchSession('batch', v3_features=24) as decoder:
        for name, module in (('before', old), ('after', joint_rate)):
            started = time.perf_counter()
            module.encode_joint(seeds[0], ref, decoder, lam=case['lambdas'][0],
                                beam=case['beam'], kind=case['kind'])
            warmup[name] = time.perf_counter() - started
        for repeat in range(repeats):
            pair = [('before', old), ('after', joint_rate)]
            if repeat % 2:
                pair.reverse()
            for name, module in pair:
                started = time.perf_counter()
                blob, pcm, report = search_budget(
                    seeds, ref, decoder, case['cap_complete_file_bytes'], case['kind'],
                    lambdas=case['lambdas'], refinement_trials=case['refinement_trials_per_seed'],
                    encoder=module.encode_joint, encoder_options={'beam': case['beam']})
                elapsed = time.perf_counter() - started
                if blob is None:
                    raise ValueError('Search found no feasible result')
                rows = [(r['stream_sha256'], r['file_bytes'], r['full_sse'], r['quality']['stoi'])
                        for r in report['candidates']]
                signature = (sha(blob), sha(pcm.astype('<i2').tobytes()),
                             sha(pwm_duties(pcm).tobytes()),
                             sha(json.dumps(rows, separators=(',', ':')).encode()), report['trials'])
                if expected is None:
                    expected = signature
                if signature != expected:
                    raise AssertionError('Search proposals, selection or full PCM/PWM changed')
                times[name].append(elapsed)
                print(name, repeat, round(elapsed, 3), 'seconds;', report['trials'], 'trials', flush=True)
    result = {
        'schema': 1,
        'scope': 'Complete bounded search; WAV I/O, native compilation and JIT warmup excluded.',
        'protocol': 'Alternating paired repeats, one process, no encoded-output caches.',
        'case': case['id'], 'samples': len(ref), 'reference_sha256': case['reference_sha256'],
        'seed_sha256': [sha(b) for b in seeds],
        **{key: case[key] for key in ('cap_complete_file_bytes', 'kind', 'lambdas',
                                     'refinement_trials_per_seed', 'beam')},
        'seconds': times, 'warmup_seconds': warmup,
        'selected_stream_sha256': expected[0], 'selected_pcm16_sha256': expected[1],
        'selected_pwm_sha256': expected[2], 'proposal_signature_sha256': expected[3],
        'encoder_trials': expected[4], 'baseline_source_sha256': baseline_sha256,
        'baseline_model_sha256': sha(Path(baseline_source).with_name('q0_model_reference.py').read_bytes()),
        'current_joint_sha256': sha(Path(joint_rate.__file__).read_bytes()),
        'current_model_sha256': sha(Path(__file__).with_name('q0_model.py').read_bytes()),
        'search_source_sha256': sha(Path(__file__).with_name('budget_search.py').read_bytes()),
        'python': platform.python_version(), 'numpy': np.__version__, 'numba': numba.__version__,
        'threads': {k: os.environ.get(k) for k in
                    ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMBA_NUM_THREADS')},
        'time_reduction_percent': 100 * (1 - statistics.median(times['after']) /
                                         statistics.median(times['before']))}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline_source', type=Path)
    parser.add_argument('baseline_sha256')
    parser.add_argument('inputs', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--repeats', type=int, default=2)
    args = parser.parse_args()
    run(args.baseline_source, args.baseline_sha256, args.inputs, args.output, args.repeats)

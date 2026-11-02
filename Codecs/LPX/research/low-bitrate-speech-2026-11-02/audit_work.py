"""Reconstruct the frozen proposal schedule, without any pulse fitting.

Checks every recorded unique-output counter and counts omitted duplicate calls.
Reconstructed operation counts and measured search wall time remain separate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

for variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    os.environ[variable] = '1'

import numpy as np
from numba import njit

ROOT = Path(__file__).resolve().parents[4]


@njit(cache=True)
def proposal_count(reference, co, source_lags, pre, sparse80, expanded, clip_guard):
    """Independent count of the frozen open-loop scale/lag/gain proposals.

    This repeats only source analysis and finite proposal bookkeeping. It never
    renders a pulse or invokes a fitting function. Integer closed-loop state
    cannot affect this frozen encoder's parameter proposal count.
    """
    n = len(reference)
    block, group = (320, 80) if sparse80 else (160, 20)
    emphasized, residual = np.zeros(n, np.float64), np.zeros(n, np.float64)
    for at in range(n):
        emphasized[at] = reference[at]/2 - (pre*(reference[at-1]/2) if at else 0)/16384
        residual[at] = emphasized[at]
        for k in range(10):
            if at > k:
                residual[at] += co[at, k]*emphasized[at-k-1]/4096
    total = 0
    for bi in range(n//block):
        start, stop = bi*block, (bi+1)*block
        desired = max(1., np.sqrt(np.mean(residual[start:stop]**2)*group)/7.5)
        center = max(1, min(31, int(np.rint((128+16*np.log2(desired/16.384))/8))))
        low, high = max(0, center-2), min(31, center+2)
        scale_count = high-low+1+int(not low <= 0 <= high)+int(not low <= 1 <= high)
        scores = np.zeros(128, np.float64)
        for candidate in range(18, 146):
            dot = energy = 0.
            for at in range(start, stop):
                value = residual[at-candidate] if at >= candidate else 0.
                dot += value*residual[at]
                energy += value*value
            scores[candidate-18] = max(0., dot)**2/(energy+1.)
        lags = np.full(7, np.argmax(scores)+18, np.int64)
        count = 1
        if expanded:
            for value in (source_lags[bi], source_lags[bi]-1, source_lags[bi]+1):
                if 18 <= value <= 145 and not np.any(lags[:count] == value):
                    lags[count] = value
                    count += 1
            for _ in range(2):
                for index in range(128):
                    if np.any(np.abs(lags[:count]-(index+18)) <= 2):
                        scores[index] = -1
                value = np.argmax(scores)+18
                if not np.any(lags[:count] == value):
                    lags[count] = value
                    count += 1
        gains = 8 if clip_guard else 4
        total += scale_count*(1+count*(gains-1))
    return total


def signature(settings):
    return tuple(settings[key] for key in ('pre_q14', 'bandwidth', 'allocation',
                                           'expanded_lags', 'clip_guard'))


def run(corpus_output, output):
    import soundfile as sf
    corpus_output = corpus_output.resolve()
    corpus_output.relative_to((ROOT/'build').resolve())
    output = output.resolve()
    output.relative_to((ROOT/'build').resolve())
    if output.exists():
        raise ValueError('Use a fresh ignored audit output directory')
    binding = json.loads((corpus_output/'binding-private.json').read_text(encoding='utf-8'))
    frozen = corpus_output/'frozen-active'
    expected = json.loads((corpus_output/'frozen-archive-private.json').read_text(encoding='utf-8'))['source']
    for original, digest in expected.items():
        archived = frozen/('src' if Path(original).parent.name == 'src' else 'tools')/Path(original).name
        if hashlib.sha256(archived.read_bytes()).hexdigest() != digest:
            raise ValueError('A frozen archived dependency changed')
    sys.path.insert(0, str(frozen/'tools'))
    import speech_v4
    from encode_low_bitrate_speech import spectral_plans
    from q0_model import coefficient_trace
    from voice_character import track_pitch
    from voice_input import prepare_level
    from wav_lpc import analyze, pack_frames
    if Path(sys.modules['encode_low_bitrate_speech'].__file__).resolve().parent != (frozen/'tools').resolve():
        raise ValueError('An imported search module belongs to a different checkout')
    records = []
    for ordinal in range(27):
        for kbps in (2, 3):
            receipt = corpus_output/('case-%03d' % ordinal)/('rate-%d-complete-private.json' % kbps)
            record = json.loads(receipt.read_text(encoding='utf-8'))
            if record['status'] != 'PASS':
                raise ValueError('All original corpus jobs must finish successfully before auditing work')
            records.append(record)
    output.mkdir(parents=True)
    results = []
    for record in records:
        started = time.perf_counter()
        ordinal, kbps = record['ordinal'], record['kbps']
        report_path = corpus_output/('case-%03d' % ordinal)/('rate-%d' % kbps)/'report-private.json'
        report = json.loads(report_path.read_text(encoding='utf-8'))
        case = binding['cases'][ordinal]
        reference, rate = sf.read(Path(binding['corpus'])/case['id']/'reference.wav', dtype='int16')
        if rate != 8000 or hashlib.sha256(reference.astype('<i2').tobytes()).hexdigest() != case['reference_sha256']:
            raise ValueError('The complete reference changed')
        target, level = prepare_level(reference, binding['level_policy'])
        if level != record['level']:
            raise AssertionError('The declared source-level plan differs')
        padded = np.pad(target.astype(np.int64), (0, (-len(target))%320))
        sparse80, block = kbps == 2, 320 if kbps == 2 else 160
        track = track_pitch(target)
        lags = np.zeros(len(padded)//block, np.int64)
        for bi in range(len(lags)):
            center = bi*block+block/2
            if len(track.period):
                index = int(np.argmin(abs(track.sample_center-center)))
                if np.isfinite(track.period[index]):
                    lags[bi] = int(np.rint(track.period[index]))
        measured = {signature(row['settings']): row for row in report['candidates']}
        visited, calls = set(), []
        for pre in binding['pres']:
            for bandwidth in binding['bandwidths']:
                vectors, _ = analyze(padded, pre=pre, bandwidth=bandwidth)
                desired = speech_v4.quantize_spectrum(vectors, 6 if sparse80 else 4)
                plans = spectral_plans(padded, desired, report['complete_byte_cap'], sparse80)
                for allocation, spectra in plans:
                    shift = 4 if sparse80 else 5
                    expanded_vectors = [[(int(v)<<shift)+(1<<(shift-1)) for v in vector]
                                        for vector in spectra for _ in range(2)]
                    co = coefficient_trace(pack_frames(expanded_vectors), len(padded))
                    choices = ((False, False), (True, True)) if not calls else ((True, True),)
                    for expanded_lags, clip_guard in choices:
                        settings = dict(pre_q14=pre, bandwidth=bandwidth, allocation=allocation,
                                        expanded_lags=expanded_lags, clip_guard=clip_guard)
                        fits = int(proposal_count(padded, co, lags, pre, sparse80, expanded_lags, clip_guard))
                        total_fits = fits+len(padded)//block
                        counters = dict(parameter_trials=fits, selected_block_replays=len(padded)//block,
                            pulse_position_sign_trials=total_fits*(512 if sparse80 else 256),
                            committed_group_replays=total_fits*(4 if sparse80 else 8))
                        key = signature(settings)
                        if key in measured:
                            for name, value in counters.items():
                                if measured[key][name] != value:
                                    raise AssertionError('Recorded and reconstructed unique-row work differs')
                            visited.add(key)
                        calls.append(dict(settings=settings, recorded_unique_output=key in measured, **counters))
        if visited != set(measured):
            raise AssertionError('A recorded unique contender was not reconstructed')
        totals = {key: sum(call[key] for call in calls) for key in (
            'parameter_trials', 'selected_block_replays', 'pulse_position_sign_trials', 'committed_group_replays')}
        result = dict(ordinal=ordinal, kbps=kbps, calls=len(calls), unique_outputs=report['candidate_count'],
            duplicate_output_calls=len(calls)-report['candidate_count'], reconstructed_work_totals=totals,
            every_recorded_unique_counter_checked=True, measured_encoding_wall_seconds=report['seconds'],
            accounting_audit_seconds=time.perf_counter()-started, pulse_fits_reexecuted=0)
        results.append(result)
        (output/('case-%03d-rate-%d-private.json' % (ordinal, kbps))).write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(dict(ordinal=ordinal, kbps=kbps, duplicate_calls=result['duplicate_output_calls'])), flush=True)
    summary = dict(schema='lpx-frozen-work-accounting-audit-v1', completed_jobs=len(results), rows=results,
        total_reconstructed_parameter_trials=sum(row['reconstructed_work_totals']['parameter_trials'] for row in results),
        pulse_fits_reexecuted=0, scope='Exact deterministic proposal counts; not a new encoder-speed measurement')
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus_output', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    run(args.corpus_output, args.output)


if __name__ == '__main__':
    main()

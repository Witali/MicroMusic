"""Bounded host-only non-speech trajectory robustness with complete references.

A manifest supplies original v5 reset segments and PCM16 references. Segment
selection depends only on frozen baseline SSE/sample and the final segment.
Search never concatenates a long recording inside its objective callback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import soundfile as sf

from batch_decoder import BatchSession
from benchmark_speech_flash import source_hashes
from output_paths import protect_outputs
from refine_speech_trajectory import refine
import speech_compact as compact
from standard_metrics import error_metrics, pwm_duties, pwm_pcm16

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[2]
SETTINGS = dict(frame_limit=2, window_frames=2, beam_width=2, spectral_candidates=2,
                excitation_candidates=1, excitation_horizon=80, max_evaluations=64,
                screening='local', screening_horizon=640, capacity_policy='amplitude',
                rate_lambda=0.0, selection='conservative', speech=False)
CHUNK = 65536


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def exact_sse(reference, pcm):
    """PCM16 SSE with bounded int64 block sums and an unbounded integer total."""
    x, y = np.asarray(reference), np.asarray(pcm)
    if x.ndim != 1 or x.shape != y.shape or x.dtype.kind not in 'iu' or y.dtype.kind not in 'iu':
        raise ValueError('Equal mono integer arrays required')
    if any(np.any(a < -32768) or np.any(a > 32767) for a in (x, y)):
        raise ValueError('PCM16 values required')
    total = 0
    for at in range(0, len(x), CHUNK):
        delta = y[at:at+CHUNK].astype(np.int64)-x[at:at+CHUNK].astype(np.int64)
        total += int(np.dot(delta, delta))
    return total


class SubstitutionObjective:
    """Exact additive whole SSE, centered to avoid a huge float constant.

    whole_SSE(candidate) = frozen_whole_SSE + returned_delta(candidate).
    A segment is at most 64k, so the integer delta is exactly representable in
    the refiner's float score even when the full recording's SSE is larger.
    """
    def __init__(self, reference_segment, baseline_segment, baseline_whole_sse):
        self.reference = np.asarray(reference_segment)
        self.segment_sse = exact_sse(self.reference, baseline_segment)
        self.whole_sse = int(baseline_whole_sse)
        if self.whole_sse < self.segment_sse:
            raise ValueError('Whole error cannot be smaller than its segment error')

    def __call__(self, candidate):
        return exact_sse(self.reference, candidate)-self.segment_sse

    def whole_error(self, candidate):
        return self.whole_sse+self(candidate)


def select_segments(errors, lengths):
    """Largest exact baseline SSE/sample (earliest tie), then final if distinct."""
    if not errors or len(errors) != len(lengths) or any(n <= 0 for n in lengths):
        raise ValueError('Nonempty positive segment geometry required')
    best = 0
    for i in range(1, len(errors)):
        if errors[i]*lengths[best] > errors[best]*lengths[i]:
            best = i
    return [best] if best == len(errors)-1 else [best, len(errors)-1]


def descriptors(pcm):
    x = np.asarray(pcm)
    if x.ndim != 1 or not len(x):
        raise ValueError('Nonempty mono data required')
    energy = exact_sse(np.zeros(len(x), np.int16), x)
    duties = pwm_duties(x)
    return dict(samples=len(x), rms_pcm16=float(np.sqrt(energy/len(x))),
                peak_abs_pcm16=int(np.max(np.abs(x.astype(np.int64)))),
                full_scale_sample_fraction=float(np.mean((x == -32768) | (x == 32767))),
                nonzero_fraction=float(np.mean(x != 0)),
                activity_abs_ge_256_fraction=float(np.mean(np.abs(x.astype(np.int64)) >= 256)),
                pwm_endpoint_fraction=float(np.mean((duties == 0) | (duties == 255))))


def numerical_metrics(reference, pcm):
    pwm = pwm_pcm16(pcm)
    result = {'pcm16': error_metrics(reference, pcm, speech=False),
              'pwm8': error_metrics(reference, pwm, speech=False)}
    for domain, actual in (('pcm16', pcm), ('pwm8', pwm)):
        result[domain].pop('stoi', None)
        result[domain]['exact_error_energy'] = exact_sse(reference, actual)
    return result


def numerical_floors(candidate, baseline):
    return all(candidate[domain]['exact_error_energy'] <= baseline[domain]['exact_error_energy']
               for domain in ('pcm16', 'pwm8'))


def decode_chain(blobs, common, narrow):
    """Fresh independent model and both native PCM/PWM paths for every segment."""
    parts = []
    for blob in blobs:
        pcm = compact.decode_model(blob)
        n = len(pcm)
        expected_pwm = pwm_duties(pcm)
        for decoder in (common, narrow):
            actual = decoder.decode_one_s16(blob, n)
            if actual is None or not np.array_equal(actual, pcm) or not np.array_equal(decoder.decode_one(blob, n), expected_pwm):
                raise AssertionError('Complete native common/v5/model PCM/PWM mismatch')
        parts.append(pcm)
    return parts, np.concatenate(parts)


def smoke_indices(records):
    """Geometry-only smoke: shortest and longest source cases, both profiles."""
    if not records:
        raise ValueError('Empty manifest')
    minimum = min(range(len(records)), key=lambda i: (records[i]['samples'], i))
    maximum = max(range(len(records)), key=lambda i: (records[i]['samples'], -i))
    cases = {records[i]['private_case_id'] for i in (minimum, maximum)}
    return [i for i, record in enumerate(records) if record['private_case_id'] in cases]


def source_inventory():
    names = ('benchmark_nonspeech_trajectory.py', 'refine_speech_trajectory.py',
             'refine_speech_lpc.py', 'refine_speech_compact.py', 'enhance_speech_compact.py',
             'speech_rate_allocation.py', 'speech_compact.py', 'standard_metrics.py',
             'q0_model.py', 'wav_lpc.py', 'batch_decoder.py')
    return dict(core=source_hashes(ROOT/'src'),
                encoder={name: sha((ROOT/'tools'/name).read_bytes()) for name in names})


def guard_outputs(inputs, outputs):
    build = (REPOSITORY/'build').resolve()
    for path in outputs:
        path = Path(path)
        if (not path.resolve().is_relative_to(build) or path.is_symlink() or
                path.exists() and path.stat().st_nlink > 1):
            raise ValueError('Private output alias or escape')
    protect_outputs(inputs, outputs)


def save(path, value):
    tmp = path.with_suffix('.writing')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    tmp.replace(path)


def run_group(record, ordinal, output, common, narrow, settings=None):
    settings = dict(SETTINGS if settings is None else settings)
    begun, cpu = time.perf_counter(), time.process_time()
    reference_path = Path(record['reference']['path'])
    if sha(reference_path.read_bytes()) != record['reference']['file_sha256']:
        raise ValueError('Frozen reference file changed')
    reference, rate = sf.read(reference_path, dtype='int16')
    if rate != 8000 or reference.ndim != 1 or len(reference) != record['samples']:
        raise ValueError('Original reference geometry mismatch')
    if sha(reference.astype('<i2').tobytes()) != record['reference']['pcm16_sha256']:
        raise ValueError('Reference PCM changed; no resampling/normalization is permitted')
    blobs, lengths, offset = [], [], 0
    for i, segment in enumerate(record['segments']):
        blob = Path(segment['path']).read_bytes()
        if sha(blob) != segment['stream_sha256'] or len(blob) != segment['file_bytes']:
            raise ValueError('Frozen segment changed')
        fields = compact.unpack(blob)
        if segment['index'] != i or segment['start'] != offset or fields[0] != segment['samples'] or fields[1] != record['profile']:
            raise ValueError('Ordered reset geometry changed')
        blobs.append(blob); lengths.append(fields[0]); offset += fields[0]
    if offset != len(reference) or sum(map(len, blobs)) != record['baseline_bytes']:
        raise ValueError('Full original chain/byte cap mismatch')
    baseline_parts, baseline_pcm = decode_chain(blobs, common, narrow)
    if (sha(baseline_pcm.astype('<i2').tobytes()) != record['baseline_pcm16_sha256'] or
            sha(pwm_duties(baseline_pcm).tobytes()) != record['baseline_pwm_sha256']):
        raise AssertionError('Baseline differs from frozen full recording')
    baseline = numerical_metrics(reference, baseline_pcm)
    offsets = np.cumsum([0, *lengths]).tolist()
    errors = [exact_sse(reference[offsets[i]:offsets[i+1]], pcm) for i, pcm in enumerate(baseline_parts)]
    if sum(errors) != baseline['pcm16']['exact_error_energy']:
        raise AssertionError('Exact additive baseline SSE failed')
    chosen_indices = select_segments(errors, lengths)
    selected, raw = list(blobs), list(blobs)
    output.mkdir(parents=True, exist_ok=True)
    searches = []
    for index in chosen_indices:
        ref = reference[offsets[index]:offsets[index+1]]
        objective = SubstitutionObjective(ref, baseline_parts[index], baseline['pcm16']['exact_error_energy'])
        candidate, pcm, report, alternative = refine(ref, blobs[index], narrow, len(blobs[index]),
            objective=objective, objective_name='exact_centered_whole_record_pcm_sse', **settings)
        if candidate is None or alternative is None:
            raise AssertionError('Original seed fits its cap and must remain eligible')
        if len(candidate) > len(blobs[index]) or len(alternative) > len(blobs[index]):
            raise AssertionError('Actual edited-segment byte cap failed')
        selected[index], raw[index] = candidate, alternative
        (output/f'selected-{index:03d}.l4hy').write_bytes(candidate)
        (output/f'raw-{index:03d}.l4hy').write_bytes(alternative)
        searches.append(dict(segment=index, original_samples=lengths[index], original_bytes=len(blobs[index]),
            exact_original_segment_sse=errors[index], objective_constant_removed=baseline['pcm16']['exact_error_energy'],
            selected_full_record_sse_if_only_this_edit=objective.whole_error(pcm),
            report=report))
    for i in set(range(len(blobs)))-set(chosen_indices):
        if selected[i] != blobs[i] or raw[i] != blobs[i]:
            raise AssertionError('Untouched segment changed')
    # Final outputs are decoded afresh, not inferred from candidate snapshots or
    # local deltas; exact duplicate role chains share this fresh independent audit.
    final_cache = {}
    outputs = {}
    for role, stream_list in (('baseline', blobs), ('selected', selected), ('raw', raw)):
        key = tuple(stream_list)
        if key not in final_cache:
            parts, pcm = decode_chain(key, common, narrow)
            if len(pcm) != len(reference):raise AssertionError('Full original length lost')
            final_cache[key] = (parts, pcm, numerical_metrics(reference, pcm), descriptors(pcm))
        parts, pcm, metrics, stats = final_cache[key]
        additive = baseline['pcm16']['exact_error_energy']
        for i in chosen_indices:
            additive += exact_sse(reference[offsets[i]:offsets[i+1]], parts[i])-errors[i]
        if additive != metrics['pcm16']['exact_error_energy']:
            raise AssertionError('Callback substitution differs from full fresh SSE')
        file_bytes = sum(map(len, stream_list))
        if file_bytes > record['baseline_bytes']:raise AssertionError('True whole-chain cap failed')
        outputs[role] = dict(stream_bytes=file_bytes, metrics=metrics, descriptors=stats,
            whole_numerical_floors_passed=numerical_floors(metrics, baseline),
            pcm16_sha256=sha(pcm.astype('<i2').tobytes()), pwm_sha256=sha(pwm_duties(pcm).tobytes()),
            segment_sha256=[sha(blob) for blob in stream_list],
            changed_segments=[i for i, blob in enumerate(stream_list) if blob != blobs[i]])
    if not outputs['selected']['whole_numerical_floors_passed']:
        raise AssertionError('Conservative complete PCM/PWM numerical floors failed')
    report = dict(ordinal=ordinal, id=record['id'], private_case_id=record['private_case_id'],
        profile=record['profile'], samples=len(reference), segment_samples=lengths,
        baseline_bytes=record['baseline_bytes'], selected_segments=chosen_indices,
        baseline_segment_error_energy=errors, reference_descriptors=descriptors(reference),
        settings=settings, searches=searches, outputs=outputs, untouched_segments=len(blobs)-len(chosen_indices),
        all_native_common_v5_model_pcm_pwm_exact=True, full_original_length_gain_exact=True,
        stoi_computed=False, metric_scope='Non-speech numerical robustness only; no subjective quality/adoption or hardware claim.',
        seconds=time.perf_counter()-begun, cpu_seconds=time.process_time()-cpu)
    save(output/'result-private.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--phase', choices=('smoke', 'full'), required=True)
    p.add_argument('--smoke-result', type=Path)
    p.add_argument('--shard', type=int, default=0)
    p.add_argument('--shards', type=int, default=1)
    a = p.parse_args()
    if not 1 <= a.shards <= 8 or not 0 <= a.shard < a.shards:
        raise ValueError('Invalid deterministic shard')
    output = a.output.resolve()
    if not output.is_relative_to((REPOSITORY/'build').resolve()) or output == (REPOSITORY/'build').resolve():
        raise ValueError('Private outputs must stay inside repository ignored build storage')
    guard_outputs([a.manifest, *(ROOT/'tools'/name for name in source_inventory()['encoder'])],
                    [output/'results-private.json', output/'results-private.writing', output/'protocol-private.json', output/'protocol-private.writing'])
    output.mkdir(parents=True, exist_ok=True)
    manifest_bytes = a.manifest.read_bytes(); manifest = json.loads(manifest_bytes)
    records = manifest['records']; source = source_inventory()
    inputs = [a.manifest, *[Path(r['reference']['path']) for r in records],
              *[Path(s['path']) for r in records for s in r['segments']]]
    targets = []
    for i, record in enumerate(records):
        folder = output/f'group-{i+1:03d}'
        targets.extend(folder/name for name in ('result-private.json', 'result-private.writing'))
        targets.extend(folder/f'{role}-{j:03d}.l4hy' for role in ('selected', 'raw') for j in range(len(record['segments'])))
    guard_outputs(inputs, targets)
    if source['core'] != manifest['source_sha256'] or any(r['split'] != 'non_speech' for r in records):
        raise ValueError('Frozen non-speech source/split contract changed')
    protocol = dict(settings=SETTINGS, source=source, manifest_sha256=sha(manifest_bytes),
        selection='Largest original exact PCM SSE/sample with earliest tie; final segment if distinct.',
        objective='Exact additive whole-record PCM SSE, centered by its frozen constant.',
        metric_scope='No STOI; complete original-level PCM/PWM errors and descriptive activity/RMS/clipping proxies.',
        speech=False, reference_length_gain='No shortening/resampling/normalization')
    fingerprint = sha(canonical(protocol))
    save(output/'protocol-private.json', dict(protocol, fingerprint=fingerprint))
    smoke = smoke_indices(records)
    if a.phase == 'full':
        if a.smoke_result is None:raise ValueError('Frozen independent smoke result required before full run')
        proof = json.loads(a.smoke_result.read_text(encoding='utf-8'))
        if proof['status'] != 'complete' or proof['protocol_fingerprint'] != fingerprint or len(proof['records']) != len(smoke):
            raise ValueError('Smoke protocol or source differs; rerun smoke')
    indices = smoke if a.phase == 'smoke' else list(range(len(records)))
    indices = [i for i in indices if i % a.shards == a.shard]
    results = []; begun = time.perf_counter()
    state = dict(schema='lpx-v5-nonspeech-trajectory-robustness-private-v1', status='running',
                 phase=a.phase, shard=a.shard, shards=a.shards, protocol=protocol,
                 protocol_fingerprint=fingerprint, planned_ordinals=[i+1 for i in indices], records=results)
    save(output/'results-private.json', state)
    with BatchSession('batch', speech=True, speech_compact=True) as common, BatchSession('batch', speech=True, speech_compact=True, compact_only=True) as narrow:
        for i in indices:
            result = run_group(records[i], i+1, output/f'group-{i+1:03d}', common, narrow)
            results.append(result)
            if source_inventory() != source or sha(a.manifest.read_bytes()) != protocol['manifest_sha256']:
                raise AssertionError('Source/manifest changed during frozen run')
            state['seconds'] = time.perf_counter()-begun
            save(output/'results-private.json', state)
            print(json.dumps(dict(completed=len(results), total=len(indices), ordinal=i+1,
                profile=result['profile'], samples=result['samples'], edited_segment_candidates=len(result['selected_segments']),
                selected_bytes=result['outputs']['selected']['stream_bytes'],
                raw_numerical_floors=result['outputs']['raw']['whole_numerical_floors_passed'])), flush=True)
    state.update(status='complete', seconds=time.perf_counter()-begun)
    save(output/'results-private.json', state)
    print(json.dumps(dict(phase=a.phase, complete=len(results), all_exact=True)), flush=True)


if __name__ == '__main__':
    main()

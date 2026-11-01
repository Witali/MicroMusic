"""Independently re-audit saved complete non-speech trajectory outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np
import soundfile as sf

import benchmark_nonspeech_trajectory as study
from batch_decoder import BatchSession
import speech_compact as compact
from standard_metrics import pwm_duties


def audit_group(record, result, folder, common, narrow):
    path = Path(record['reference']['path'])
    if study.sha(path.read_bytes()) != record['reference']['file_sha256']:
        raise AssertionError('Frozen original reference changed')
    reference, rate = sf.read(path, dtype='int16')
    if (rate != 8000 or reference.ndim != 1 or len(reference) != record['samples'] or
            study.sha(reference.astype('<i2').tobytes()) != record['reference']['pcm16_sha256']):
        raise AssertionError('Original reference length/level differs')
    blobs = []
    lengths = []
    offset = 0
    for i, entry in enumerate(record['segments']):
        blob = Path(entry['path']).read_bytes()
        fields = compact.unpack(blob)
        if (study.sha(blob) != entry['stream_sha256'] or len(blob) != entry['file_bytes'] or
                fields[0] != entry['samples'] or fields[1] != record['profile'] or
                entry['start'] != offset or entry['index'] != i):
            raise AssertionError('Frozen ordered segment differs')
        blobs.append(blob); lengths.append(fields[0]); offset += fields[0]
    if offset != len(reference) or lengths != result['segment_samples']:
        raise AssertionError('Reset geometry changed')
    original_parts, original = study.decode_chain(blobs, common, narrow)
    baseline = study.numerical_metrics(reference, original)
    offsets = np.cumsum([0, *lengths]).tolist()
    errors = [study.exact_sse(reference[offsets[i]:offsets[i+1]], part)
              for i, part in enumerate(original_parts)]
    indices = study.select_segments(errors, lengths)
    if indices != result['selected_segments'] or errors != result['baseline_segment_error_energy']:
        raise AssertionError('Segment choice differs from the frozen predeclared rule')
    if result['reference_descriptors'] != study.descriptors(reference):
        raise AssertionError('Original-level descriptors differ')
    cache = {tuple(blobs): (original_parts, original)}
    roles = {}
    for role in ('baseline', 'selected', 'raw'):
        chain = list(blobs)
        if role != 'baseline':
            for index in indices:
                candidate = (Path(folder)/f'{role}-{index:03d}.l4hy').read_bytes()
                if len(candidate) > len(blobs[index]) or compact.unpack(candidate)[:2] != compact.unpack(blobs[index])[:2]:
                    raise AssertionError('Edited-segment cap/geometry changed')
                chain[index] = candidate
        key = tuple(chain)
        if key not in cache:
            cache[key] = study.decode_chain(key, common, narrow)
        parts, pcm = cache[key]
        metrics = study.numerical_metrics(reference, pcm)
        stored = result['outputs'][role]
        if len(pcm) != len(reference) or metrics != stored['metrics'] or study.descriptors(pcm) != stored['descriptors']:
            raise AssertionError('Independent full numerical reconstruction differs')
        if (study.sha(pcm.astype('<i2').tobytes()) != stored['pcm16_sha256'] or
                study.sha(pwm_duties(pcm).tobytes()) != stored['pwm_sha256'] or
                [study.sha(blob) for blob in chain] != stored['segment_sha256']):
            raise AssertionError('Actual saved output differs from its private evidence')
        if sum(map(len, chain)) != stored['stream_bytes'] or stored['stream_bytes'] > record['baseline_bytes']:
            raise AssertionError('True complete-chain cap differs')
        additive = baseline['pcm16']['exact_error_energy']
        for index in indices:
            additive += study.exact_sse(reference[offsets[index]:offsets[index+1]], parts[index])-errors[index]
        if additive != metrics['pcm16']['exact_error_energy']:
            raise AssertionError('Whole-record additive SSE differs')
        if study.numerical_floors(metrics, baseline) != stored['whole_numerical_floors_passed']:
            raise AssertionError('Whole PCM/PWM floor label differs')
        roles[role] = dict(stream_bytes=stored['stream_bytes'], whole_numerical_floors_passed=stored['whole_numerical_floors_passed'])
    if not roles['selected']['whole_numerical_floors_passed']:
        raise AssertionError('Numerical selected result regressed')
    for search in result['searches']:
        report = search['report']
        if (report['quality_kind'] != 'non-speech-numerical' or
                report['full_synthesis_evaluations'] > result['settings']['max_evaluations'] or
                report['max_file_bytes'] != len(blobs[search['segment']])):
            raise AssertionError('Search bounds/non-speech contract differs')
    if result['stoi_computed'] or not result['all_native_common_v5_model_pcm_pwm_exact']:
        raise AssertionError('Unexpected metric/backend scope')
    return dict(ordinal=result['ordinal'], profile=result['profile'], samples=len(reference),
                segments=len(blobs), searched_segments=indices, outputs=roles,
                all_complete_native_common_v5_model_pcm_pwm_exact=True,
                full_reference_metrics_caps_and_policy_exact=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', required=True, type=Path)
    p.add_argument('--run', required=True, action='append', type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    output = a.output.resolve()
    if not output.is_relative_to((study.REPOSITORY/'build').resolve()) or output == (study.REPOSITORY/'build').resolve():
        raise ValueError('Private audit storage must stay inside ignored build')
    study.guard_outputs([a.manifest, *a.run, Path(__file__)],
                        [output/'audit-private.json', output/'audit-private.writing'])
    output.mkdir(parents=True, exist_ok=True)
    raw = a.manifest.read_bytes(); manifest = json.loads(raw); source = study.source_inventory()
    source_files = dict(source, independent_auditor=study.sha(Path(__file__).read_bytes()))
    rows = []; planned = []
    runs = []
    for path in a.run:
        run = json.loads(path.read_text(encoding='utf-8'))
        if (run['status'] != 'complete' or run['protocol']['source'] != source or
                run['protocol']['settings'] != study.SETTINGS or
                run['protocol']['manifest_sha256'] != study.sha(raw) or
                study.sha(study.canonical(run['protocol'])) != run['protocol_fingerprint']):
            raise AssertionError('Frozen run/source/manifest protocol differs')
        runs.append((path, run))
        planned.extend(run['planned_ordinals'])
    if len(planned) != len(set(planned)):
        raise ValueError('Audit runs overlap')
    begun = time.perf_counter()
    state = dict(schema='lpx-v5-nonspeech-trajectory-audit-private-v1', status='running',
                 source=source_files, manifest_sha256=study.sha(raw), planned_ordinals=sorted(planned), records=rows)
    study.save(output/'audit-private.json', state)
    with BatchSession('batch', speech=True, speech_compact=True) as common, BatchSession('batch', speech=True, speech_compact=True, compact_only=True) as narrow:
        for path, run in runs:
            for result in run['records']:
                ordinal = result['ordinal']; record = manifest['records'][ordinal-1]
                if result['id'] != record['id'] or result['settings'] != study.SETTINGS:
                    raise AssertionError('Saved group identity/settings differ')
                row = audit_group(record, result, path.parent/f'group-{ordinal:03d}', common, narrow)
                rows.append(row)
                if study.source_inventory() != source or study.sha(a.manifest.read_bytes()) != state['manifest_sha256']:
                    raise AssertionError('Source/manifest changed during audit')
                state['seconds'] = time.perf_counter()-begun
                study.save(output/'audit-private.json', state)
                print(json.dumps(dict(audited=len(rows), total=len(planned), ordinal=ordinal,
                    samples=row['samples'], all_exact=True)), flush=True)
    if sorted(row['ordinal'] for row in rows) != sorted(planned):
        raise AssertionError('Audit did not cover its complete run set')
    state.update(status='complete', seconds=time.perf_counter()-begun)
    study.save(output/'audit-private.json', state)
    print(json.dumps(dict(complete=len(rows), all_exact=True)), flush=True)


if __name__ == '__main__':
    main()

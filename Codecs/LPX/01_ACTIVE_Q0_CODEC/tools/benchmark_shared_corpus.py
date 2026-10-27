"""LPX 4/6 validation on local shared audio; generated media stay in build/."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
from pathlib import Path
import time

import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from benchmark_standards import save
from enhance_speech_compact import enhance
from level_policy import preserves_activity
from profile_avr import ROOT
from refine_speech_v4 import refine
from shared_corpus import prepare
from speech_compact import decode_model
from speech_v4 import encode
from standard_metrics import error_metrics, pwm_duties, pwm_pcm16

PROFILES = (4, 6)
ENCODER_FILES = ('speech_v4.py', 'refine_speech_v4.py', 'speech_compact.py',
                 'enhance_speech_compact.py', 'standard_metrics.py',
                 'level_policy.py', 'q0_model.py', 'batch_decoder.py', 'wav_lpc.py',
                 'lpx4.py', 'rice_v3.py', 'rice_v7.py')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def environment():
    files = [ROOT/'tools'/name for name in ENCODER_FILES]
    files += [p for p in sorted((ROOT/'src').iterdir()) if p.is_file()]
    return {'source_sha256': {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p.read_bytes()) for p in files},
            'benchmark_sha256': sha(Path(__file__).read_bytes()), 'sample_rate': 8000,
            'python': platform.python_version(),
            'packages': {name: importlib.metadata.version(name) for name in ('numpy', 'scipy', 'numba', 'pystoi', 'soundfile')},
            'protocol': 'Original levels, complete references, balanced independent segments <=64000; no fitted gain/delay.'}


def checked_reference(root, row, key='reference_pcm16_sha256'):
    base = Path(root).resolve()
    path = (base/row['reference']).resolve()
    if Path(row['reference']).is_absolute() or not path.is_relative_to(base):
        raise ValueError('Reference escapes prepared input tree')
    pcm, rate = sf.read(path, dtype='int16')
    if rate != 8000 or pcm.shape != (row['samples'],) or sha(pcm.astype('<i2').tobytes()) != row[key]:
        raise ValueError('Prepared PCM reference changed')
    return pcm


def validated_inputs(inputs, case):
    reference = checked_reference(inputs, case)
    segments = []
    start = 0
    for index, row in enumerate(case['segments']):
        if row['index'] != index or row['start'] != start or not 1 <= row['samples'] <= 64000:
            raise ValueError('Invalid contiguous segment accounting')
        part = checked_reference(inputs, row, 'pcm16_sha256')
        if not np.array_equal(part, reference[start:start+len(part)]):
            raise ValueError('Segment differs from complete reference slice')
        segments.append(part)
        start += len(part)
    if start != len(reference):
        raise ValueError('Segments do not cover the full reference')
    return reference, segments


def validate_saved(row, case, profile, env, identity, dest, inputs):
    reference, refs = validated_inputs(inputs, case)
    unsigned = {k: v for k, v in row.items() if k != 'report_sha256'}
    if (row.get('report_sha256') != sha(canonical(unsigned)) or
            row.get('fingerprint') != identity or row.get('environment') != env or
            row.get('id') != case['id'] or row.get('profile') != profile or
            row.get('reference_pcm16_sha256') != case['reference_pcm16_sha256']):
        raise ValueError('Stale or modified result metadata')
    if row['status'] != 'complete':
        return row
    if len(row['segments']) != len(refs):
        raise ValueError('Cached result has a different segment count')
    pieces = []
    for expected, ref, segment in zip(case['segments'], refs, row['segments']):
        if any(segment[k] != expected[k] for k in ('index', 'start', 'samples')):
            raise ValueError('Cached segment geometry changed')
        stream_path = (dest/segment['stream']).resolve()
        if not stream_path.is_relative_to(dest.resolve()):
            raise ValueError('Cached stream escapes result directory')
        blob = stream_path.read_bytes()
        pcm = checked_reference(dest, {'reference': segment['decoded'], 'samples': len(ref),
            'pcm16_sha256': segment['pcm16_sha256']}, 'pcm16_sha256')
        cap = 20 + ((len(ref)+319)//320)*(20 if profile == 4 else 30)
        if (sha(blob) != segment['stream_sha256'] or blob[:5] != b'L4HY\x05' or blob[5] not in (profile, profile|128) or
                len(blob) != segment['file_bytes'] or len(blob) > cap or segment['cap_bytes'] != cap or
                not np.array_equal(pcm, decode_model(blob)) or
                sha(pwm_duties(pcm).tobytes()) != segment['pwm_sha256']):
            raise ValueError('Cached stream/PCM/model/PWM verification failed')
        pieces.append(pcm)
    pcm = np.concatenate(pieces)
    saved = checked_reference(dest, {'reference': 'complete.wav', 'samples': len(reference),
        'pcm16_sha256': row['pcm16_sha256']}, 'pcm16_sha256')
    if not np.array_equal(pcm, saved) or row['file_bytes'] != sum(s['file_bytes'] for s in row['segments']):
        raise ValueError('Cached full output or byte accounting changed')
    return row


def quality(reference, pcm, speech):
    x = reference.astype(float)
    y = pcm.astype(float)
    source_rms = float(np.sqrt(np.mean(x*x)))
    output_rms = float(np.sqrt(np.mean(y*y)))
    metrics = error_metrics(reference, pcm, speech)
    pwm_samples = pwm_pcm16(pcm)
    pwm = error_metrics(reference, pwm_samples, speech)
    pwm_rms = float(np.sqrt(np.mean(pwm_samples.astype(float)**2)))
    return {'pcm16': metrics, 'pwm8': pwm,
            'activity_preserved': bool(preserves_activity(reference, pcm)),
            'pwm_activity_preserved': bool(preserves_activity(reference, pwm_samples)),
            'sse_no_worse_than_silence': metrics['error_energy'] <= metrics['reference_energy'],
            'rms_gain_db': 20*math.log10(output_rms/source_rms) if output_rms and source_rms else None,
            'reference_rms': source_rms, 'output_rms': output_rms,
            'pwm_output_rms': pwm_rms,
            'pwm_rms_gain_db': 20*math.log10(pwm_rms/source_rms) if pwm_rms and source_rms else None,
            'dc_error_pcm16': float(np.mean(y)-np.mean(x)),
            'clipped_samples': int(np.count_nonzero((pcm == -32768) | (pcm == 32767)))}


def run_encode(inputs, output, shard=0, shards=1, cohorts=None, profiles=PROFILES):
    if not 0 <= shard < shards:
        raise ValueError('Invalid independent shard')
    inputs, output = Path(inputs), Path(output)
    manifest = load(inputs/'manifest.json')
    if manifest.get('schema') != 'lpx-shared-corpus-v1':
        raise ValueError('Expected prepared shared corpus manifest')
    env = environment()
    jobs = [(case, p) for case in manifest['cases'] if not cohorts or case['cohort'] in cohorts for p in profiles]
    complete = 0
    with BatchSession('batch', v3_features=24, speech=True, speech_compact=True) as decoder, \
         BatchSession('batch', v3_features=24, speech=True, speech_compact=True, compact_only=True) as only:
        for index, (case, profile) in enumerate(jobs):
            if index % shards != shard:
                continue
            dest = output/case['id']/str(profile)
            identity = sha(canonical([env, case, profile]))
            cache = dest/'report.json'
            if cache.exists():
                old = load(cache)
                validate_saved(old, case, profile, env, identity, dest, inputs)
                complete += old['status'] == 'complete'
                continue
            dest.mkdir(parents=True, exist_ok=True)
            row = {'id': case['id'], 'cohort': case['cohort'], 'kind': case['kind'],
                   'language': case['language'], 'condition': case['condition'], 'split': case['split'],
                   'samples': case['samples'], 'reference_pcm16_sha256': case['reference_pcm16_sha256'],
                   'profile': profile, 'fingerprint': identity, 'environment': env,
                   'status': 'failed', 'segments': []}
            started = time.perf_counter()
            try:
                reference, segment_refs = validated_inputs(inputs, case)
                pieces = []
                speech = case['kind'] == 'speech'
                for segment, ref in zip(case['segments'], segment_refs):
                    n = len(ref)
                    cap = 20 + ((n+319)//320)*(20 if profile == 4 else 30)
                    original, _, enc = encode(ref, profile, decoder)
                    refined, _, refinement = refine(ref, original, decoder, passes=2, horizon=320)
                    blob, pcm, enhancement = enhance(ref, refined, decoder, cap)
                    model = decode_model(blob)
                    pwm = decoder.decode_one(blob, n)
                    only_pcm = only.decode_one_s16(blob, n)
                    if len(blob) > cap or not np.array_equal(pcm, model) or not np.array_equal(pcm, only_pcm):
                        raise AssertionError('Complete-file cap or integer model/compact-only mismatch')
                    if not np.array_equal(pwm, pwm_duties(pcm)):
                        raise AssertionError('Native PWM transfer mismatch')
                    stem = f'segment-{segment["index"]:03d}'
                    (dest/(stem+'.l4hy')).write_bytes(blob)
                    sf.write(dest/(stem+'.wav'), pcm, 8000, subtype='PCM_16')
                    pieces.append(pcm)
                    row['segments'].append({'index': segment['index'], 'start': segment['start'], 'samples': n,
                        'reference_pcm16_sha256': segment['pcm16_sha256'], 'stream': stem+'.l4hy', 'decoded': stem+'.wav',
                        'stream_sha256': sha(blob), 'pcm16_sha256': sha(pcm.astype('<i2').tobytes()),
                        'pwm_sha256': sha(pwm.tobytes()), 'cap_bytes': cap, 'file_bytes': len(blob),
                        'header_bytes': 22, 'payload_bytes': len(blob)-22,
                        'native_model_pcm16_exact': True, 'native_compact_only_pcm16_exact': True,
                        'native_pwm_exact': True,
                        'quality': quality(ref, pcm, speech),
                        'encode_seconds': enc['seconds'], 'refine_seconds': refinement['seconds'],
                        'enhance_seconds': enhancement['seconds']})
                pcm = np.concatenate(pieces)
                if pcm.shape != reference.shape:
                    raise AssertionError('Segmentation discarded samples')
                sf.write(dest/'complete.wav', pcm, 8000, subtype='PCM_16')
                size = sum(s['file_bytes'] for s in row['segments'])
                payload = sum(s['payload_bytes'] for s in row['segments'])
                row.update(status='complete', quality=quality(reference, pcm, speech), file_bytes=size,
                           payload_bytes=payload, file_bps=size*64000/len(reference),
                           payload_bps=payload*64000/len(reference),
                           pcm16_sha256=sha(pcm.astype('<i2').tobytes()), segment_resets=len(pieces))
            except (ValueError, AssertionError, RuntimeError) as error:
                if isinstance(error, ValueError) and str(error) == 'Exact compact baseline does not fit file cap':
                    row['status'] = 'no_fit'
                row['error'] = {'type': type(error).__name__, 'message': str(error) if isinstance(error, (ValueError, AssertionError)) else 'Runtime failure; inspect private local logs.'}
            row['seconds'] = time.perf_counter()-started
            row['report_sha256'] = sha(canonical(row))
            save(cache, row)
            complete += row['status'] == 'complete'
            q = row.get('quality', {}).get('pcm16', {})
            print(case['id'], profile, row['status'], 'SER', q.get('ser_db'), 'STOI', q.get('stoi'), flush=True)
    if environment() != env:
        raise ValueError('Source changed during corpus measurement')
    print('Shard', shard, 'completed', complete, 'jobs', flush=True)


def summarize(inputs, output, destination):
    manifest = load(Path(inputs)/'manifest.json')
    env = environment()
    rows = []
    for case in manifest['cases']:
        for p in PROFILES:
            path = Path(output)/case['id']/str(p)/'report.json'
            if not path.exists():
                raise ValueError('Incomplete full matrix')
            identity = sha(canonical([env, case, p]))
            rows.append(validate_saved(load(path), case, p, env, identity, path.parent, inputs))
    groups = {}
    for cohort in sorted({r['cohort'] for r in rows}):
        groups[cohort] = {}
        for p in PROFILES:
            chosen = [r for r in rows if r['cohort'] == cohort and r['profile'] == p]
            ok = [r for r in chosen if r['status'] == 'complete']
            def scores(field):
                values = [r['quality']['pcm16'][field] for r in ok if r['quality']['pcm16'][field] is not None]
                return {'count': len(values), 'mean': float(np.mean(values)) if values else None,
                        'minimum': min(values) if values else None, 'maximum': max(values) if values else None}
            groups[cohort][str(p)] = {'cases': len(chosen), 'complete': len(ok),
                'failed': sum(r['status'] == 'failed' for r in chosen),
                'no_fit': sum(r['status'] == 'no_fit' for r in chosen), 'ser_db': scores('ser_db'), 'stoi': scores('stoi'),
                'activity_failures': sum(not r['quality']['activity_preserved'] for r in ok),
                'pwm_activity_failures': sum(not r['quality']['pwm_activity_preserved'] for r in ok),
                'worse_than_silence': sum(not r['quality']['sse_no_worse_than_silence'] for r in ok),
                'file_bytes': sum(r['file_bytes'] for r in ok), 'samples': sum(r['samples'] for r in ok)}
    report = {'schema': 'lpx-shared-corpus-results-v1', 'environment': rows[0]['environment'],
              'input_manifest_sha256': sha((Path(inputs)/'manifest.json').read_bytes()),
              'matrix_rows': len(rows), 'groups': groups, 'cases': rows,
              'physical_hardware_measured': False, 'human_listening_scores_collected': False}
    save(Path(destination), report)
    print(json.dumps(groups, indent=2), flush=True)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--collection', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cohorts', nargs='+')
    p = sub.add_parser('encode')
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--shard', type=int, default=0)
    p.add_argument('--shards', type=int, default=1)
    p.add_argument('--cohorts', nargs='+')
    p.add_argument('--profiles', type=int, choices=PROFILES, nargs='+', default=PROFILES)
    p = sub.add_parser('summarize')
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    args = vars(ap.parse_args())
    mode = args.pop('mode')
    if mode == 'prepare':
        prepare(**args)
    elif mode == 'encode':
        run_encode(**args)
    else:
        summarize(**args)


if __name__ == '__main__':
    main()

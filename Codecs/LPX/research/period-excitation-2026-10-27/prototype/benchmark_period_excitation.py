#!/usr/bin/env python3
"""Benchmark opt-in LPWB excitation against frozen, private LPX v5 inputs.

The input is an ignored lpx-period-pilot-private-v1 manifest. All generated
streams, WAVs and caches stay in an ignored repository build subdirectory.
results.json contains only anonymous case IDs, hashes, categorical corpus
labels, accounting and numeric measurements. Original paths and fitted books
are never copied into that report. This harness makes no firmware claim.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import time
import traceback
import warnings
import wave

import numpy as np

from batch_decoder import BatchSession
from lpx4 import BitWriter
import period_excitation as period
import speech_compact as compact
from standard_metrics import error_metrics, pwm_duties, pwm_pcm16
from wav_to_lpx4 import quality


TOOLS = Path(__file__).resolve().parent
REPOSITORY = TOOLS.parents[4]
ACTIVE_TOOLS = REPOSITORY / 'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'
RATE = 8000
TOLERANCE = 1e-10
WORDS = (0, 4, 8)
RATE_WEIGHTS = (0., .05)
SCHEMA = 'lpx-period-benchmark-v1'
ANONYMOUS_ID = re.compile(r'(?:period-speech-[0-9]{2,}|case-[0-9a-f]{16})\Z')


class BenchmarkError(ValueError):
    """An error whose message contains no private source information."""


def sha(content):
    return hashlib.sha256(content).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.writing')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n',
                         encoding='utf-8', newline='\n')
    temporary.replace(path)


def checked_output(output):
    output = Path(output).resolve()
    build = (REPOSITORY / 'build').resolve()
    rules = (REPOSITORY / '.gitignore').read_text(encoding='utf-8').splitlines()
    if (output == build or not output.is_relative_to(build) or
            '/build/' not in (line.strip() for line in rules)):
        raise BenchmarkError('Output must be a subdirectory of ignored repository build/')
    return output


def artifact_bytes(record, output):
    path = Path(record['path']).resolve()
    if path.is_relative_to(output):
        raise BenchmarkError('Input and benchmark output must not overlap')
    content = path.read_bytes()
    if (sha(content) != record['file_sha256'] or
            len(content) != record.get('file_bytes', len(content))):
        raise BenchmarkError('Frozen input file hash or size changed')
    return content


def pcm_bytes(pcm):
    return np.asarray(pcm, dtype='<i2').tobytes()


def read_wav(path):
    with wave.open(str(path), 'rb') as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate(),
                source.getcomptype()) != (1, 2, RATE, 'NONE'):
            raise BenchmarkError('Expected mono PCM16 8 kHz WAV')
        raw = source.readframes(source.getnframes())
    return np.frombuffer(raw, dtype='<i2').copy()


def read_pcm(record, output):
    artifact_bytes(record, output)
    pcm = read_wav(Path(record['path']))
    if (len(pcm) != record['samples'] or
            sha(pcm_bytes(pcm)) != record['pcm16_sha256'] or
            record['sample_rate_hz'] != RATE or record['channels'] != 1):
        raise BenchmarkError('Frozen PCM samples or geometry changed')
    return pcm


def write_wav(path, pcm):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(RATE)
        target.writeframes(pcm_bytes(pcm))


def environment():
    names = ('benchmark_period_excitation.py', 'fit_period_excitation.py',
             'period_excitation.py', 'speech_compact.py', 'speech_v4.py',
             'q0_model.py', 'wav_lpc.py', 'lpx4.py', 'rice_v3.py', 'rice_v7.py',
             'rice_v4_reference.py', 'l3av_parse.py',
             'standard_metrics.py', 'wav_to_lpx4.py', 'tune_pcm16.py',
             'batch_decoder.py')
    files = [(TOOLS / name) if (TOOLS / name).is_file() else (ACTIVE_TOOLS / name) for name in names]
    files.extend(sorted((ACTIVE_TOOLS.parent / 'src').iterdir()))
    files.append(REPOSITORY / 'ATtiny13A/Sound/codec/period_wave.py')
    return {'source_sha256': {str(p.relative_to(REPOSITORY)).replace('\\', '/'):
                             sha(p.read_bytes()) for p in files if p.is_file()},
            'python': platform.python_version(),
            'packages': {name: importlib.metadata.version(name)
                         for name in ('numpy', 'scipy', 'numba', 'pystoi', 'soundfile')},
            'native_decoder': {'speech': True, 'speech_compact': True,
                               'v3_features': 124}}


def validate_manifest(path, output, limit_cases=None):
    path = Path(path).resolve()
    if path.is_relative_to(output):
        raise BenchmarkError('Private manifest and output must not overlap')
    content = path.read_bytes()
    manifest = json.loads(content)
    if manifest.get('schema') != 'lpx-period-pilot-private-v1':
        raise BenchmarkError('Unsupported private pilot manifest schema')
    cases = manifest['cases']
    if limit_cases is not None:
        cases = cases[:limit_cases]
    if not cases or len({case['id'] for case in cases}) != len(cases):
        raise BenchmarkError('Expected nonempty, unique anonymous cases')
    for case in cases:
        if not ANONYMOUS_ID.fullmatch(case['id']):
            raise BenchmarkError('Case ID is not an approved anonymous identifier')
        if (case['kind'] != 'speech' or case['sample_rate_hz'] != RATE or
                case['channels'] != 1 or case['samples'] < 1):
            raise BenchmarkError('Unsupported pilot case geometry')
        if (case['language'] not in ('ru', 'en', 'und') or
                case['cohort'] not in ('speech', 'regression', 'independent', 'phrases') or
                case['condition'] not in ('natural', 'clean', 'quiet', 'quiet_minus24dB',
                                          'noise15', 'white_noise_15dB', 'prepared')):
            raise BenchmarkError('Unsupported anonymous corpus category')
        if sorted(pair['profile'] for pair in case['paired_outputs']) != [4, 6]:
            raise BenchmarkError('Expected paired profile 4 and 6 baselines')
    return cases, sha(content)


def checked_baseline(case, pair, refs, full_reference, decoder, output):
    """Check strongest selected v5 bytes with current native and host decoders."""
    selected = pair['selected']
    profile = pair['profile']
    report_content = artifact_bytes(selected['report'], output)
    report = json.loads(report_content)
    unsigned = {key: value for key, value in report.items() if key != 'report_sha256'}
    if (sha(canonical(unsigned)) != report['report_sha256'] or
            report['report_sha256'] != selected['report_signature_sha256'] or
            report['id'] != case['original_case_id'] or
            report['reference_pcm16_sha256'] != case['reference']['pcm16_sha256'] or
            report['samples'] != case['samples'] or report['profile'] != profile or
            report['status'] != 'complete'):
        raise BenchmarkError('Frozen selected baseline report validation failed')
    if len(selected['segments']) != len(refs) or len(report['segments']) != len(refs):
        raise BenchmarkError('Frozen selected baseline segment count changed')
    blobs, pieces, caps = [], [], []
    for reference, segment, saved in zip(refs, selected['segments'], report['segments']):
        if any(segment[key] != reference[key] or saved[key] != reference[key]
               for key in ('index', 'start', 'samples')):
            raise BenchmarkError('Frozen selected baseline segment geometry changed')
        blob = artifact_bytes(segment['stream'], output)
        n = reference['samples']
        if (blob[:5] != b'L4HY\x05' or blob[5] & 127 != profile or
                sha(blob) != saved['stream_sha256'] or len(blob) != saved['file_bytes'] or
                segment['reference_pcm16_sha256'] != reference['reference']['pcm16_sha256']):
            raise BenchmarkError('Frozen selected stream identity changed')
        model = np.asarray(compact.decode_model(blob), dtype=np.int16)
        native = decoder.decode_one_s16(blob, n)
        saved_pcm = read_pcm(segment['decoded'], output)
        if (native is None or len(model) != n or
                not np.array_equal(model, native) or not np.array_equal(model, saved_pcm) or
                sha(pcm_bytes(model)) != saved['pcm16_sha256']):
            raise BenchmarkError('Current native/model/frozen baseline PCM mismatch')
        native_pwm = decoder.decode_one(blob, n)
        if (native_pwm is None or not np.array_equal(native_pwm, pwm_duties(model)) or
                sha(pwm_duties(model).tobytes()) != segment['pwm_sha256']):
            raise BenchmarkError('Current native/fixed-transfer baseline PWM mismatch')
        cap = segment.get('cap_bytes')
        if cap is not None and (cap != saved.get('cap_bytes') or len(blob) > cap):
            raise BenchmarkError('Frozen selected baseline configured cap mismatch')
        blobs.append(blob)
        pieces.append(model)
        caps.append(cap)
    joined = np.concatenate(pieces)
    if (not np.array_equal(joined, read_pcm(selected['complete_decoded'], output)) or
            len(joined) != len(full_reference)):
        raise BenchmarkError('Frozen baseline join differs from complete saved PCM')
    return blobs, pieces, caps


def accounting(blob):
    """Count every serialized LPWB bit, including per-segment dictionaries."""
    model = period.unpack(blob)
    writer = BitWriter()
    spectrum_bits = legacy_bits = periodic_bits = 0
    old = None
    index_bits = len(model['book']).bit_length() - 1
    for packet, spectrum in enumerate(model['spectra']):
        before = writer.total
        compact.put_spectrum(writer, spectrum, old, 5 if model['profile'] == 4 else 6)
        spectrum_bits += writer.total - before
        old = spectrum
        for block in (2 * packet, 2 * packet + 1):
            writer.put(model['phase_codes'][block], 8)
            writer.put(model['modes'][block], 1)
            before = writer.total
            if model['modes'][block]:
                index, gain, level = model['wave_params'][block]
                writer.put(model['params'][block][0], 5)
                writer.put(index, index_bits)
                writer.put(gain, 5)
                writer.put(level, 4)
                periodic_bits += writer.total - before
            else:
                period._put_legacy(writer, model, block)
                legacy_bits += writer.total - before
    payload_bits = writer.total
    writer.aligned()
    payload = writer.get()
    header_bytes = period.HEADER.size
    dictionary_bytes = 16 * len(model['book'])
    if (len(blob) != header_bytes + dictionary_bytes + len(payload) or
            blob[header_bytes + dictionary_bytes:] != payload):
        raise BenchmarkError('LPWB bit accounting does not reproduce the saved payload')
    blocks = len(model['modes'])
    periodic_active = noise_only = silent_book = 0
    for mode, (index, gain, level) in zip(model['modes'], model['wave_params']):
        if mode:
            if gain and any(model['book'][index]):
                periodic_active += 1
            elif level:
                noise_only += 1
            else:
                silent_book += 1
    return {'file_bytes': len(blob), 'header_bytes': header_bytes,
            'dictionary_bytes': dictionary_bytes, 'dictionary_words': len(model['book']),
            'payload_bytes': len(payload),
            'payload_bits': payload_bits, 'padding_bits': len(payload) * 8 - payload_bits,
            'spectrum_bits': spectrum_bits, 'phase_bits': 8 * blocks,
            'mode_bits': blocks, 'periodic_parameter_bits': periodic_bits,
            'legacy_parameter_bits': legacy_bits,
            'metadata_bits_excluding_dictionary': header_bytes * 8 + spectrum_bits + 9 * blocks,
            'legacy_blocks': blocks - sum(model['modes']),
            'periodic_blocks': sum(model['modes']),
            'periodic_active_blocks': periodic_active,
            'noise_only_blocks': noise_only, 'silent_book_blocks': silent_book,
            'unused_final_packet_samples': len(model['spectra']) * 320 - model['n']}


def fit_statistics(report):
    """Explicit numeric allowlist: never retain dictionaries or fitted fields."""
    keys = ('evaluations', 'objective_evaluations', 'candidate_evaluations',
            'full_evaluations', 'local_evaluations', 'synthesis_evaluations',
            'analysis_evaluations', 'trials', 'dictionary_iterations',
            'analysis_frames', 'words', 'rate_weight', 'seconds',
            'periodic_active_blocks', 'noise_only_blocks', 'silent_book_blocks',
            'requested_words', 'retained_words', 'baseline_bytes', 'candidate_bytes',
            'dictionary_bytes', 'header_bytes', 'payload_bytes', 'payload_bits', 'padding_bits')
    result = {}
    for key in keys:
        value = report.get(key)
        if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
            if np.isfinite(value):
                result[key] = value.item() if isinstance(value, np.generic) else value
    modes = report.get('mode_counts', {})
    if isinstance(modes, dict):
        safe_modes = {}
        for key in ('legacy', 'book', 'periodic_active', 'noise_only', 'silent'):
            value = modes.get(key)
            if isinstance(value, (int, np.integer)) and not isinstance(value, bool) and value >= 0:
                safe_modes[key] = int(value)
        if safe_modes:
            result['mode_counts'] = safe_modes
    return result


def metric_set(reference, pcm):
    """Whole-case original-level, unshifted PCM and fixed PWM measurements."""
    with warnings.catch_warnings(record=True):
        warnings.simplefilter('always')
        legacy = quality(reference, pcm, 'speech')
        measures = {'pcm16': error_metrics(reference, pcm, speech=True),
                    'pwm8': error_metrics(reference, pwm_pcm16(pcm), speech=True)}
    for measured in measures.values():
        value = measured['stoi']
        valid = value is not None and np.isfinite(value) and abs(value - 1e-5) > 1e-12
        measured['stoi'] = {'status': 'valid' if valid else 'unavailable',
                            'value': float(value) if valid else None}
    value = legacy['stoi']
    legacy['stoi'] = (float(value) if value is not None and np.isfinite(value) and
                      abs(value - 1e-5) > 1e-12 else None)
    legacy = {key: None if isinstance(value, float) and not np.isfinite(value) else value
              for key, value in legacy.items()}
    measures['wav_to_lpx4_quality'] = legacy
    measures['pwm_sha256'] = sha(pwm_duties(pcm).tobytes())
    return measures


def floors(candidate, baseline):
    checks = {}
    unavailable = 0
    for domain in ('pcm16', 'pwm8'):
        left, right = candidate[domain], baseline[domain]
        checks[domain + '_sse'] = left['error_energy'] <= right['error_energy'] + TOLERANCE
        if right['stoi']['status'] == 'valid':
            checks[domain + '_stoi'] = (left['stoi']['status'] == 'valid' and
                                       left['stoi']['value'] + TOLERANCE >= right['stoi']['value'])
        else:
            checks[domain + '_stoi'] = None
            unavailable += 1
    return {'passed': all(value for value in checks.values() if value is not None),
            'checks': checks, 'unavailable_baseline_stoi_floors': unavailable,
            'absolute_numerical_tolerance': TOLERANCE}


def variant_id(words, weight):
    return f'k{words:02d}-r{round(weight * 1000):03d}'


def cached_fit(directory, fingerprint):
    try:
        meta = json.loads((directory / 'cache-private.json').read_text(encoding='utf-8'))
        blob = (directory / 'candidate.lpwb').read_bytes()
        if meta['fingerprint'] != fingerprint or sha(blob) != meta['stream_sha256']:
            return None
        pcm = np.asarray(period.decode_model(blob), dtype=np.int16)
        if (sha(pcm_bytes(pcm)) != meta['pcm16_sha256'] or
                not np.array_equal(pcm, read_wav(directory / 'candidate.wav')) or
                accounting(blob) != meta['accounting']):
            return None
        return blob, pcm, fit_statistics(meta['fit_statistics'])
    except (OSError, ValueError, KeyError, TypeError, EOFError, wave.Error):
        return None


def aggregate_accounting(rows):
    return {key: sum(row[key] for row in rows) for key in rows[0]}


def selection(rows, scenario):
    eligible = [row for row in rows if row['quality_floors']['passed'] and row['caps'][scenario]]
    best_quality = min(eligible, key=lambda row: (row['metrics']['pcm16']['error_energy'],
                                                row['metrics']['pwm8']['error_energy'],
                                                row['file_bytes'], row['variant']))
    smallest = min(eligible, key=lambda row: (row['file_bytes'],
                                            row['metrics']['pcm16']['error_energy'], row['variant']))
    return {'best_pcm_sse_variant': best_quality['variant'],
            'minimum_bytes_variant': smallest['variant'],
            'eligible_variants': len(eligible)}


def benchmark_case(case, pair, decoder, output, source_fingerprint, seed, counters):
    # Imported only when the benchmark is explicitly run, after the fitter exists.
    from fit_period_excitation import analyze, fit

    started = time.perf_counter()
    reference = read_pcm(case['reference'], output)
    refs, reference_parts, start = case['reference_segments'], [], 0
    for index, segment in enumerate(refs):
        if (segment['index'] != index or segment['start'] != start or
                not 1 <= segment['samples'] <= 64000):
            raise BenchmarkError('Reference segment geometry is not contiguous')
        part = read_pcm(segment['reference'], output)
        if not np.array_equal(part, reference[start:start + len(part)]):
            raise BenchmarkError('Reference segment differs from complete PCM slice')
        reference_parts.append(part)
        start += len(part)
    if start != len(reference):
        raise BenchmarkError('Reference segments do not cover the complete case')
    blobs, baseline_parts, configured_caps = checked_baseline(
        case, pair, refs, reference, decoder, output)
    counters['baseline_segments_verified'] += len(blobs)
    baseline_pcm = np.concatenate(baseline_parts)
    baseline_metrics = metric_set(reference, baseline_pcm)
    baseline_bytes = sum(map(len, blobs))
    all_caps_known = all(cap is not None for cap in configured_caps)
    configured_total = sum(configured_caps) if all_caps_known else None
    variants = [(words, weight) for words in WORDS for weight in RATE_WEIGHTS]
    pieces = {variant_id(*variant): [] for variant in variants}
    accounts = {name: [] for name in pieces}
    segment_rows = []
    destination = output / case['id'] / str(pair['profile'])
    for segment, ref, baseline in zip(refs, reference_parts, blobs):
        analysis = None
        for words, weight in variants:
            name = variant_id(words, weight)
            directory = destination / f"segment-{segment['index']:03d}" / name
            fingerprint = sha(canonical({'environment': source_fingerprint,
                'reference_pcm16_sha256': sha(pcm_bytes(ref)), 'baseline_sha256': sha(baseline),
                'words': words, 'rate_weight': weight, 'seed': seed}))
            cached = cached_fit(directory, fingerprint)
            if cached is None:
                if analysis is None:
                    analysis = analyze(ref, baseline)
                    counters['analyses_executed'] += 1
                candidate, report, analysis = fit(ref, baseline, words=words,
                    rate_weight=weight, seed=seed, analysis=analysis)
                pcm = np.asarray(period.decode_model(candidate), dtype=np.int16)
                if len(pcm) != len(ref):
                    raise BenchmarkError('Candidate decoded length differs from reference')
                stats = fit_statistics(report)
                count = accounting(candidate)
                directory.mkdir(parents=True, exist_ok=True)
                (directory / 'candidate.lpwb').write_bytes(candidate)
                write_wav(directory / 'candidate.wav', pcm)
                save_json(directory / 'cache-private.json', {'schema': SCHEMA + '-fit-cache',
                    'fingerprint': fingerprint, 'stream_sha256': sha(candidate),
                    'pcm16_sha256': sha(pcm_bytes(pcm)), 'fit_statistics': stats,
                    'accounting': count})
                counters['fits_executed'] += 1
            else:
                candidate, pcm, stats = cached
                count = accounting(candidate)
                counters['fits_reused'] += 1
            model = period.unpack(candidate)
            if (model['n'] != len(ref) or model['profile'] != pair['profile'] or
                    len(model['book']) > max(1, words) or
                    (words == 0 and any(any(row) for row in model['book']))):
                raise BenchmarkError('Candidate format geometry differs from requested experiment')
            pieces[name].append(pcm)
            accounts[name].append(count)
            cap = configured_caps[segment['index']]
            segment_rows.append({'index': segment['index'], 'samples': len(ref),
                'variant': name, 'reference_pcm16_sha256': sha(pcm_bytes(ref)),
                'baseline_stream_sha256': sha(baseline), 'candidate_stream_sha256': sha(candidate),
                'candidate_pcm16_sha256': sha(pcm_bytes(pcm)),
                'baseline_file_bytes': len(baseline), 'configured_cap_bytes': cap,
                'within_existing_stream_bytes': len(candidate) <= len(baseline),
                'within_configured_cap': len(candidate) <= cap if cap is not None else None,
                'accounting': count, 'fit_statistics': stats})
    baseline = {'variant': 'baseline-v5', 'file_bytes': baseline_bytes,
                'file_bps': baseline_bytes * 8 * RATE / len(reference),
                'metrics': baseline_metrics, 'quality_floors': floors(baseline_metrics, baseline_metrics),
                'caps': {'existing_total_bytes': True, 'existing_segment_bytes': True,
                         'configured_caps': True}}
    rows = [baseline]
    for words, weight in variants:
        name = variant_id(words, weight)
        joined = np.concatenate(pieces[name])
        measured = metric_set(reference, joined)
        count = aggregate_accounting(accounts[name])
        write_wav(destination / name / 'complete.wav', joined)
        related = [row for row in segment_rows if row['variant'] == name]
        configured_fit = all_caps_known and all(row['within_configured_cap'] for row in related)
        existing_total_fit = count['file_bytes'] <= baseline_bytes
        existing_segment_fit = all(row['within_existing_stream_bytes'] for row in related)
        rows.append({'variant': name, 'words': words, 'rate_weight': weight,
            'file_bytes': count['file_bytes'], 'accounting': count,
            'file_bps': count['file_bytes'] * 8 * RATE / len(reference),
            'metrics': measured, 'quality_floors': floors(measured, baseline_metrics),
            'byte_limit_diagnostics': {'existing_total_bytes': existing_total_fit,
                                      'each_existing_segment_bytes': existing_segment_fit,
                                      'each_configured_segment_cap': configured_fit},
            'caps': {'existing_total_bytes': existing_total_fit and configured_fit,
                     'existing_segment_bytes': existing_segment_fit and configured_fit,
                     'configured_caps': (configured_fit and
                                         count['file_bytes'] <= configured_total) if all_caps_known else False}})
    return {'id': case['id'], 'cohort': case['cohort'], 'language': case['language'],
            'condition': case['condition'], 'profile': pair['profile'],
            'samples': len(reference), 'seconds': len(reference) / RATE,
            'reference_pcm16_sha256': sha(pcm_bytes(reference)),
            'baseline_total_file_bytes': baseline_bytes, 'configured_total_cap_bytes': configured_total,
            'baseline_current_native_model_and_saved_pcm_exact': True,
            'baseline_current_native_and_fixed_transfer_pwm_exact': True,
            'segment_resets': len(refs), 'segments': segment_rows, 'variants': rows,
            'selection': {scenario: selection(rows, scenario) for scenario in
                          ('existing_total_bytes', 'existing_segment_bytes', 'configured_caps')},
            'elapsed_seconds': time.perf_counter() - started}


def run(manifest_path, output, limit_cases=None, seed=20261027):
    started = time.perf_counter()
    output = checked_output(output)
    cases, manifest_hash = validate_manifest(manifest_path, output, limit_cases)
    env = environment()
    source_fingerprint = sha(canonical(env))
    counters = {'baseline_segments_verified': 0, 'analyses_executed': 0,
                'fits_executed': 0, 'fits_reused': 0}
    report = {'schema': SCHEMA, 'input_manifest_sha256': manifest_hash,
        'environment': env, 'seed': seed, 'words': list(WORDS),
        'rate_weights': list(RATE_WEIGHTS), 'case_count': len(cases),
        'expected_baseline_segments': 2 * sum(len(case['reference_segments']) for case in cases),
        'expected_candidate_streams': 2 * len(WORDS) * len(RATE_WEIGHTS) *
                                      sum(len(case['reference_segments']) for case in cases),
        'protocol': {'original_level_and_dc': True, 'gain_fit': False, 'delay_fit': False,
            'full_case_join_before_quality': True, 'fixed_pwm_gain': 130,
            'fixed_pwm_rounding': 1, 'all_lpwb_header_dictionary_metadata_padding_counted': True,
            'baseline_is_frozen_selected_v5': True,
            'floors': 'PCM/PWM SSE <= baseline; available PCM/PWM STOI >= baseline; absolute tolerance 1e-10.',
            'unavailable_stoi': 'No invented floor; explicitly counted as unavailable.',
            'selection': 'Keep baseline eligible; report best PCM SSE and minimum bytes choices separately.',
            'cap_scenarios': ['existing total complete-stream bytes',
                              'each existing segment complete-stream bytes',
                              'each configured segment cap and their total'],
            'configured_segment_caps_mandatory_for_adoption': True,
            'firmware_or_real_time_support_claimed': False,
            'human_listening_scores_collected': False},
        'status': 'running', 'counters': counters, 'cases': []}
    output.mkdir(parents=True, exist_ok=True)
    with BatchSession('batch', speech=True, speech_compact=True, v3_features=124) as decoder:
        if decoder is None:
            raise BenchmarkError('Current native batch decoder is required')
        for case in cases:
            for pair in case['paired_outputs']:
                row = benchmark_case(case, pair, decoder, output, source_fingerprint, seed, counters)
                report['cases'].append(row)
                save_json(output / 'results.json', report)
                print(json.dumps({'id': row['id'], 'profile': row['profile'],
                                  'status': 'complete', 'fits_executed': counters['fits_executed'],
                                  'fits_reused': counters['fits_reused']}), flush=True)
    report['status'] = 'complete'
    if (counters['baseline_segments_verified'] != report['expected_baseline_segments'] or
            counters['fits_executed'] + counters['fits_reused'] != report['expected_candidate_streams']):
        raise BenchmarkError('Completed benchmark job accounting is inconsistent')
    report['completed_case_profiles'] = len(report['cases'])
    report['elapsed_seconds'] = time.perf_counter() - started
    raw = [variant for case in report['cases'] for variant in case['variants'][1:]]
    report['raw_variant_counts'] = {'total': len(raw),
        'strict_quality_floors_passed': sum(row['quality_floors']['passed'] for row in raw),
        'accepted_under_existing_total': sum(row['quality_floors']['passed'] and
                                             row['caps']['existing_total_bytes'] for row in raw),
        'accepted_under_configured_caps': sum(row['quality_floors']['passed'] and
                                              row['caps']['configured_caps'] for row in raw)}
    report['selection_counts'] = {}
    for scenario in ('existing_total_bytes', 'existing_segment_bytes', 'configured_caps'):
        counts = {}
        for row in report['cases']:
            mode = row['selection'][scenario]['best_pcm_sse_variant']
            counts[mode] = counts.get(mode, 0) + 1
        report['selection_counts'][scenario] = counts
    save_json(output / 'results.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path, help='Private pilot input manifest')
    parser.add_argument('output', type=Path, help='Ignored repository build subdirectory')
    parser.add_argument('--limit-cases', type=int, help='First N anonymous cases for a smoke run')
    parser.add_argument('--seed', type=int, default=20261027)
    args = parser.parse_args()
    if args.limit_cases is not None and args.limit_cases < 1:
        parser.error('--limit-cases must be positive')
    try:
        result = run(args.manifest, args.output, args.limit_cases, args.seed)
    except Exception as exc:
        # Detailed diagnostics can contain private input paths: save locally only.
        try:
            output = checked_output(args.output)
            output.mkdir(parents=True, exist_ok=True)
            (output / 'failure-private.txt').write_text(traceback.format_exc(), encoding='utf-8')
        except Exception:
            pass
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__,
                          'private_diagnostics': 'failure-private.txt'}))
        return 1
    print(json.dumps({'status': result['status'], 'case_profiles': result['completed_case_profiles'],
                      'counters': result['counters'], 'selection_counts': result['selection_counts']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

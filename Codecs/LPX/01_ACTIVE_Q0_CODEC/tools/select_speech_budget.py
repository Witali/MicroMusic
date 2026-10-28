"""Choose among measured v5 budgets using complete firmware cost.

The default automatically selects a quality-safe result that does not grow the
full image. Measured growth alternatives remain a listening shortlist. The
explicit metric-proxy policy can recommend growth above configured numerical
thresholds; it never establishes perceptual improvement or timing admission.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import re
import sys

import numpy as np
from refine_speech_compact import quality, no_regression
from speech_compact import unpack, decode_model
from standard_metrics import error_metrics, pwm_duties, pwm_pcm16
from benchmark_speech_flash import source_hashes, srcdir

ROOT = Path(__file__).resolve().parents[1]
HEX = re.compile(r'[0-9a-f]{64}\Z')
TOLERANCE = 1e-12
COST_SCHEMA = 'lpx-v5-firmware-cost-v1'


def _integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(name + ' must be an integer >= ' + str(minimum))
    return value


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _hash(value, name):
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise ValueError(name + ' must be a lowercase SHA256 hex string')
    return value


def exact_budget_cap(byte_count, growth_percent):
    """Round a proposed stream budget upward with exact integer arithmetic.

    This arithmetic helper does not impose the stream API's 65535-byte limit;
    the encoder still validates the supplied complete-stream cap separately.
    """
    _integer(byte_count, 'byte_count', 1)
    _integer(growth_percent, 'growth_percent')
    return (byte_count * (100 + growth_percent) + 99) // 100


def decoder_source_fingerprint(source=None):
    """Canonical fingerprint of the exact decoder source inventory."""
    source = srcdir(source if source is not None else ROOT / 'src')
    files = source_hashes(source)
    if not files or 'Lpx4HybridCore.cpp' not in files:
        raise ValueError('Decoder source inventory is incomplete')
    return _sha(json.dumps(files, sort_keys=True, separators=(',', ':')).encode())


def quality_source_fingerprint():
    """Hash the bounded local import closure of parsing, synthesis and metrics.

    Walk imports without executing modules, including imports inside functions.
    This tools directory uses flat modules with static local import names.
    Bind the external numerical package versions and Python runtime as well.
    """
    files, pending = {}, ['standard_metrics', 'refine_speech_compact',
                          'speech_compact', 'q0_model']
    while pending:
        name = pending.pop()
        filename = name + '.py'
        if filename in files:
            continue
        data = (ROOT / 'tools' / filename).read_bytes()
        files[filename] = _sha(data)
        for node in ast.walk(ast.parse(data, filename=filename)):
            modules = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                       else [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            for module in modules:
                local = module.split('.')[0]
                if (ROOT / 'tools' / (local + '.py')).is_file():
                    pending.append(local)
    runtime = {'python':sys.version, **{name:version(name)
               for name in ('numpy','scipy','numba','pystoi')}}
    return _sha(json.dumps({'sources':files,'runtime':runtime},
                           sort_keys=True, separators=(',', ':')).encode())


def evaluation_fingerprint(row):
    """Bind a cached evaluation to its reference, ordered streams and metrics."""
    keys = ('id', 'reference_pcm16_sha256', 'samples', 'segment_samples', 'profiles',
            'quality_kind', 'stream_sha256', 'stream_bytes', 'output_pcm16_sha256',
            'output_pwm_sha256', 'metrics', 'quality_source_fingerprint',
            'decoder_source_fingerprint')
    value = {key: row[key] for key in keys}
    return _sha(json.dumps(value, sort_keys=True, separators=(',', ':'),
                           allow_nan=False).encode())


def validate_firmware_cost(cost, stream_hashes, stream_bytes,
                           expected_source_fingerprint=None):
    """Bind a locally collected full-image measurement to exact stream bytes.

    These fingerprints detect stale/mismatched local records; they are not a
    cryptographic attestation that a third-party measurement is trustworthy.
    Timing and board verification are separate from this size evidence.
    """
    if cost is None:
        return None
    if not isinstance(cost, dict) or cost.get('schema') != COST_SCHEMA:
        raise ValueError('Unsupported firmware cost schema')
    if cost.get('measurement') != 'linked-elf-text-plus-data':
        raise ValueError('Firmware cost must measure complete linked .text + .data')
    if cost.get('complete_image') is not True or cost.get('embedded_streams_exact') is not True:
        raise ValueError('Complete image and exact embedded streams must be verified')
    if cost.get('stream_sha256') != list(stream_hashes) or cost.get('stream_bytes') != stream_bytes:
        raise ValueError('Firmware cost belongs to different ordered streams')
    flash = _integer(cost.get('flash_bytes'), 'flash_bytes', 1)
    program = _integer(cost.get('program_flash_bytes'), 'program_flash_bytes')
    if flash < stream_bytes or program != flash - stream_bytes:
        raise ValueError('Firmware cost does not account for complete embedded streams')
    for key in ('source_fingerprint', 'build_fingerprint', 'image_sha256'):
        _hash(cost.get(key), key)
    if cost.get('image_kind', 'elf') not in ('elf', 'binary'):
        raise ValueError('image_kind must be elf or binary')
    source = (expected_source_fingerprint if expected_source_fingerprint is not None
              else decoder_source_fingerprint())
    _hash(source, 'expected_source_fingerprint')
    if cost['source_fingerprint'] != source:
        raise ValueError('Firmware cost uses a different decoder source inventory')
    return dict(cost)


def _evaluate_candidate(reference, streams, decoder, candidate_id, *, context, firmware=None,
                        speech=True, expected_source_fingerprint=None):
    """Recompute whole-recording quality from strict v5 decoding and reset joins."""
    ref = np.asarray(reference)
    if (ref.ndim != 1 or ref.dtype.kind not in 'iu' or not len(ref) or
            np.any(ref < -32768) or np.any(ref > 32767)):
        raise ValueError('Reference must be a nonempty mono PCM16 array')
    if not isinstance(candidate_id, str) or not candidate_id or len(candidate_id) > 128:
        raise ValueError('Candidate id must be a nonempty string of at most 128 characters')
    if not isinstance(streams, (list, tuple)) or not streams:
        raise ValueError('Candidate needs an ordered nonempty list of v5 streams')
    if not isinstance(speech, bool):
        raise ValueError('speech must be boolean')
    blobs, parts, lengths, profiles = [], [], [], []
    for blob in streams:
        if not isinstance(blob, (bytes, bytearray, memoryview)):
            raise ValueError('Each stream must be bytes')
        blob = bytes(blob)
        n, profile, *_ = unpack(blob)
        actual = decoder.decode_one_s16(blob, n)
        expected = decode_model(blob)
        if actual is None or not np.array_equal(actual, expected):
            raise AssertionError('Candidate native/model mismatch')
        if not np.array_equal(decoder.decode_one(blob, n), pwm_duties(expected)):
            raise AssertionError('Candidate native/PWM mismatch')
        blobs.append(blob); parts.append(expected); lengths.append(n); profiles.append(profile)
    pcm = np.concatenate(parts)
    if len(pcm) != len(ref):
        raise ValueError('Complete reset-chain length differs from original reference')
    if speech:
        measured = quality(ref, pcm)
    else:
        measured = {'pcm16': error_metrics(ref, pcm),
                    'pwm8': error_metrics(ref, pwm_pcm16(pcm))}
    hashes = [_sha(blob) for blob in blobs]
    size = sum(map(len, blobs))
    result = {'id': candidate_id, 'reference_pcm16_sha256': _sha(ref.astype('<i2').tobytes()),
            'samples': len(ref), 'segment_samples': lengths, 'profiles': profiles,
            'quality_kind': 'speech' if speech else 'non-speech-numerical',
            'stream_sha256': hashes, 'stream_bytes': size,
            'output_pcm16_sha256': _sha(pcm.astype('<i2').tobytes()),
            'output_pwm_sha256': _sha(pwm_duties(pcm).tobytes()), 'metrics': measured,
            'firmware': validate_firmware_cost(firmware, hashes, size,
                                               expected_source_fingerprint if expected_source_fingerprint
                                               is not None else context[0]),
            'quality_source_fingerprint': context[1],
            'decoder_source_fingerprint': context[0]}
    result['evaluation_fingerprint'] = evaluation_fingerprint(result)
    return result


def evaluate_candidate(reference, streams, decoder, candidate_id, *, firmware=None,
                       speech=True, expected_source_fingerprint=None):
    """Evaluate one candidate, taking fresh source fingerprints for this call."""
    context = (decoder_source_fingerprint(), quality_source_fingerprint())
    return _evaluate_candidate(reference, streams, decoder, candidate_id, context=context,
        firmware=firmware, speech=speech,
        expected_source_fingerprint=expected_source_fingerprint)


def evaluate(reference, candidates, decoder, *, speech=True,
             expected_source_fingerprint=None):
    """Decode and measure each candidate from its ordered complete v5 streams.

    No stored metrics are accepted as substitutes for decoding. Firmware cost
    may be unavailable for research candidates; selection keeps them separate.
    """
    if not isinstance(candidates, (list, tuple)) or not candidates:
        raise ValueError('No candidates to evaluate')
    context = (decoder_source_fingerprint(), quality_source_fingerprint())
    result, seen = [], set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError('Each candidate must be an object')
        identifier = candidate.get('id')
        if not isinstance(identifier, str) or identifier in seen:
            raise ValueError('Candidate ids must be unique strings')
        seen.add(identifier)
        result.append(_evaluate_candidate(reference, candidate.get('streams'), decoder,
            identifier, context=context, firmware=candidate.get('firmware'), speech=speech,
            expected_source_fingerprint=expected_source_fingerprint))
    return result


def _validate_record(row, source, quality_source):
    if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id']:
        raise ValueError('Evaluation needs a candidate id')
    _hash(row.get('reference_pcm16_sha256'), 'reference_pcm16_sha256')
    _hash(row.get('output_pcm16_sha256'), 'output_pcm16_sha256')
    _hash(row.get('output_pwm_sha256'), 'output_pwm_sha256')
    _integer(row.get('samples'), 'samples', 1)
    lengths = row.get('segment_samples')
    hashes = row.get('stream_sha256')
    if (not isinstance(lengths, list) or not lengths or not isinstance(hashes, list) or
            len(lengths) != len(hashes)):
        raise ValueError('Evaluation needs complete ordered segment geometry and hashes')
    for n in lengths:
        if _integer(n, 'segment_samples', 1) > 64000:
            raise ValueError('v5 segment exceeds 64000 samples')
    if sum(lengths) != row['samples']:
        raise ValueError('Evaluation segment lengths do not preserve the recording')
    for value in hashes:
        _hash(value, 'stream_sha256')
    _integer(row.get('stream_bytes'), 'stream_bytes', 22 * len(lengths))
    if row.get('quality_kind') not in ('speech', 'non-speech-numerical'):
        raise ValueError('Unknown evaluation quality kind')
    profiles = row.get('profiles')
    if (not isinstance(profiles, list) or len(profiles) != len(lengths) or
            any(type(p) is not int or p not in (4, 6) for p in profiles)):
        raise ValueError('Evaluation needs one v5 profile per segment')
    for domain in ('pcm16', 'pwm8'):
        metrics = row.get('metrics', {})
        if not isinstance(metrics, dict) or not isinstance(metrics.get(domain), dict):
            raise ValueError('Evaluation needs PCM/PWM metric objects')
        metrics = metrics[domain]
        if 'stoi' not in metrics:
            raise ValueError('Evaluation needs an explicit STOI value or null')
        sse, stoi = metrics.get('error_energy'), metrics.get('stoi')
        if (isinstance(sse, bool) or not isinstance(sse, (int, float)) or
                not math.isfinite(sse) or sse < 0 or type(metrics.get('samples')) is not int or
                metrics['samples'] != row['samples']):
            raise ValueError('Evaluation needs finite full-reference PCM/PWM SSE')
        if stoi is not None and (isinstance(stoi, bool) or
                                not isinstance(stoi, (int, float)) or not math.isfinite(stoi)):
            raise ValueError('Unavailable STOI must be null; valid STOI must be finite')
    if row.get('decoder_source_fingerprint') != source:
        raise ValueError('Evaluation uses a stale decoder source inventory')
    if row.get('quality_source_fingerprint') != quality_source:
        raise ValueError('Evaluation uses a stale quality implementation')
    if row.get('evaluation_fingerprint') != evaluation_fingerprint(row):
        raise ValueError('Evaluation fingerprint is stale or mismatched')
    return validate_firmware_cost(row.get('firmware'), hashes, row['stream_bytes'], source)


def _dominates(a, b):
    """Strict cost/metric dominance; unavailable STOI stays incomparable."""
    ca, cb = a['firmware']['flash_bytes'], b['firmware']['flash_bytes']
    if ca > cb:
        return False
    left, right = [], []
    for domain in ('pcm16', 'pwm8'):
        x, y = a['metrics'][domain], b['metrics'][domain]
        left.append(x['error_energy']); right.append(y['error_energy'])
        if (x['stoi'] is None) != (y['stoi'] is None):
            return False
        if x['stoi'] is not None:
            left.append(-x['stoi']); right.append(-y['stoi'])
    return (all(x <= y + TOLERANCE for x, y in zip(left, right)) and
            (ca < cb or any(x < y - TOLERANCE for x, y in zip(left, right))))


def _rank(row):
    return (row['metrics']['pcm16']['error_energy'], row['metrics']['pwm8']['error_energy'],
            row['firmware']['flash_bytes'], row['stream_bytes'], row['id'])


def _proxy(candidate, anchor, min_stoi_gain, min_ser_gain_db):
    stoi_gains, ser_gains = [], []
    for domain in ('pcm16', 'pwm8'):
        new, old = candidate['metrics'][domain], anchor['metrics'][domain]
        stoi_gains.append(None if old['stoi'] is None or new['stoi'] is None
                          else new['stoi'] - old['stoi'])
        a, b = old['error_energy'], new['error_energy']
        ser_gains.append(math.inf if a > 0 and b == 0 else
                         10 * math.log10(a / b) if a > 0 and b > 0 else 0.0)
    stoi_pass = (min_stoi_gain is not None and all(g is not None and g + TOLERANCE >= min_stoi_gain
                                                for g in stoi_gains))
    ser_pass = (min_ser_gain_db is not None and all(g + TOLERANCE >= min_ser_gain_db
                                                 for g in ser_gains))
    # Growth recommendations always preserve the best no-growth result's four floors.
    passed = no_regression(candidate['metrics'], anchor['metrics']) and (stoi_pass or ser_pass)
    return {'passed': bool(passed), 'stoi_gains': stoi_gains,
            'ser_gains_db': [v if math.isfinite(v) else None for v in ser_gains],
            'ser_perfect_output': [math.isinf(v) for v in ser_gains],
            'stoi_threshold_passed': bool(stoi_pass), 'ser_threshold_passed': bool(ser_pass)}


def select(candidates, baseline_id, max_flash_bytes, *, growth_policy='review',
           max_flash_growth_percent=10, min_stoi_gain=0.005, min_ser_gain_db=0.25,
           expected_source_fingerprint=None):
    """Choose a budget from fresh evaluations and verified complete-image cost.

    Default 'review' adopts only no-growth images and lists all feasible measured
    Pareto growth options for listening. Explicit 'metric-proxy' may recommend a
    larger image if either configured threshold passes in both output domains.
    Neither policy claims that numerical significance establishes audibility.
    """
    _integer(max_flash_bytes, 'max_flash_bytes', 1)
    _integer(max_flash_growth_percent, 'max_flash_growth_percent')
    if growth_policy not in ('review', 'metric-proxy'):
        raise ValueError('growth_policy must be review or metric-proxy')
    for name, value in (('min_stoi_gain', min_stoi_gain), ('min_ser_gain_db', min_ser_gain_db)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or
                                  not math.isfinite(value) or value <= 0):
            raise ValueError(name + ' must be positive and finite, or null')
    if growth_policy == 'metric-proxy' and min_stoi_gain is None and min_ser_gain_db is None:
        raise ValueError('Metric-proxy growth requires a numerical significance threshold')
    if not isinstance(candidates, (list, tuple)) or not candidates:
        raise ValueError('No candidate evaluations')
    source = (decoder_source_fingerprint() if expected_source_fingerprint is None
              else _hash(expected_source_fingerprint, 'expected_source_fingerprint'))
    if not isinstance(baseline_id, str) or not baseline_id:
        raise ValueError('baseline_id must be a nonempty string')
    quality_source = quality_source_fingerprint()
    by_id, costs = {}, {}
    for row in candidates:
        if not isinstance(row, dict):
            raise ValueError('Each evaluation must be an object')
        cost = _validate_record(row, source, quality_source)
        if row['id'] in by_id:
            raise ValueError('Duplicate candidate id')
        costs[row['id']] = cost
        by_id[row['id']] = row
    if baseline_id not in by_id or costs[baseline_id] is None:
        raise ValueError('Baseline requires a matching measured complete-image cost')
    baseline = by_id[baseline_id]; baseline_cost = costs[baseline_id]
    geometry = (baseline['reference_pcm16_sha256'], baseline['samples'],
                baseline['segment_samples'], baseline.get('quality_kind'))
    for row in candidates:
        if (row['reference_pcm16_sha256'], row['samples'], row['segment_samples'],
                row.get('quality_kind')) != geometry:
            raise ValueError('Candidates must share original reference and reset geometry')
        cost = costs[row['id']]
        if cost is not None and cost['build_fingerprint'] != baseline_cost['build_fingerprint']:
            raise ValueError('Candidates use incompatible build/toolchain/harness fingerprints')
    # A hard growth limit rounds downward, so the full-image percentage is never exceeded.
    growth_limit = baseline_cost['flash_bytes'] * (100 + max_flash_growth_percent) // 100
    allowed_limit = min(max_flash_bytes, growth_limit)
    measured = [r for r in candidates if costs[r['id']] is not None]
    feasible = [r for r in measured if r['firmware']['flash_bytes'] <= allowed_limit]
    frontier = [r for r in feasible if not any(_dominates(x, r) for x in feasible)]
    safe = [r for r in feasible if no_regression(r['metrics'], baseline['metrics'])]
    no_growth = [r for r in safe if r in frontier and
                 r['firmware']['flash_bytes'] <= baseline_cost['flash_bytes']]
    anchor = min(no_growth, key=_rank) if no_growth else None
    chosen = anchor
    proxy = {r['id']: _proxy(r, anchor, min_stoi_gain, min_ser_gain_db)
             for r in frontier if anchor is not None and
             r['firmware']['flash_bytes'] > anchor['firmware']['flash_bytes']}
    if growth_policy == 'metric-proxy' and anchor is not None:
        recommended = [r for r in frontier if r['id'] in proxy and proxy[r['id']]['passed']]
        if recommended:
            chosen = min([anchor, *recommended], key=_rank)
    alternatives = []
    for row in candidates:
        cost = costs[row['id']]
        alternatives.append({'id': row['id'], 'stream_bytes': row['stream_bytes'],
            'full_flash_bytes': None if cost is None else cost['flash_bytes'],
            'within_hard_flash_limit': None if cost is None else cost['flash_bytes'] <= max_flash_bytes,
            'within_full_image_growth_limit': None if cost is None else cost['flash_bytes'] <= growth_limit,
            'four_baseline_floors_passed': no_regression(row['metrics'], baseline['metrics']),
            'measured_pareto_frontier': row in frontier,
            'dominated_by': [] if cost is None else [x['id'] for x in feasible if _dominates(x, row)],
            'metric_proxy_vs_no_growth': proxy.get(row['id'])})
    return {'schema': 'lpx-v5-budget-selection-v1', 'baseline_id': baseline_id,
            'selected_id': None if chosen is None else chosen['id'],
            'selection_status': 'no-feasible-candidate' if chosen is None else 'selected',
            'no_growth_id': None if anchor is None else anchor['id'],
            'selected_flash_bytes': None if chosen is None else chosen['firmware']['flash_bytes'],
            'selected_stream_bytes': None if chosen is None else chosen['stream_bytes'],
            'hard_flash_limit': max_flash_bytes, 'full_image_growth_limit': growth_limit,
            'growth_policy': growth_policy, 'max_flash_growth_percent': max_flash_growth_percent,
            'metric_thresholds': {'min_stoi_gain': min_stoi_gain, 'min_ser_gain_db': min_ser_gain_db,
                                  'rule': 'Either threshold in both PCM/PWM domains, with four floors.'},
            'human_listening_confirmation_collected': False,
            'timing_admission_inferred_from_flash': False,
            'growth_listening_ids': [r['id'] for r in sorted(frontier, key=lambda r:
                (r['firmware']['flash_bytes'], _rank(r)))
                if r['firmware']['flash_bytes'] > baseline_cost['flash_bytes']],
            'measured_frontier_ids': [r['id'] for r in frontier],
            'unknown_firmware_ids': [r['id'] for r in candidates if costs[r['id']] is None],
            'alternatives': alternatives}


def main():
    """Input schema: lpx-v5-budget-input-v1, baseline_id and candidates.

    Each candidate has id, segments=[{path,sha256}], and optional firmware cost.
    Segment paths are relative to the manifest; report/evaluations contain no
    source paths. The output directory must be empty to avoid stale selections.
    """
    import soundfile as sf
    from batch_decoder import BatchSession
    from output_paths import protect_outputs
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path); parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--max-flash-bytes', type=int, required=True)
    parser.add_argument('--growth-policy', choices=('review', 'metric-proxy'), default='review')
    parser.add_argument('--max-flash-growth-percent', type=int, default=10)
    parser.add_argument('--min-stoi-gain', type=float, default=.005)
    parser.add_argument('--min-ser-gain-db', type=float, default=.25)
    parser.add_argument('--non-speech', action='store_true')
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text(encoding='utf-8'))
    if data.get('schema') != 'lpx-v5-budget-input-v1' or not isinstance(data.get('candidates'), list):
        raise ValueError('Unsupported budget input schema')
    sources = [args.reference, args.manifest]; loaded = []
    for item in data['candidates']:
        blobs = []
        for segment in item['segments']:
            path = args.manifest.parent / segment['path']; blob = path.read_bytes()
            if _sha(blob) != _hash(segment['sha256'], 'segment.sha256'):
                raise ValueError('Input candidate stream hash changed')
            sources.append(path); blobs.append(blob)
        loaded.append((item, blobs))
    if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
        raise ValueError('Output directory must be absent or empty')
    ref, rate = sf.read(args.reference, dtype='int16')
    if rate != 8000:
        raise ValueError('Reference must be 8kHz')
    with BatchSession('batch', speech=True, speech_compact=True, compact_only=True) as decoder:
        evaluated = evaluate(ref, [{'id': item['id'], 'streams': blobs,
            'firmware': item.get('firmware')} for item, blobs in loaded], decoder,
            speech=not args.non_speech)
    report = select(evaluated, data['baseline_id'], args.max_flash_bytes,
                    growth_policy=args.growth_policy,
                    max_flash_growth_percent=args.max_flash_growth_percent,
                    min_stoi_gain=args.min_stoi_gain, min_ser_gain_db=args.min_ser_gain_db)
    report['evaluations'] = evaluated
    report['input_manifest_sha256'] = _sha(args.manifest.read_bytes())
    chosen = next(((item, blobs) for item, blobs in loaded if item['id'] == report['selected_id']), None)
    targets = [args.output / 'selection.json']
    if chosen is not None:
        targets += [args.output / f'segment-{i:03d}.l4hy' for i in range(len(chosen[1]))]
        targets += [args.output / 'decoded.wav']
    protect_outputs(sources, targets)
    args.output.mkdir(parents=True, exist_ok=True)
    if chosen is not None:
        for path, blob in zip(targets[1:-1], chosen[1]):
            path.write_bytes(blob)
        pcm = np.concatenate([decode_model(blob) for blob in chosen[1]])
        sf.write(targets[-1], pcm, 8000, subtype='PCM_16')
    targets[0].write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in
          ('selected_id', 'selected_flash_bytes', 'growth_policy', 'growth_listening_ids')}))


if __name__ == '__main__':
    main()

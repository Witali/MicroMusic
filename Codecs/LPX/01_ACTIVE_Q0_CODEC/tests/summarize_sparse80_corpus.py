"""Export anonymous whole-record sparse80 numerical evidence (stdlib only).

Input media, paths, names and media fingerprints are private. The output uses
an explicit field allowlist and never serializes an input object wholesale.
Numerical proxies do not establish audibility or listening preference.
"""
from __future__ import annotations

import argparse
from array import array
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import wave


COHORTS = ('speech', 'regression', 'independent', 'phrases', 'music', 'instruments')
KINDS = ('speech', 'music')
SPLITS = ('tuning', 'evaluation', 'non_speech', 'additional')
DOMAINS = ('pcm16', 'pwm8')
EPSILON = 1e-12
CODE_PATHS = (
    'tools/encode_low_bitrate_speech.py', 'tools/refine_speech_compact.py',
    'tools/refine_sparse80.py', 'tools/enhance_sparse80.py',
    'tools/standard_metrics.py', 'tools/voice_character.py',
    'tools/speech_voice_objective.py', 'tools/speech_noise_objective.py',
    'tools/speech_sparse80.py', 'tools/speech_v9.py',
    'src/Lpx4HybridCore.cpp', 'src/Lpx4HybridCore.h',
)


class StudyError(ValueError):
    """A sanitized diagnostic, containing no input paths or private values."""


@dataclass(frozen=True)
class StudyContract:
    records: int
    samples: int
    segments: int
    kinds: tuple[tuple[str, int], ...]
    splits: tuple[tuple[str, int], ...]
    cohorts: tuple[tuple[str, int], ...]


PRODUCTION = StudyContract(
    181, 15_188_029, 306,
    (('speech', 49), ('music', 132)),
    (('tuning', 20), ('evaluation', 20), ('non_speech', 132), ('additional', 9)),
    (('speech', 20), ('regression', 27), ('independent', 4),
     ('phrases', 5), ('music', 3), ('instruments', 122)),
)


def require(condition, message):
    if not condition:
        raise StudyError(message)


def integer(value, label, minimum=0):
    require(type(value) is int and value >= minimum, 'Invalid ' + label)
    return value


def number(value, label, minimum=0):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and value >= minimum
    except OverflowError:
        valid = False
    require(valid, 'Invalid ' + label)
    return value


def nullable_number(value, label, minimum=0):
    return None if value is None else number(value, label, minimum)


def load(path, label):
    try:
        result = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError):
        raise StudyError('Missing or invalid ' + label) from None
    require(isinstance(result, dict), 'Invalid ' + label)
    return result


def read_wav(path, samples, label, *, hardware=False):
    try:
        with wave.open(str(path), 'rb') as stream:
            geometry = (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(),
                        stream.getnframes(), stream.getcomptype())
            require(geometry == (1, 2, 8000, samples, 'NONE'), 'Invalid ' + label + ' geometry')
            raw = stream.readframes(samples + 1)
    except (OSError, EOFError, wave.Error):
        raise StudyError('Missing or invalid ' + label) from None
    require(len(raw) == samples * 2, 'Truncated ' + label)
    values = array('h')
    values.frombytes(raw)
    if sys.byteorder != 'little':
        values.byteswap()
    if hardware:
        require(all(-32768 <= value <= 32512 and value % 256 == 0 for value in values),
                label + ' is not an exact PWM-domain PCM16 mapping')
    return values, raw


def ser(reference_energy, error_energy, *, assessed=True):
    if not assessed:
        return {'ser_db': None, 'ser_status': 'unassessed'}
    if error_energy == 0:
        return {'ser_db': None, 'ser_status': 'perfect'}
    if reference_energy == 0:
        return {'ser_db': None, 'ser_status': 'zero_reference'}
    return {'ser_db': 10 * (math.log10(reference_energy) - math.log10(error_energy)),
            'ser_status': 'finite'}


def ser_gain(before, after):
    if before['reference_energy'] == 0 or before['error_energy'] == 0:
        return {'db': None, 'status': 'unassessed', 'at_least_0_1_db': False}
    if after['error_energy'] == 0:
        return {'db': None, 'status': 'improved_to_perfect', 'at_least_0_1_db': True}
    gain = 10 * (math.log10(before['error_energy']) - math.log10(after['error_energy']))
    return {'db': gain, 'status': 'finite', 'at_least_0_1_db': gain >= .1 - EPSILON}


def checked_manifest(path, contract):
    manifest = load(path, 'corpus manifest')
    require(manifest.get('schema') == 'lpx-shared-corpus-v1' and manifest.get('sample_rate') == 8000,
            'Invalid corpus manifest schema or rate')
    cases = manifest.get('cases')
    require(isinstance(cases, list) and len(cases) == contract.records, 'Corpus record count differs')
    identities = set()
    fingerprints = set()
    for ordinal, case in enumerate(cases):
        label = 'record ' + str(ordinal)
        require(isinstance(case, dict), 'Invalid ' + label)
        for key, vocabulary in (('cohort', COHORTS), ('kind', KINDS), ('split', SPLITS)):
            require(case.get(key) in vocabulary, 'Unknown ' + key + ' in ' + label)
        identity, fingerprint = case.get('id'), case.get('reference_pcm16_sha256')
        require(isinstance(identity, str) and identity and identity not in identities,
                'Invalid or duplicate identity in ' + label)
        require(isinstance(fingerprint, str) and len(fingerprint) == 64
                and all(c in '0123456789abcdef' for c in fingerprint)
                and fingerprint not in fingerprints, 'Invalid or duplicate source binding in ' + label)
        identities.add(identity)
        fingerprints.add(fingerprint)
        n = integer(case.get('samples'), label + ' samples', 1)
        segments = case.get('segments')
        require(isinstance(segments, list) and segments, 'Missing segments in ' + label)
        offset = 0
        for index, segment in enumerate(segments):
            require(isinstance(segment, dict) and type(segment.get('index')) is int
                    and segment['index'] == index and type(segment.get('start')) is int
                    and segment['start'] == offset, 'Noncontiguous segments in ' + label)
            length = integer(segment.get('samples'), label + ' segment samples', 1)
            require(length <= 64000, 'Oversized segment in ' + label)
            offset += length
        require(offset == n, 'Segment duration differs in ' + label)
    require(sum(c['samples'] for c in cases) == contract.samples, 'Corpus sample total differs')
    require(sum(len(c['segments']) for c in cases) == contract.segments, 'Corpus segment total differs')
    for key, expected in (('kind', contract.kinds), ('split', contract.splits), ('cohort', contract.cohorts)):
        require(Counter(c[key] for c in cases) == Counter(dict(expected)), 'Corpus ' + key + ' totals differ')
    return cases


def reference_path(manifest_path, case, label):
    relative = case.get('reference')
    require(isinstance(relative, str) and relative, 'Missing reference in ' + label)
    root = manifest_path.parent.resolve()
    path = (root / relative).resolve()
    require(path.is_relative_to(root) and path != root, 'Reference leaves corpus storage in ' + label)
    return path


def stream_bytes(path, samples, label):
    try:
        data = path.read_bytes()
    except OSError:
        raise StudyError('Missing ' + label) from None
    require(13 <= len(data) <= 65535, 'Invalid ' + label + ' length')
    magic, profile, rate, count, pre, bright, payload = struct.unpack('<2sBHHHHH', data[:13])
    require((magic, profile, rate, count) == (b'L9', 15, 8000, samples)
            and pre <= 16384 and bright <= 11469 and payload == len(data) - 13,
            'Invalid ' + label + ' v9 header')
    return data


def metrics(raw, n, reference_energy, label):
    require(isinstance(raw, dict), 'Invalid ' + label)
    require('stoi' in raw, 'Missing STOI assessment in ' + label)
    require(raw.get('samples') == n, 'Metric sample count differs in ' + label)
    energy = number(raw.get('reference_energy'), label + ' reference energy')
    error = number(raw.get('error_energy'), label + ' error energy')
    require(energy == float(reference_energy) and error <= n * 65535**2,
            'Metric energy differs in ' + label)
    stoi = nullable_number(raw.get('stoi'), label + ' STOI', -1)
    require(stoi is None or stoi <= 1 + EPSILON, 'Invalid STOI range in ' + label)
    return {'samples': n, 'reference_energy': reference_energy, 'error_energy': error,
            **ser(reference_energy, error), 'stoi': stoi}


def voice(raw, n, label):
    require(isinstance(raw, dict), 'Invalid ' + label)
    keys = ('frames', 'active_reference_frames', 'reference_period_frames',
            'within_tolerance_frames', 'missing_decoded_period_frames', 'decoded_collapsed_active_frames')
    out = {key: integer(raw.get(key), label + ' ' + key) for key in keys}
    require(out['frames'] <= n and out['active_reference_frames'] <= out['frames']
            and out['reference_period_frames'] <= out['frames']
            and out['within_tolerance_frames'] <= out['reference_period_frames']
            and out['missing_decoded_period_frames'] <= out['reference_period_frames']
            and out['decoded_collapsed_active_frames'] <= out['active_reference_frames'],
            'Inconsistent frame counts in ' + label)
    for key in ('fixed_source_period_error_mean', 'fixed_decoded_period_error_mean',
                'relative_spectral_shape_rms_db_mean'):
        require(key in raw, 'Missing voice assessment in ' + label)
        out[key] = nullable_number(raw.get(key), label + ' ' + key)
    for key in ('fixed_source_period_error_mean', 'fixed_decoded_period_error_mean'):
        require((out[key] is None) == (out['reference_period_frames'] == 0)
                and (out[key] is None or out[key] <= 2 + EPSILON), 'Invalid period error in ' + label)
    return out


def state(raw, reference, pwm, n, label):
    require(isinstance(raw, dict), 'Invalid ' + label)
    source_energy = sum(value * value for value in reference)
    raw_metrics = raw.get('metrics')
    require(isinstance(raw_metrics, dict), 'Missing metrics in ' + label)
    out = {'metrics': {d: metrics(raw_metrics.get(d), n, source_energy, label + ' ' + d) for d in DOMAINS}}
    pwm_error = sum((a - b)**2 for a, b in zip(reference, pwm))
    require(out['metrics']['pwm8']['error_energy'] == float(pwm_error),
            'PWM error energy does not match WAV data in ' + label)
    out['metrics']['pwm8']['error_energy'] = pwm_error
    out['metrics']['pwm8'].update(ser(source_energy, pwm_error))
    values = raw.get('voice')
    require(isinstance(values, list) and len(values) == 2, 'Missing voice domains in ' + label)
    out['voice'] = {d: voice(values[i], n, label + ' ' + d) for i, d in enumerate(DOMAINS)}
    clipped = raw.get('clipped')
    require(isinstance(clipped, list) and len(clipped) == 2, 'Missing clipping counts in ' + label)
    out['clipped'] = {d: integer(clipped[i], label + ' clipping') for i, d in enumerate(DOMAINS)}
    require(all(v <= n for v in out['clipped'].values()), 'Invalid clipping count in ' + label)
    require(out['clipped']['pwm8'] == sum(v in (-32768, 32512) for v in pwm),
            'PWM clipping count does not match WAV data in ' + label)
    out['joint_proxy'] = number(raw.get('score'), label + ' joint score')
    return out


def floors(before, after, label):
    require(after['joint_proxy'] <= before['joint_proxy'] + EPSILON, 'Joint proxy regressed in ' + label)
    for domain in DOMAINS:
        a, b = before['metrics'][domain], after['metrics'][domain]
        require(b['error_energy'] <= a['error_energy'], 'SSE regressed in ' + label + ' ' + domain)
        require(a['stoi'] is None or b['stoi'] is not None and b['stoi'] >= a['stoi'] - EPSILON,
                'STOI regressed or became unavailable in ' + label + ' ' + domain)
        a, b = before['voice'][domain], after['voice'][domain]
        for key in ('frames', 'active_reference_frames', 'reference_period_frames', 'fixed_source_period_error_mean'):
            require(a[key] == b[key], 'Source frame membership changed in ' + label)
        require(b['within_tolerance_frames'] >= a['within_tolerance_frames']
                and b['decoded_collapsed_active_frames'] <= a['decoded_collapsed_active_frames'],
                'Period coverage or collapse regressed in ' + label + ' ' + domain)
        old, new = a['fixed_decoded_period_error_mean'], b['fixed_decoded_period_error_mean']
        require(old is None or new is not None and new <= old + EPSILON,
                'Fixed-period error regressed in ' + label + ' ' + domain)
        require(after['clipped'][domain] <= before['clipped'][domain],
                'Clipping regressed in ' + label + ' ' + domain)


def record(ordinal, case, folder, manifest_path):
    label = 'record ' + str(ordinal)
    raw = load(folder / 'result-private.json', label + ' receipt')
    n = case['samples']
    require(type(raw.get('number')) is int and raw['number'] == ordinal and raw.get('samples') == n
            and raw.get('segments') == len(case['segments'])
            and raw.get('cohort') == case['cohort'] and raw.get('kind') == case['kind'],
            'Receipt metadata differs in ' + label)
    changed = raw.get('changed')
    guarded = raw.get('whole_record_gate_passed')
    require(type(changed) is bool and type(guarded) is bool, 'Missing outcome flags in ' + label)
    declared_segments = integer(raw.get('changed_segments'), label + ' changed segments')
    require(declared_segments <= len(case['segments']), 'Invalid changed segment count in ' + label)
    before_bytes = after_bytes = changed_streams = 0
    for segment in case['segments']:
        directory = folder / ('segment-%03d' % segment['index'])
        old = stream_bytes(directory / 'baseline-v9.lpx', segment['samples'], label + ' baseline stream')
        new = stream_bytes(directory / 'candidate-v9.lpx', segment['samples'], label + ' selected stream')
        require(len(new) <= len(old), 'Compressed data grew in ' + label)
        before_bytes += len(old)
        after_bytes += len(new)
        changed_streams += old != new
    require(raw.get('bytes') == before_bytes and raw.get('selected_bytes') == after_bytes,
            'Reported file bytes differ from actual streams in ' + label)
    require(changed_streams <= declared_segments and (not changed or changed_streams > 0),
            'Stream changes disagree with outcome in ' + label)
    reference, source_raw = read_wav(reference_path(manifest_path, case, label), n, label + ' reference WAV')
    require(hashlib.sha256(source_raw).hexdigest() == case['reference_pcm16_sha256'],
            'Reference binding differs in ' + label)
    old, old_raw = read_wav(folder / 'baseline.wav', n, label + ' baseline WAV', hardware=True)
    new, new_raw = read_wav(folder / 'selected.wav', n, label + ' selected WAV', hardware=True)
    pwm_changed = old_raw != new_raw
    require(not pwm_changed or changed, 'PWM changed without a reported PCM change in ' + label)
    before = state(raw.get('baseline'), reference, old, n, label + ' baseline')
    after = state(raw.get('selected'), reference, new, n, label + ' selected')
    floors(before, after, label)
    if not changed:
        require(before == after, 'Unchanged PCM has differing metrics in ' + label)
    if not guarded:
        require(not changed and not pwm_changed and not declared_segments and not changed_streams
                and before == after, 'Whole-record fallback is inconsistent in ' + label)
    gain = ser_gain(before['metrics']['pwm8'], after['metrics']['pwm8'])
    old_stoi, new_stoi = before['metrics']['pwm8']['stoi'], after['metrics']['pwm8']['stoi']
    stoi_gain = None if old_stoi is None else new_stoi - old_stoi
    material = pwm_changed and (gain['at_least_0_1_db'] or stoi_gain is not None and stoi_gain >= .005 - EPSILON)
    reduction = None if before['joint_proxy'] == 0 else (before['joint_proxy'] - after['joint_proxy']) / before['joint_proxy']
    if reduction is not None and not math.isfinite(reduction):
        reduction = None
    joint = reduction is not None and reduction >= .01 - EPSILON
    return {
        'ordinal': ordinal, 'cohort': case['cohort'], 'kind': case['kind'], 'split': case['split'],
        'samples': n, 'segments': len(case['segments']), 'baseline_bytes': before_bytes,
        'selected_bytes': after_bytes, 'whole_record_guard_passed': guarded, 'fallback': not guarded,
        'reported_pcm_changed': changed, 'stream_changed_segments': changed_streams,
        'pwm_changed': pwm_changed, 'pwm_changed_samples': sum(a != b for a, b in zip(old, new)) if pwm_changed else 0,
        'material_pwm_proxy_change': bool(material), 'pwm_ser_gain': gain, 'pwm_stoi_gain': stoi_gain,
        'joint_proxy_reduction_fraction': reduction, 'joint_proxy_one_percent': bool(joint),
        'baseline': before, 'selected': after,
    }


def aggregate(rows, expected, *, eligible):
    count = len(rows)
    out = {
        'records': count, 'expected_records': expected, 'samples': sum(r['samples'] for r in rows),
        'segments': sum(r['segments'] for r in rows),
        'baseline_bytes': sum(r['baseline_bytes'] for r in rows),
        'selected_bytes': sum(r['selected_bytes'] for r in rows),
        'fallback_records': sum(r['fallback'] for r in rows),
        'selected_floor_regression_records': 0,
        'reported_pcm_changed_records': sum(r['reported_pcm_changed'] for r in rows),
        'any_pwm_change_records': sum(r['pwm_changed'] for r in rows),
        'material_pwm_proxy_records': sum(r['material_pwm_proxy_change'] for r in rows),
        'joint_proxy_one_percent_records': sum(r['joint_proxy_one_percent'] for r in rows),
        'pwm_changed_joint_proxy_one_percent_records': sum(r['pwm_changed'] and r['joint_proxy_one_percent'] for r in rows),
    }
    out['majority_eligible'] = bool(eligible and count == expected and count > 0)
    out['material_pwm_proxy_majority'] = (out['material_pwm_proxy_records'] * 2 > count) if out['majority_eligible'] else None
    out['perceived_quality_majority'] = None
    out['domains'] = {}
    for domain in DOMAINS:
        before = [r['baseline']['metrics'][domain] for r in rows]
        after = [r['selected']['metrics'][domain] for r in rows]
        power = sum(v['reference_energy'] for v in before)
        old_error = sum(v['error_energy'] for v in before)
        new_error = sum(v['error_energy'] for v in after)
        members = [i for i, value in enumerate(before) if value['stoi'] is not None]
        old_stoi = math.fsum(before[i]['stoi'] for i in members) / len(members) if members else None
        new_stoi = math.fsum(after[i]['stoi'] for i in members) / len(members) if members else None
        old_periods = [r['baseline']['voice'][domain] for r in rows]
        new_periods = [r['selected']['voice'][domain] for r in rows]
        denominator = sum(v['reference_period_frames'] for v in old_periods)
        old_within = sum(v['within_tolerance_frames'] for v in old_periods)
        new_within = sum(v['within_tolerance_frames'] for v in new_periods)
        out['domains'][domain] = {
            'reference_energy': power, 'baseline_error_energy': old_error, 'selected_error_energy': new_error,
            'baseline_ser': ser(power, old_error, assessed=bool(rows)),
            'selected_ser': ser(power, new_error, assessed=bool(rows)),
            'stoi_assessed_records': len(members), 'stoi_unassessed_records': count - len(members),
            'newly_available_stoi_records': sum(a['stoi'] is None and b['stoi'] is not None for a, b in zip(before, after)),
            'baseline_mean_stoi': old_stoi, 'selected_mean_stoi': new_stoi,
            'mean_stoi_delta': None if old_stoi is None else new_stoi - old_stoi,
            'source_period_frames': denominator, 'baseline_within_tolerance_frames': old_within,
            'selected_within_tolerance_frames': new_within,
            'baseline_period_coverage': old_within / denominator if denominator else None,
            'selected_period_coverage': new_within / denominator if denominator else None,
            'baseline_clipped_samples': sum(r['baseline']['clipped'][domain] for r in rows),
            'selected_clipped_samples': sum(r['selected']['clipped'][domain] for r in rows),
        }
    return out


def code_digests(snapshot):
    result = {'exporter': {'tests/summarize_sparse80_corpus.py': hashlib.sha256(
        Path(__file__).read_bytes().replace(b'\r\n', b'\n')).hexdigest()}, 'declared_quality_snapshot': {}}
    if snapshot is not None:
        for name in CODE_PATHS:
            path = Path(snapshot) / name
            try:
                data = path.read_bytes()
            except OSError:
                raise StudyError('Declared code snapshot is incomplete') from None
            result['declared_quality_snapshot'][name] = hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()
    return result


def summarize(manifest_path, result_root, *, allow_partial=False, code_snapshot=None, _contract=PRODUCTION):
    """Return an allowlisted report without writing any output file.

    The CLI always uses PRODUCTION. The explicit private contract argument is
    for small synthetic unit fixtures; it never enables a production majority.
    """
    manifest_path, result_root = Path(manifest_path), Path(result_root)
    cases = checked_manifest(manifest_path, _contract)
    rows = []
    missing = []
    for ordinal, case in enumerate(cases):
        folder = result_root / ('%03d' % ordinal)
        if not (folder / 'result-private.json').is_file():
            missing.append(ordinal)
        else:
            rows.append(record(ordinal, case, folder, manifest_path))
    if result_root.is_dir():
        for folder in result_root.iterdir():
            if folder.is_dir() and (folder / 'result-private.json').exists():
                require(folder.name.isdecimal() and folder.name == '%03d' % int(folder.name)
                        and int(folder.name) < len(cases), 'Unexpected completed record directory')
    require(allow_partial or not missing, 'Incomplete study: completed records are missing')
    complete = not missing
    eligible = complete and _contract == PRODUCTION
    result = {
        'schema': 'lpx-sparse80-whole-corpus-summary-v1', 'complete': complete,
        'mode': 'final' if complete else 'partial_diagnostic', 'sample_hz': 8000,
        'expected': {'records': _contract.records, 'samples': _contract.samples, 'segments': _contract.segments},
        'missing_ordinals': missing,
        'scope': ('Exploratory numerical comparison. The evaluation split is descriptive, not an independent '
                  'confirmatory heldout study: public examples and some corpus records informed pilots. '
                  'Proxy thresholds do not establish audibility or perceived quality.'),
        'subjective_validation': 'not_established',
        'policy': {'unit_of_vote': 'whole_recording', 'material_proxy_requires_changed_pwm': True,
                   'material_pwm_ser_gain_db': .1, 'material_pwm_stoi_gain': .005,
                   'joint_proxy_fraction': .01, 'stoi_membership': 'fixed_from_baseline',
                   'float_floor_and_threshold_tolerance': EPSILON,
                   'ser_aggregation': 'summed_reference_and_error_energy',
                   'pwm_evidence': 'Independent exact PWM-domain WAV comparison and recomputed SSE/clipping',
                   'pcm16_evidence': 'Reported native/model PCM16 metrics checked against numerical floors',
                   'upper_band_specific_floor': 'not_validated_by_this_exporter',
                   'majority_requires_complete_production_corpus': True},
        'code_source_sha256': code_digests(code_snapshot),
        'code_digest_scope': 'Exporter and optional caller-declared quality snapshot; not execution attestation.',
        'all': aggregate(rows, len(cases), eligible=eligible),
        'by_kind': {}, 'by_cohort': {}, 'by_split': {}, 'records': rows,
    }
    for key, output, vocabulary in (('kind', 'by_kind', KINDS), ('cohort', 'by_cohort', COHORTS), ('split', 'by_split', SPLITS)):
        for value in vocabulary:
            expected = sum(c[key] == value for c in cases)
            result[output][value] = aggregate([r for r in rows if r[key] == value], expected, eligible=eligible)
    json.dumps(result, allow_nan=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('results', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--allow-partial', action='store_true')
    parser.add_argument('--code-snapshot', type=Path)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), 'Output already exists; choose a new report file')
        report = summarize(args.manifest, args.results, allow_partial=args.allow_partial, code_snapshot=args.code_snapshot)
        payload = json.dumps(report, indent=2, allow_nan=False) + '\n'
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8', newline='\n') as output:
            output.write(payload)
    except StudyError as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps({'complete': report['complete'], 'records': report['all']['records'],
                      'any_pwm_change_records': report['all']['any_pwm_change_records'],
                      'material_pwm_proxy_records': report['all']['material_pwm_proxy_records']}))


if __name__ == '__main__':
    main()

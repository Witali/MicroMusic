"""Audit exact HQ4 arithmetic, WAV conversion and quantized flat peaks.

Repeated levels or flat observed extrema are measurements, not proof of clipping.
The independent hq4_phase auditor is used in frozen legacy-phase mode.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from model import decode
from hq4_phase import render, audit
from hq4_core import pack_stream, unpack_stream


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def runs(values):
    values = np.asarray(values)
    if not len(values):
        return np.array([], int), np.array([], int), values
    starts = np.r_[0, np.flatnonzero(values[1:] != values[:-1])+1]
    lengths = np.diff(np.r_[starts, len(values)])
    return starts, lengths, values[starts]


def extrema_runs(values, level):
    _, lengths, levels = runs(values)
    selected = lengths[levels == level]
    return dict(level=float(level), samples=int(np.count_nonzero(values == level)),
        maximum_equal_run=int(selected.max()) if len(selected) else 0,
        equal_runs_ge2=int(np.count_nonzero(selected >= 2)),
        samples_in_equal_runs_ge2=int(selected[selected >= 2].sum()))


def signal_stats(values):
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or not len(values) or not np.all(np.isfinite(values)):
        raise ValueError('Audit requires finite nonempty mono samples')
    starts, lengths, levels = runs(values)
    positive = negative = 0
    for start, length, level in zip(starts, lengths, levels):
        end = start+length
        if length < 2 or not start or end == len(values):
            continue
        positive += int(level > 0 and values[start-1] < level and values[end] < level)
        negative += int(level < 0 and values[start-1] > level and values[end] > level)
    unique, counts = np.unique(values, return_counts=True)
    common = np.lexsort((unique, -counts))[:8]
    rms = float(np.sqrt(np.mean(values*values)))
    return dict(samples=len(values), minimum=float(values.min()), maximum=float(values.max()),
        peak=float(abs(values).max()), mean=float(values.mean()), rms=rms,
        unique_levels=len(unique), samples_outside_unit_interval=int(np.count_nonzero(abs(values) > 1)),
        samples_abs_ge_one=int(np.count_nonzero(abs(values) >= 1)),
        maximum_equal_run=int(lengths.max()), equal_neighbor_fraction=float(np.mean(values[1:] == values[:-1])) if len(values) > 1 else 0.,
        local_positive_plateaus_ge2=positive, local_negative_plateaus_ge2=negative,
        observed_minimum=extrema_runs(values, values.min()), observed_maximum=extrema_runs(values, values.max()),
        most_common_levels=[dict(level=float(unique[i]), samples=int(counts[i])) for i in common])


def audit_model(model_path, entry, reference_root):
    model_path = Path(model_path)
    model = json.loads(model_path.read_text(encoding='utf-8'))
    if model['schema'] != 'hq4-corpus-baseline-v1' or model['reference_sha256'] != entry['reference_sha256']:
        raise ValueError('Model does not identify the frozen corpus reference')
    frames, durations = np.asarray(model['frames'], np.uint8), np.asarray(model['durations'], np.uint16)
    pcm, excitation, pulses, boundaries, _ = render(frames, durations, False)
    if not np.array_equal(pcm, decode(frames, durations, 0)):
        raise AssertionError('Independent legacy arithmetic auditor differs from the frozen HQ4 oracle')
    payload = (model_path.parent/'speech.hq').read_bytes()
    packed_frames, packed_durations = unpack_stream(payload)
    if payload != pack_stream(frames, durations) or not np.array_equal(pcm, decode(packed_frames, packed_durations, 0)):
        raise AssertionError('Packed stream changed frozen-model output')
    if (model_path.parent/'expected.raw').read_bytes() != pcm.tobytes():
        raise AssertionError('Expected raw bytes differ from the exact decoder')
    if ('stream_sha256' in model and model['stream_sha256'] != hashlib.sha256(payload).hexdigest()) or (
            'pcm_u8_sha256' in model and model['pcm_u8_sha256'] != hashlib.sha256(pcm.tobytes()).hexdigest()):
        raise AssertionError('Model recorded stream/PCM hashes disagree with exact output')
    raw = (pcm.astype(float)-128)/128
    wav_path = model_path.parent/'decoded.wav'
    wav, sr = sf.read(wav_path, dtype='float64')
    if sr != model['sample_rate'] or sf.info(wav_path).subtype != 'FLOAT' or not np.array_equal(wav, raw):
        raise AssertionError('Decoded FLOAT WAV altered, clipped or rescaled the exact DAC samples')
    reference_path = (Path(reference_root)/entry['reference']).resolve()
    if not reference_path.is_relative_to(Path(reference_root).resolve()) or sha(reference_path) != entry['reference_sha256']:
        raise ValueError('Reference location/hash differs from prepared corpus')
    reference, rate = sf.read(reference_path, dtype='float64')
    if rate != sr or len(reference) != len(pcm):
        raise ValueError('Reference and output duration/rate differ')
    arithmetic = audit(frames, durations, continuous=False)
    periods = frames[:, 0]
    histogram = lambda a: [dict(value=int(v), count=int(n)) for v, n in zip(*np.unique(a, return_counts=True))]
    return dict(id=entry['id'], language=entry['language'], voice=entry['voice'], condition=entry['condition'],
        source_id=entry['source_id'], reference_sha256=entry['reference_sha256'],
        model_sha256=sha(model_path), stream_sha256=hashlib.sha256(payload).hexdigest(),
        pcm_u8_sha256=hashlib.sha256(pcm.tobytes()).hexdigest(), decoded_wav_sha256=sha(wav_path),
        exact_oracle_equal=True, packed_stream_equal=True, expected_raw_equal=True, float_wav_sample_exact=True,
        reference_subtype=sf.info(reference_path).subtype, decoded_subtype=sf.info(wav_path).subtype,
        arithmetic=arithmetic, reference=signal_stats(reference), decoded=signal_stats(wav),
        source=dict(excitation=signal_stats(excitation/128), pulse_events=int(pulses.sum()),
            frame_boundaries=int(boundaries.sum()), unique_period_codes=len(np.unique(periods[periods != 0])),
            voiced_samples=int(durations[periods != 0].sum()),
            pulse_shape_modes=histogram((frames[:, 1] >> 4) & 3), gain_codes=histogram(frames[:, 1] & 15)),
        output_rms_over_reference_rms=float(np.sqrt(np.mean(wav*wav))/max(1e-30, np.sqrt(np.mean(reference*reference)))))


def run(manifest_path, models, reference_root, expected_count=20):
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    entries = [c for c in manifest['clips'] if c['variant'] == 'center2048']
    if len(entries) != expected_count:
        raise ValueError('Unexpected number of short corpus references')
    rows = [audit_model(Path(models)/entry['id']/'model.json', entry, reference_root) for entry in entries]
    return dict(schema='hq4-speech-clipping-audit-v1', manifest_sha256=sha(manifest_path),
        audit_phase='legacy; continuous=False; no decoder or model changes',
        plateau_definition='At least two consecutive exactly equal samples; local peaks require both neighboring runs to be lower/higher; extrema are the observed min/max, not only DAC endpoints',
        interpretation='Internal modulo wrap is overflow distortion, not saturating clipping. DAC endpoint occupancy, flat quantized peaks, and external WAV limiting are separate checks. A flat peak alone does not prove clipping.',
        source_sha256_normalized_lf={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for p in (Path(__file__), CODEC/'model.py', CODEC/'hq4_phase.py', CODEC/'hq4_core.py')},
        totals=dict(clips=len(rows), samples=sum(r['decoded']['samples'] for r in rows),
            subtraction_wraps=sum(r['arithmetic']['subtraction_wraps'] for r in rows),
            state_addition_wraps=sum(r['arithmetic']['state_addition_wraps'] for r in rows),
            negative_128_multiplications=sum(r['arithmetic']['negative_128_multiplication'] for r in rows),
            dac_endpoint_samples=sum(r['arithmetic']['extreme_pwm_samples'] for r in rows),
            fractional_products=sum(r['arithmetic']['fractional_products'] for r in rows),
            multiplication_count=sum(r['arithmetic']['multiplication_count'] for r in rows),
            minimum_unique_output_levels=min(r['decoded']['unique_levels'] for r in rows),
            maximum_unique_output_levels=max(r['decoded']['unique_levels'] for r in rows),
            float_wav_exact_clips=sum(r['float_wav_sample_exact'] for r in rows)), clips=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT/'build/speech-corpus/manifest.json')
    parser.add_argument('--references', type=Path, default=ROOT/'build/speech-corpus')
    parser.add_argument('--models', type=Path, default=ROOT/'build/speech-corpus-benchmark/short/models')
    parser.add_argument('--output', type=Path, default=ROOT/'build/speech-clipping/audit.json')
    args = parser.parse_args()
    report = run(args.manifest, args.models, args.references)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(report['totals']))
    for row in report['clips']:
        print(row['id'], row['arithmetic']['subtraction_wraps'], row['arithmetic']['state_addition_wraps'],
            row['decoded']['unique_levels'], row['decoded']['observed_minimum']['maximum_equal_run'],
            row['decoded']['observed_maximum']['maximum_equal_run'])


if __name__ == '__main__':
    main()

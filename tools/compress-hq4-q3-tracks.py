"""Reduce real Q3 stream bytes with explicit measured partial-track tolerances.

Frequency and amplitude caps apply to power-weighted p95 errors by default,
not every instantaneous partial. Absolute-original and explicitly relative
additional-error modes are distinct. Missing/extra energy, coverage and track
continuity remain bounded by the frozen input model at every sweep level.
"""
import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys

import numpy as np
import soundfile as sf
from pystoi import stoi

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from harmonic_tracks import HarmonicTrackObjective
from hq4_core import pack_stream
from hq4_q3 import render
from hq4_speech_search import deterministic_estoi, validate
from q3_track_rate import TrackLimits, VERSION, reduce_rate
from spectrogram_objective import SpectrogramObjective


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tolerance_levels(args):
    if args.sweep:
        if args.frequency_tolerance_cents is not None or args.frequency_tolerance_hz is not None or args.amplitude_tolerance_db is not None:
            raise ValueError('Use --frequency-unit with --sweep; individual tolerance arguments are for a single level')
        levels = [tuple(map(float, item.split(':'))) for item in args.sweep.split(',')]
        unit = args.frequency_unit
    else:
        if args.frequency_tolerance_cents is None and args.frequency_tolerance_hz is None:
            raise ValueError('Specify a frequency tolerance or a sweep')
        if args.amplitude_tolerance_db is None:
            raise ValueError('A single level requires --amplitude-tolerance-db')
        unit = 'hz' if args.frequency_tolerance_hz is not None else 'cents'
        levels = [(args.frequency_tolerance_hz if unit == 'hz' else args.frequency_tolerance_cents,
                   args.amplitude_tolerance_db)]
    if (not levels or any(len(level) != 2 or not np.all(np.isfinite(level)) or min(level) < 0 for level in levels)
            or any(b[0] < a[0] or b[1] < a[1] for a, b in zip(levels, levels[1:]))):
        raise ValueError('Sweep levels must be finite nonnegative frequency:amplitude pairs, both monotonically nondecreasing')
    return levels, unit


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', required=True, type=Path)
    p.add_argument('--model', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    group = p.add_mutually_exclusive_group()
    group.add_argument('--frequency-tolerance-cents', type=float)
    group.add_argument('--frequency-tolerance-hz', type=float)
    p.add_argument('--amplitude-tolerance-db', type=float)
    p.add_argument('--sweep', help='Comma-separated frequency:amplitude pairs; for example 0:0,25:1,75:2')
    p.add_argument('--frequency-unit', choices=('cents', 'hz'), default='cents', help='Frequency units in --sweep')
    p.add_argument('--relative-to-baseline', action='store_true', help='Allow only the specified ADDITIONAL error over the frozen input model')
    p.add_argument('--error-statistic', choices=('p95', 'mean', 'max'), default='p95',
                   help='p95 is weighted by matched original partial power; max bounds every matched partial')
    p.add_argument('--max-evaluations', type=int, default=500, help='Exact candidate evaluations per tolerance level')
    p.add_argument('--repair-proposals', type=int, default=2, help='Joint coefficient refits per byte-saving operation, 0..16')
    speech = p.add_mutually_exclusive_group()
    speech.add_argument('--minimum-stoi', type=float, help='Optional absolute intelligibility floor')
    speech.add_argument('--maximum-stoi-drop', type=float, help='Optional maximum drop from the frozen input STOI')
    p.add_argument('--seed', type=int, default=23191)
    p.add_argument('--layout', choices=('standalone', 'bell'), default='standalone')
    p.add_argument('--build', action='store_true', help='Qualify the final feasible standalone model with all three AVR engines')
    p.add_argument('--avr-bin', type=Path)
    p.add_argument('--node', default='node')
    a = p.parse_args()
    try:
        levels, unit = tolerance_levels(a)
    except (ValueError, TypeError) as error:
        p.error(str(error))
    if a.max_evaluations < 0 or not 0 <= a.repair_proposals <= 16:
        p.error('Evaluation budget must be nonnegative and repair count 0..16')
    if any(value is not None and (not np.isfinite(value) or not 0 <= value <= 1)
           for value in (a.minimum_stoi, a.maximum_stoi_drop)):
        p.error('STOI floor/drop must be finite and within 0..1')
    reference, sr = sf.read(a.reference, dtype='float64')
    model = json.loads(a.model.read_text(encoding='utf-8'))
    if (model.get('schema') != 'hq4-q3-v1' or model.get('coefficient_scale') != 8
            or model.get('coefficient_range') != [-7, 7] or model.get('tilt_shift') not in (0, 1)
            or model.get('sample_rate') != 7500 or sr != 7500 or reference.ndim != 1):
        p.error('Expected an explicitly tagged Q3 model and mono 7500-Hz original')
    f, d = np.asarray(model['frames']), np.asarray(model['durations'])
    validate(f, d, len(reference))
    if model.get('samples') != len(reference) or np.any((f[:, 2:] & 15) == 0) or np.any((f[:, 2:] >> 4) == 0):
        p.error('Model must preserve the complete reference and exclude Q3 coefficient -8')
    f, d = f.astype(np.uint8), d.astype(np.uint16)
    tilt = model['tilt_shift']
    if a.layout == 'bell' and tilt != 1:
        p.error('The compact bell profile implements Q3/T1')
    if a.build and a.layout != 'standalone':
        p.error('Composite models use build-q3-bell-hq4.py for bell balancing and qualification')
    code_bytes = 576 if a.layout == 'bell' else 420 if tilt else 408
    descriptor_bytes, eeprom_bytes = (15, 64) if a.layout == 'bell' else (0, 0)
    objective = HarmonicTrackObjective(reference, sr)
    baseline_audio = (render(f, d, tilt)[0].astype(float)-128)/128
    baseline_stoi = float(stoi(reference, baseline_audio, sr))
    baseline_estoi = deterministic_estoi(reference, baseline_audio, sr)
    minimum_stoi = (max(0., baseline_stoi-a.maximum_stoi_drop) if a.maximum_stoi_drop is not None else a.minimum_stoi)
    cache, renders = {}, 0
    def evaluate(frames, durations):
        nonlocal renders
        payload = pack_stream(frames, durations)
        if payload not in cache:
            renders += 1
            pcm, counts = render(frames, durations, tilt)
            signed = pcm.astype(np.int16)-128
            if np.any(counts) or np.max(abs(signed)) > 115 or np.any(abs(np.diff(signed)) >= 48):
                cache[payload] = None
            else:
                audio = signed.astype(float)/128
                if a.error_statistic == 'max':
                    detail = objective.details(audio)
                    metrics = detail['metrics']
                    matches = detail['matches']
                    metrics.update(frequency_error_max_cents=max((abs(x['frequency_error_cents']) for x in matches), default=0.),
                        frequency_error_max_hz=max((abs(x['frequency_error_hz']) for x in matches), default=0.),
                        level_error_max_db=max((abs(x['level_error_db']) for x in matches), default=0.))
                    cache[payload] = metrics
                else:
                    cache[payload] = objective.evaluate(audio)
                if minimum_stoi is not None:
                    cache[payload]['stoi'] = float(stoi(reference, audio, sr))
        return cache[payload]
    baseline = evaluate(f, d)
    if baseline is None:
        p.error('Input Q3 model must satisfy every internal wrap, PWM headroom and discontinuity guard')
    a.output.mkdir(parents=True, exist_ok=True)
    baseline_bytes = len(pack_stream(f, d))
    report = dict(schema=VERSION, sample_rate=sr, samples=len(reference), seed=a.seed,
        mode='additional-error-over-frozen-input' if a.relative_to_baseline else 'absolute-error-from-original',
        frequency_unit=unit, error_statistic=a.error_statistic,
        error_definition=('Maximum absolute error of every matched original partial' if a.error_statistic == 'max' else
            'Matched-original-partial-power-weighted p95 absolute error' if a.error_statistic == 'p95' else
            'Matched-original-partial-power-weighted mean absolute error'),
        missing_extra_coverage_continuity='Hard caps/floor frozen from the original input model; never loosened by the sweep',
        baseline_tracking=baseline, baseline_stream_bytes=baseline_bytes,
        baseline_stoi=baseline_stoi, baseline_estoi=baseline_estoi,
        minimum_stoi=minimum_stoi, maximum_stoi_drop=a.maximum_stoi_drop,
        code_bytes=code_bytes, descriptor_bytes=descriptor_bytes, end_marker_bytes=1,
        eeprom_bytes=eeprom_bytes, layout=a.layout, flash_limit_bytes=1024,
        max_evaluations_per_level=a.max_evaluations, repair_proposals=a.repair_proposals,
        reference_sha256=sha(a.reference.read_bytes()), input_model_sha256=sha(a.model.read_bytes()),
        harmonic_config=objective.config, hardware_tested=False, human_listening_verified=False, levels=[])
    rng = random.Random(a.seed)
    spectral = SpectrogramObjective(reference)
    for index, (frequency, amplitude) in enumerate(levels):
        limits = TrackLimits.create(baseline, frequency, amplitude, unit=unit,
                                   statistic=a.error_statistic, relative=a.relative_to_baseline,
                                   minimum_stoi=minimum_stoi)
        result = reduce_rate(f, d, evaluate, limits, rng, max_evaluations=a.max_evaluations, repairs=a.repair_proposals)
        f, d = result['frames'], result['durations']
        pcm, counts = render(f, d, tilt)
        audio = (pcm.astype(float)-128)/128
        flash = (code_bytes+descriptor_bytes+result['stream_bytes']+2)//2*2
        entry = {key:result[key] for key in ('feasible', 'failed_guards', 'initial_stream_bytes', 'stream_bytes',
                                            'evaluations', 'accepted_operations', 'history')}
        entry.update(level=index, requested_frequency_tolerance=frequency, requested_amplitude_tolerance_db=amplitude,
            limits=asdict(limits), tracking=result['score'], computed_flash_bytes=flash,
            fits_target=flash <= 1024, firmware_qualified=False, intermediate_wraps=counts.tolist(),
            stoi=float(stoi(reference, audio, sr)), estoi=deterministic_estoi(reference, audio, sr),
            spectrum=spectral.evaluate(audio), stream_sha256=sha(result['payload']), pcm_sha256=sha(pcm.tobytes()))
        entry['status'] = 'feasible' if result['feasible'] and flash <= 1024 else 'infeasible-tracking-bounds' if not result['feasible'] else 'oversized'
        directory = a.output/f'level-{index}'
        directory.mkdir(exist_ok=True)
        exported = dict(model, frames=f.tolist(), durations=d.tolist(), samples=len(reference),
                        stream_sha256=sha(result['payload']))
        (directory/'model.json').write_text(json.dumps(exported, indent=2)+'\n', encoding='utf-8', newline='\n')
        (directory/'speech.hq').write_bytes(result['payload'])
        (directory/'expected.raw').write_bytes(pcm.tobytes())
        sf.write(directory/'decoded.wav', audio, sr, subtype='PCM_16')
        (directory/'quality.json').write_text(json.dumps(entry, indent=2)+'\n', encoding='utf-8', newline='\n')
        report['levels'].append(entry)
        print(json.dumps({key:entry[key] for key in ('level', 'status', 'stream_bytes', 'computed_flash_bytes',
                                                   'requested_frequency_tolerance', 'requested_amplitude_tolerance_db', 'tracking', 'stoi')}), flush=True)
    sources = (Path(__file__), CODEC/'q3_track_rate.py', CODEC/'harmonic_tracks.py', CODEC/'hq4_q3.py',
               CODEC/'hq4_core.py', CODEC/'spectrogram_objective.py')
    report['source_sha256_normalized_lf'] = {path.relative_to(ROOT).as_posix():sha(path.read_text(encoding='utf-8').encode()) for path in sources}
    report['unique_exact_renders'] = renders
    if a.build and report['levels'][-1]['status'] == 'feasible':
        spec = importlib.util.spec_from_file_location('rate_q3_builder', ROOT/'tools/probe-hq4-q3.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        report['build'] = builder.build(a.output/f'level-{len(levels)-1}'/'avr', f, d, tilt, a.avr_bin, a.node)
        if report['build']['status'] != 'verified':
            raise ValueError('Compressed final model did not pass three-engine AVR qualification')
        report['levels'][-1]['firmware_qualified'] = True
        (a.output/f'level-{len(levels)-1}'/'quality.json').write_text(
            json.dumps(report['levels'][-1], indent=2)+'\n', encoding='utf-8', newline='\n')
    (a.output/'quality.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()

"""PC proof: three/ten independently controlled adaptive sinusoidal tracks."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from pystoi import stoi
from scipy.signal import sosfilt
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from harmonic_tracks import HarmonicTrackObjective
from hq4_speech_search import deterministic_estoi
from partial_bounds import check_partial_bounds
from sin_partials import analyze, render, encode, decode, simplify, curve_errors, encode_log, decode_log, fit_phase_only, log_layout
from spectrogram_objective import SpectrogramObjective


def measure(reference, audio, components):
    control = HarmonicTrackObjective(reference, max_tracks=components)
    matched = control.details(audio)
    raw = copy.copy(control)
    raw.matched = lambda value: sosfilt(raw.hp, np.asarray(value, float))
    absolute = raw.details(audio)
    residual = float(np.sum((reference-audio)**2)/np.sum(reference**2))
    return dict(stoi=float(stoi(reference, audio, 7500)), estoi=deterministic_estoi(reference, audio, 7500),
                **SpectrogramObjective(reference).evaluate(audio),
                raw_residual_energy_ratio=residual, raw_explained_energy_fraction=1-residual,
                raw_output_to_reference_rms=float(np.sqrt(np.mean(audio**2)/np.mean(reference**2))),
                raw_partial_metrics=absolute['metrics'], level_matched_partial_metrics=matched['metrics'],
                raw_partial_bounds=check_partial_bounds(absolute, max_level_error_db=5., duration_seconds=len(reference)/7500),
                raw_frequency_and_level_bounds=check_partial_bounds(absolute, max_level_error_db=5., max_frequency_error_cents=50., duration_seconds=len(reference)/7500),
                level_matched_partial_bounds=check_partial_bounds(matched, max_level_error_db=5., duration_seconds=len(reference)/7500))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--components', nargs='+', type=int, default=[3, 10])
    a = p.parse_args()
    reference, sr = sf.read(a.reference)
    if sr != 7500 or reference.ndim != 1 or any(n not in range(1, 11) for n in a.components):
        p.error('Expected mono7500 reference and 1..10 components')
    a.output.mkdir(parents=True, exist_ok=True)
    sha = lambda data: hashlib.sha256(data).hexdigest()
    sources = (Path(__file__), CODEC/'sin_partials.py', CODEC/'harmonic_tracks.py', CODEC/'partial_bounds.py')
    report = dict(schema='sin-partials-pc-study-v1', reference_sha256=sha(a.reference.read_bytes()),
        samples=len(reference), sample_rate=sr, hardware_tested=False, avr_implemented=False,
        payload_policy='Actual source-parameter serialization only; PC decoder code and runtime memory are excluded',
        residual_policy='No source waveform or uncompressed residual is stored; remaining aperiodic speech is measured, not synthesized',
        phase_policy='Integral of linearly interpolated frequency, continuous at every knot; one fitted initial phase per stable track',
        amplitude_policy='Linear dB interpolation inside positive runs; explicit zero knots/gaps and amplitude fades at birth/death',
        sources_sha256_normalized_lf={path.relative_to(ROOT).as_posix():sha(path.read_text(encoding='utf-8').encode()) for path in sources},
        variants={})
    for n in a.components:
        model = analyze(reference, n)
        dest = a.output/f'components-{n}'
        dest.mkdir(parents=True, exist_ok=True)
        raw_json = json.dumps(model, separators=(',', ':')).encode()
        (dest/'unquantized-model.json').write_bytes(raw_json)
        audio = render(model)
        sf.write(dest/'unquantized.wav', audio, sr, subtype='FLOAT')
        rows = dict(unquantized=dict(measure(reference, audio, n), parameter_json_bytes=len(raw_json),
                    tracks=len(model['tracks']), knots=sum(len(t['frames']) for t in model['tracks'])))
        signals = [reference, audio]
        for name, ftol, atol, bits in (('dense-q8', .00001, .00001, 8),
                                     ('adaptive-tight-q8', 1., .5, 8),
                                     ('adaptive-medium-q8', 3., 1., 8),
                                     ('adaptive-loose-q8', 8., 3., 8),
                                     ('adaptive-loose-q4', 8., 3., 4)):
            sparse = simplify(model, ftol, atol)
            payload = encode(sparse, frequency_step=1., amplitude_bits=bits)
            restored = decode(payload)
            synthesized = render(restored)
            (dest/(name+'.sp')).write_bytes(payload)
            sf.write(dest/(name+'.wav'), synthesized, sr, subtype='FLOAT')
            row = dict(measure(reference, synthesized, n), payload_bytes=len(payload),
                knots=sum(len(t['frames']) for t in restored['tracks']), tracks=len(restored['tracks']),
                amplitude_bits=bits, frequency_quantum_hz=1.,
                requested_interpolation_frequency_bound_hz=ftol, requested_interpolation_level_bound_db=atol,
                actual_curve_errors_including_quantization=curve_errors(model, restored),
                payload_sha256=sha(payload), waveform_sha256=sha(synthesized.astype('<f8').tobytes()))
            rows[name] = row
            signals.append(synthesized)
        for name, ftol, atol in (('log32-tight', 1., .5), ('log32-medium', 3., 1.), ('log32-loose', 8., 3.)):
            sparse = simplify(model, ftol, atol)
            initial = decode_log(encode_log(sparse, bins_per_octave=32, level_step_db=1.))
            phase_fitted = fit_phase_only(reference, initial)
            payload = encode_log(phase_fitted, bins_per_octave=32, level_step_db=1.)
            restored = decode_log(payload)
            synthesized = render(restored)
            (dest/(name+'.sp')).write_bytes(payload)
            sf.write(dest/(name+'.wav'), synthesized, sr, subtype='FLOAT')
            rows[name] = dict(measure(reference, synthesized, n), payload_bytes=len(payload),
                knots=sum(len(t['frames']) for t in restored['tracks']), tracks=len(restored['tracks']),
                log_bins_per_octave=32, level_quantum_db=1., theoretical_frequency_quantization_max_cents=18.75,
                theoretical_level_quantization_max_db=.5, phase_fitted_after_frequency_quantization=True,
                actual_curve_errors_including_quantization=curve_errors(model, restored),
                payload_layout=log_layout(restored, len(payload)),
                payload_sha256=sha(payload), waveform_sha256=sha(synthesized.astype('<f8').tobytes()))
            signals.append(synthesized)
        presentation = SpectralObjective(reference)
        signals = [sosfilt(presentation.hp, value) for value in signals]
        signals = [value*presentation.rms/(np.sqrt(np.mean(value*value))+1e-20) for value in signals]
        gain = .85/max(float(np.max(abs(value))) for value in signals)
        sf.write(dest/'comparison.wav', np.concatenate([part for value in signals for part in (value*gain, np.zeros(2250))]), sr, subtype='PCM_16')
        report['variants'][str(n)] = rows
        (a.output/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
        print(json.dumps(dict(components=n, results={key:dict(stoi=value['stoi'], estoi=value['estoi'],
            bytes=value.get('payload_bytes', value.get('parameter_json_bytes')), explained=value['raw_explained_energy_fraction'],
            raw_bound_pass=value['raw_partial_bounds']['passed']) for key,value in rows.items()})), flush=True)


if __name__ == '__main__':
    main()

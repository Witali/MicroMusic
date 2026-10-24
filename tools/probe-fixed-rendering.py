"""Measure synthesis simplifications with frozen, automatically fitted speech.

These experimental rendering variants do not change fixed_period.py or its
format. Coefficients/noise/DC remain identical; results are controlled ablation
measurements, not optimistically retuned scores or assembled AVR size claims.
"""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
import numpy as np
from numba import njit
import soundfile as sf
from pystoi import stoi

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from dc_blocker import block_dc
from fixed_period import decode_fixed, frame_sample, integer_noise, pack_avr_data, pack_fixed, validate


@njit(cache=True)
def synthesize_variant(frames, book, noise, samples, initial_phase, temporal, phase_bits, nearest_residual):
    out = np.empty(samples, np.uint8)
    phase = initial_phase
    for n in range(samples):
        # The 16-bit oscillator still accumulates its exact original pitch.
        # Only the table lookup fraction loses precision in these variants.
        lookup_phase = phase if phase_bits == 4 else phase & ~((1 << (11-phase_bits))-1)
        nearest = n//64
        if not temporal:
            sample = frame_sample(int(frames[nearest, 1]), int(frames[nearest, 2]),
                                  lookup_phase, book, noise, n, 4)
        else:
            left = max(0, (n-32)//64)
            right = min(len(frames)-1, left+1) if n >= 32 else 0
            blend = ((n-32) & 63) if n >= 32 else 0
            # One selected residual can be computed once and reused by both
            # base frames. Sharing it before the existing branch saturation
            # preserves the precise arithmetic/clipping order of this probe.
            first_residual = int(frames[nearest if nearest_residual else left, 2])
            second_residual = int(frames[nearest if nearest_residual else right, 2])
            first = frame_sample(int(frames[left, 1]), first_residual, lookup_phase, book, noise, n, 4)
            second = frame_sample(int(frames[right, 1]), second_residual, lookup_phase, book, noise, n, 4)
            sample = first+(((second-first)*blend+32) >> 6)
        out[n] = sample+128
        phase = (phase+(int(frames[nearest, 0]) << 5)) & 65535
    return out


def render(model, temporal=True, phase_bits=4, nearest_residual=False):
    frames, book, filters = validate(model)
    noise = integer_noise(model['samples'], model['noise_seed_u16'], filters)
    raw = synthesize_variant(frames, book, noise, model['samples'], model['initial_phase_u16'],
                             temporal, phase_bits, nearest_residual)
    shift = model.get('dc_block_shift', 0)
    if shift:
        pcm, _, clips, peak = block_dc(raw, shift)
    else:
        pcm, clips, peak = raw, 0, int(np.max(abs(raw.astype(int)-128)))
    return pcm, raw, clips, peak


def metrics(pcm, raw, dc_clips, preclip_peak, reference, objective):
    audio = (pcm.astype(np.float64)-128)/128
    local_mean = np.convolve(audio, np.ones(750)/750, mode='valid')
    return dict(**objective.spectrum(audio), stoi=float(stoi(reference, audio, 7500)),
                estoi=float(stoi(reference, audio, 7500, extended=True)),
                peak=float(np.max(abs(audio))), output_endpoints=int(np.sum((pcm==0)|(pcm==255))),
                pre_dc_endpoints=int(np.sum((raw==0)|(raw==255))), dc_clipped=int(dc_clips),
                pre_dc_clamp_peak=int(preclip_peak), mean_pwm_lsb=float(np.mean(audio)*128),
                max_abs_100ms_mean_lsb=float(np.max(abs(local_mean))*128))


def operation_counts(model, temporal, nearest_residual):
    frames = np.asarray(model['frames'])
    calls = colored = white = 0
    for n in range(model['samples']):
        if temporal and not nearest_residual:
            left = max(0, (n-32)//64)
            indices = (left, min(len(frames)-1,left+1) if n>=32 else 0)
        else:
            indices = (n//64,)
        calls += len(indices)
        for i in indices:
            residual = int(frames[i, 2])
            if residual & 15:
                if residual >> 4:
                    colored += 1
                else:
                    white += 1
    return dict(base_frame_evaluations=model['samples']*(2 if temporal else 1),
                distinct_residual_evaluations=calls, colored_fir_evaluations=colored,
                white_residual_evaluations=white,
                note='Potential native evaluations before common-subexpression elimination; PC probe reuses baseline frame helper.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    model_bytes = args.model.read_bytes()
    model = json.loads(model_bytes)
    if model['phase_bits'] != 4:
        raise ValueError('This controlled study expects a phase_bits=4 fitted model')
    reference_bytes = args.reference.read_bytes()
    digest = lambda data:hashlib.sha256(data).hexdigest()
    clips = json.loads((ROOT/'ATtiny13A/Sound/audio-references.json').read_text(encoding='utf-8'))['clips']
    clip = next((item for item in clips if item['sha256']==digest(reference_bytes)), None)
    if clip is None:
        raise ValueError('Reference is not a hash-verified canonical original')
    reference, sr = sf.read(args.reference)
    if sr != 7500 or reference.shape != (model['samples'],):
        raise ValueError('Reference/model duration or sample rate differs')
    objective = SpectralObjective(reference)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'source-model.json').write_bytes(model_bytes)
    variants = [
        ('baseline', True, 4, False, 'Full integer model; numerical equality checked against decode_fixed.'),
        ('no-frame-interpolation', False, 4, False, 'One nearest frame per sample; removes second render and temporal blend, may create boundary clicks.'),
        ('phase-2bit', True, 2, False, 'Four lookup substeps per table entry instead of sixteen; oscillator phase remains exact.'),
        ('phase-nearest', True, 0, False, 'Direct 32-point table lookup; removes waveform interpolation but adds harmonic distortion.'),
        ('nearest-residual', True, 4, True, 'Base frame fade retained; one nearest residual reused before branch saturation, up to one FIR per sample.'),
        ('phase-2bit-nearest-residual', True, 2, True, 'Combine reduced lookup precision and shared nearest residual.'),
        ('no-frame-interpolation-phase-2bit', False, 2, False, 'Combine one frame render and reduced lookup precision.'),
    ]
    report = dict(schema='fixed-speech-rendering-ablation-v1', clip_id=clip['id'],
                  source_model_sha256=digest(model_bytes), reference_sha256=digest(reference_bytes),
                  portable_payload_bytes=len(pack_fixed(model)), avr_table_bytes=len(pack_avr_data(model)),
                  coefficients_frozen=True, auto_retuned=False, avr_assembled=False, hardware_verified=False,
                  dc_block_shift=model.get('dc_block_shift',0),
                  objective='same 70 Hz highpass/RMS-matched multi-resolution spectral loss; unfiltered STOI/eSTOI',
                  packages={name:version(name) for name in ('numpy','scipy','numba','soundfile','pystoi')},
                  normalized_source_sha256={str(p.relative_to(ROOT)).replace('\\','/'):
                      digest(p.read_text(encoding='utf-8').encode('utf-8')) for p in (
                          Path(__file__),CODEC/'fixed_period.py',CODEC/'dc_blocker.py',CODEC/'auto_encoder.py')},
                  variants=[])
    baseline_pcm = baseline_raw = baseline_metrics = None
    for name, temporal, phase_bits, nearest_residual, note in variants:
        pcm, raw, dc_clips, preclip_peak = render(model, temporal, phase_bits, nearest_residual)
        if name=='baseline':
            if not np.array_equal(pcm, decode_fixed(model)):
                raise AssertionError('Baseline probe does not reproduce the independent integer decoder')
            baseline_pcm, baseline_raw = pcm, raw
        elif phase_bits==4:
            centres = np.arange(32,model['samples'],64)
            if not np.array_equal(raw[centres], baseline_raw[centres]):
                raise AssertionError('A frame-selection ablation changed the exact frame-center samples')
        value = metrics(pcm, raw, dc_clips, preclip_peak, reference, objective)
        if name=='baseline':
            baseline_metrics = value
        diff = pcm.astype(int)-baseline_pcm.astype(int)
        entry = dict(variant=name, temporal_interpolation=temporal, lookup_fraction_bits=phase_bits,
                     nearest_residual=nearest_residual, note=note, metrics=value,
                     stoi_change=value['stoi']-baseline_metrics['stoi'],
                     estoi_change=value['estoi']-baseline_metrics['estoi'],
                     log_error_change=value['log_spectral_error']-baseline_metrics['log_spectral_error'],
                     differing_samples=int(np.count_nonzero(diff)), maximum_pwm_difference=int(np.max(abs(diff))),
                     operations=operation_counts(model,temporal,nearest_residual), pcm_sha256=digest(pcm.tobytes()))
        report['variants'].append(entry)
        sf.write(args.output/(name+'.wav'), (pcm.astype(float)-128)/128,7500,subtype='PCM_16')
        print(f"{name}: STOI={value['stoi']:.6f} eSTOI={value['estoi']:.6f} log={value['log_spectral_error']:.6f} "
              f"DCclips={value['dc_clipped']} maxdiff={entry['maximum_pwm_difference']}",flush=True)
    (args.output/'quality.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')


if __name__=='__main__':
    main()

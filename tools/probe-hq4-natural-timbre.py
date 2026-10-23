"""Compare integer HQ4-T tilt/gain profiles with complete ordinary-HQ4 speech.

The seven-instruction tilt stage is independent of lattice state. Its filter
wraps and the lattice's internal wraps must not grow. Brightness/roughness
diagnostics are engineering measurements, never a naturalness listening score.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import re
import sys

import numpy as np
import soundfile as sf
from numba import njit
from pystoi import stoi
from scipy.signal import sosfilt, welch

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from hq4_core import pack_stream, unpack_stream
from hq4_phase import audit
from hq4_speech_search import deterministic_estoi, proposal
from model import decode
from new_hq4_encoder import reuse_coefficients, validate_reference


def sha(data):
    return hashlib.sha256(data).hexdigest()


@njit
def tilt(pcm, shift):
    output = np.empty(len(pcm), np.uint8)
    previous = wraps = 0
    for i in range(len(pcm)):
        raw = int(pcm[i])-128+previous-(previous >> shift)
        wraps += int(raw < -128 or raw > 127)
        previous = ((raw+128) & 255)-128
        output[i] = (previous+128) & 255
    return output, wraps


def diagnostics(pcm):
    x = np.asarray(pcm, dtype=float)/128-1
    f, power = welch(x, fs=7500, nperseg=512)
    total = float(power.sum())+1e-30
    rms = float(np.sqrt(np.mean(x*x)))
    return dict(spectral_centroid_hz=float(np.sum(f*power)/total),
                power_above_2000_hz=float(np.sum(power[f >= 2000])/total),
                difference_rms_over_signal_rms=float(np.sqrt(np.mean(np.diff(x)**2))/(rms+1e-20)),
                distinct_pwm_values=int(len(np.unique(pcm))), pwm_rms=rms*128,
                mean_signed_pwm=float(np.mean(x)*128))


def evaluate(objective, frames, durations, shift, *, full=False):
    raw = decode(frames, durations, 0)
    pcm, wraps = tilt(raw, shift)
    signed = pcm.astype(np.int16)-128
    steps = int(np.sum(abs(np.diff(signed)) >= 48))
    if wraps or np.max(abs(signed)) > 115 or steps:
        return None
    audio = signed.astype(float)/128
    spectrum = objective.spectrum(audio)
    value = float(stoi(objective.reference, audio, 7500))
    if not math.isfinite(value):
        return None
    result = dict(**spectrum, stoi=value, balanced_score=value-.08*spectrum['loss'],
                  peak_signed=int(np.max(abs(signed))), steps_ge_48=steps, tilt_wraps=wraps,
                  stream_bytes=len(pack_stream(frames, durations)))
    if full:
        result.update(estoi=deterministic_estoi(objective.reference, audio, 7500),
                      diagnostics=diagnostics(pcm), lattice=audit(frames, durations))
    return result


def no_new_wraps(frames, durations, baseline):
    measured = audit(frames, durations)
    return all(measured[key] <= baseline[key]
               for key in ('subtraction_wraps', 'state_addition_wraps', 'negative_128_multiplication'))


def fit_rate(frames, durations, budget):
    """Save a few spectral-update bytes with minimum-duration-weighted edits.

    Unlike increasing a global reuse threshold, this changes only the cheapest
    individual spectral halves needed for the extra output-filter instructions.
    Pitch, gain, excitation and every sample duration remain unchanged.
    """
    f = frames.copy()
    while len(pack_stream(f, durations)) > budget:
        old_size = len(pack_stream(f, durations))
        best = None
        for index in range(1, len(f)):
            for half in (slice(2, 4), slice(4, 6)):
                trial = f.copy()
                trial[index, half] = trial[index-1, half]
                saved = old_size-len(pack_stream(trial, durations))
                if saved <= 0:
                    continue
                a, b = f[index, half], trial[index, half]
                distance = np.sum((a.astype(int) % 16-b.astype(int) % 16)**2)
                distance += np.sum(((a.astype(int) >> 4)-(b.astype(int) >> 4))**2)
                cost = float(distance*int(durations[index])/saved)
                if best is None or cost < best[0]:
                    best = cost, trial
        if best is None:
            raise ValueError('No spectral-half reuse edit can meet this rate budget')
        f = best[1]
    return f


def build_candidate(output, frames, durations, shift, avr_bin, node):
    """Use the existing isolated builder's verified transport with a T model.

    The imported module instance is private to this call. Its template and
    numerical synthesis callback select the new profile; original files and
    global application state are never changed. The outer report fingerprints
    this callback and the profile template in addition to the builder's inputs.
    """
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    template = (CODEC/'natural-oneshot/hq4.S').read_text(encoding='utf-8')
    code_bytes = 416+2*shift
    template = template.replace('.set TILT_SHIFT,2', f'.set TILT_SHIFT,{shift}')
    template = template.replace('.set VOICE_ADDR,0x1a4', f'.set VOICE_ADDR,0x{code_bytes:x}')
    profile_source = output/'profile.S'
    profile_source.write_text(template, encoding='utf-8', newline='\n')
    spec = importlib.util.spec_from_file_location('natural_private_builder', ROOT/'tools/build-hq4-oneshot.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.TEMPLATE = profile_source
    builder.decode = lambda f, d, keep_phase=0: tilt(decode(f, d, keep_phase), shift)[0]
    stream = output.parent/'speech.hq'
    stream.write_bytes(pack_stream(frames, durations))
    report = builder.build('natural-timbre', output, avr_bin, node, stream=stream,
                           expected_samples=int(np.sum(durations)))
    report['naturalTimbre'] = dict(tiltShift=shift, codeBytes=code_bytes,
        callbackSourceSha256NormalizedLf=sha(Path(__file__).read_text(encoding='utf-8').encode('utf-8')),
        templateSha256NormalizedLf=sha((CODEC/'natural-oneshot/hq4.S').read_text(encoding='utf-8').encode('utf-8')))
    (output/'build.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--stream', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--proposals', type=int, default=4000)
    p.add_argument('--seed', type=int, default=23130)
    p.add_argument('--stream-budget', type=int, help='Optional tighter stream limit for a composite decoder')
    p.add_argument('--tilt-shift', type=int, choices=(1, 2, 3), help='Restrict the experiment to one specified leakage profile')
    p.add_argument('--build', action='store_true')
    p.add_argument('--avr-bin', type=Path)
    p.add_argument('--node', default='node')
    a = p.parse_args()
    if a.proposals < 0 or (a.stream_budget is not None and not 8 <= a.stream_budget <= 605):
        p.error('Invalid proposal count')
    reference, sr = sf.read(a.reference)
    validate_reference(reference, sr)
    frames, durations = unpack_stream(a.stream.read_bytes())
    if int(np.sum(durations)) != len(reference):
        p.error('Input stream must preserve the complete reference')
    baseline_pcm = decode(frames, durations, 0)
    objective = SpectralObjective(reference, sr)
    baseline_audio = (baseline_pcm.astype(float)-128)/128
    baseline = dict(**objective.spectrum(baseline_audio),
                    stoi=float(stoi(reference, baseline_audio, sr)),
                    estoi=deterministic_estoi(reference, baseline_audio, sr),
                    diagnostics=diagnostics(baseline_pcm), lattice=audit(frames, durations))
    trials, initial = [], None
    shifts = (a.tilt_shift,) if a.tilt_shift else (1, 2, 3)
    for shift in shifts:
        budget = 1024-(416+2*shift)-1
        if a.stream_budget is not None:
            budget = min(budget, a.stream_budget)
        candidates = [('local-minimum', fit_rate(frames, durations, budget))]
        candidates += [(threshold, reuse_coefficients(frames, threshold))
                       for threshold in (0., .25, .5, 1., 2., 4., 8., 16., 32., 225.)]
        for threshold, compressed in candidates:
            if len(pack_stream(compressed, durations)) > budget:
                continue
            for scale in (.5, .75, 1., 1.25, 1.5, 2.):
                trial = compressed.copy()
                trial[:, 1] = (trial[:, 1] & 48) | np.minimum(15, np.rint((trial[:, 1] & 15)*scale)).astype(np.uint8)
                if not no_new_wraps(trial, durations, baseline['lattice']):
                    trials.append(dict(shift=shift, reuse_threshold=threshold, gain_scale=scale, rejected='lattice-wrap'))
                    continue
                score = evaluate(objective, trial, durations, shift)
                trials.append(dict(shift=shift, reuse_threshold=threshold, gain_scale=scale, score=score))
                if score is not None and (initial is None or score['balanced_score'] > initial[3]['balanced_score']):
                    initial = trial, durations.copy(), shift, score, dict(reuse_threshold=threshold, gain_scale=scale)
    if initial is None:
        p.error('No clean T profile fits the complete recording')
    frames, durations, shift, first, settings = initial
    rng = random.Random(a.seed)
    budget = 1024-(416+2*shift)-1
    if a.stream_budget is not None:
        budget = min(budget, a.stream_budget)
    best = frames.copy(), durations.copy(), first
    history = []
    for step in range(a.proposals):
        trial, d = proposal(best[0], best[1], rng)
        if len(pack_stream(trial, d)) > budget:
            continue
        score = evaluate(objective, trial, d, shift)
        if (score is not None and score['balanced_score'] > best[2]['balanced_score']+1e-10
                and score['stoi'] >= first['stoi']-1e-12
                and score['loss'] <= first['loss']*1.03
                and no_new_wraps(trial, d, baseline['lattice'])):
            best = trial.copy(), d.copy(), score
            history.append(dict(proposal=step+1, **score))
        if (step+1) % 1000 == 0:
            print(json.dumps(dict(proposals=step+1, shift=shift, **best[2])), flush=True)
    frames, durations = best[:2]
    final = evaluate(objective, frames, durations, shift, full=True)
    pcm = tilt(decode(frames, durations, 0), shift)[0]
    payload = pack_stream(frames, durations)
    a.output.mkdir(exist_ok=True, parents=True)
    model = dict(schema='hq4-natural-timbre-v1', samples=len(reference), sample_rate=sr,
                 tilt_shift=shift, frames=frames.tolist(), durations=durations.tolist(),
                 reference_sha256=sha(a.reference.read_bytes()), stream_sha256=sha(payload))
    paths = [Path(__file__), CODEC/'natural-oneshot/hq4.S', CODEC/'hq4_phase.py', CODEC/'model.py',
             CODEC/'hq4_speech_search.py', CODEC/'new_hq4_encoder.py', CODEC/'auto_encoder.py']
    report = dict(schema='hq4-natural-timbre-v1', baseline=baseline, initial=first, final=final,
                  profile=dict(tilt_shift=shift, **settings), proposals=a.proposals, seed=a.seed,
                  requested_stream_budget=a.stream_budget,
                  candidate_tilt_shifts=list(shifts),
                  initial_trials=trials, history=history, samples=len(reference),
                  code_bytes=416+2*shift, stream_bytes=len(payload),
                  flash_bytes=(416+2*shift+len(payload)+2)//2*2,
                  reference_sha256=model['reference_sha256'], input_stream_sha256=sha(a.stream.read_bytes()),
                  pcm_sha256=sha(pcm.tobytes()), stream_sha256=sha(payload),
                  sources_sha256_normalized_lf={path.relative_to(ROOT).as_posix(): sha(path.read_text(encoding='utf-8').encode('utf-8')) for path in paths},
                  human_listening_verified=False, hardware_tested=False)
    for name, data in (('model.json', model), ('training.json', report)):
        (a.output/name).write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8', newline='\n')
    (a.output/'speech.hq').write_bytes(payload)
    (a.output/'expected.raw').write_bytes(pcm.tobytes())
    sf.write(a.output/'decoded.wav', (pcm.astype(float)-128)/128, sr, subtype='PCM_16')
    filtered = [sosfilt(objective.hp, x) for x in (reference, baseline_audio, (pcm.astype(float)-128)/128)]
    matched = [x*objective.rms/(np.sqrt(np.mean(x*x))+1e-10) for x in filtered]
    scale = .85/max(float(np.max(abs(x))) for x in matched)
    for name, audio in zip(('original-matched', 'before-matched', 'after-matched'), matched):
        sf.write(a.output/(name+'.wav'), audio*scale, sr, subtype='PCM_16')
    gap = np.zeros(round(.3*sr))
    sf.write(a.output/'comparison.wav', np.concatenate([part for i in (0, 1, 0, 2) for part in (matched[i]*scale, gap)]), sr, subtype='PCM_16')
    print(json.dumps(dict(stage='complete', profile=report['profile'], before=baseline,
                          after=final, flash_bytes=report['flash_bytes'])), flush=True)
    if a.build:
        built = build_candidate(a.output/'avr', frames, durations, shift, a.avr_bin, a.node)
        print(json.dumps(dict(stage='avr', status=built['status'], flash_bytes=built['flashBytes'])), flush=True)


if __name__ == '__main__':
    main()

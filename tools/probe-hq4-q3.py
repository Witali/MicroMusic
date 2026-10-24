"""Retune a wider Q3 HQ4 lattice against complete reference audio.

This is a separate codec profile: Q4 streams must never be played as Q3 without
refitting. The search checks every intermediate byte wrap, not merely PWM peaks.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import sys

import numpy as np
from pystoi import stoi
from scipy.signal import sosfilt
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from hq4_core import unpack_stream, pack_stream
from hq4_q3 import render
from hq4_speech_search import proposal, deterministic_estoi
from model import decode
from new_hq4_encoder import analyze, reuse_coefficients
from spectrogram_objective import SpectrogramObjective


def convert_coefficients(frames, scale=1.):
    out = frames.copy()
    for j in range(2, 6):
        low = np.maximum(1, np.minimum(15, np.rint(((frames[:, j]&15).astype(int)-8)*scale)+8)).astype(np.uint8)
        high = np.maximum(1, np.minimum(15, np.rint(((frames[:, j]>>4).astype(int)-8)*scale)+8)).astype(np.uint8)
        out[:, j] = low | (high << 4)
    return out


def evaluate(objective, frames, durations, tilt, budget, full=False):
    payload = pack_stream(frames, durations)
    if len(payload) > budget or np.any((frames[:, 2:]&15) == 0) or np.any((frames[:, 2:]>>4) == 0):
        return None
    pcm, wraps = render(frames, durations, tilt)
    if np.any(wraps):
        return None
    signed = pcm.astype(np.int16)-128
    steps = int(np.sum(abs(np.diff(signed)) >= 48))
    if np.max(abs(signed)) > 115 or steps:
        return None
    audio = signed.astype(float)/128
    spec = objective.spectrum(audio)
    st = float(stoi(objective.reference, audio, 7500))
    if not math.isfinite(st):
        return None
    # A balanced analysis-by-synthesis objective; final reports expose both.
    fitted = getattr(objective, 'spectrogram_objective', None)
    fine = fitted.evaluate(audio) if fitted is not None else {}
    value = st-.35*fine['spectrogram_loss'] if fine else st-.18*spec['loss']
    score = dict(**spec, **fine, stoi=st, objective=value,
                 stream_bytes=len(payload), peak_signed=int(np.max(abs(signed))),
                 steps_ge_48=steps, intermediate_wraps=wraps.tolist())
    if full:
        score['estoi'] = deterministic_estoi(objective.reference, audio, 7500)
    return score


def initial_models(reference, old_frames, old_durations, tilt, budget, objective=None, resume=None):
    objective = objective or SpectralObjective(reference)
    candidates = []
    # The half-scale seed approximately preserves retained Q4 filter responses;
    # fresh scale-eight LPC can use the additional representable resonances.
    bases = [(f'retained-scale{scale}', convert_coefficients(old_frames, scale), old_durations)
             for scale in (.5, .625, .75, .875, 1.)]
    if resume is not None:
        bases.insert(0, ('resumed-q3', resume[0], resume[1]))
    for hop in (64, 128, 256):
        if 2*math.ceil(len(reference)/hop)+4 > budget:
            continue
        for emphasis in (0., .65):
            f, d = analyze(reference, hop=hop, preemphasis=emphasis, coefficient_scale=8)
            bases.append((f'lpc-hop{hop}-pre{emphasis}', convert_coefficients(f), d))
    for label, frames, d in bases:
        for threshold in (0., .25, .5, 1., 2., 4., 8., 16., 32., 225.):
            shared = reuse_coefficients(frames, threshold)
            if len(pack_stream(shared, d)) > budget:
                continue
            for scale in (.15, .25, .4, .65, 1.):
                f = shared.copy()
                f[:, 1] = (f[:, 1]&48) | np.minimum(15, np.rint((f[:, 1]&15)*scale)).astype(np.uint8)
                score = evaluate(objective, f, d, tilt, budget)
                if score is not None:
                    candidates.append((f.copy(), d.copy(), score, dict(source=label, reuse_threshold=threshold, gain_scale=scale)))
    if not candidates:
        raise ValueError('No complete wrap-free Q3 seed fits the byte budget')
    return min(candidates, key=lambda item:-item[2]['objective']), [dict(settings=item[3], score=item[2]) for item in candidates]


def build(output, f, d, tilt, avr_bin, node):
    spec = importlib.util.spec_from_file_location('q3_private_builder', ROOT/'tools/build-hq4-oneshot.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    profile = CODEC/'q3-oneshot'/('hq4-t1.S' if tilt else 'hq4.S')
    builder.TEMPLATE = profile
    builder.decode = lambda frames, durations, keep_phase=0: render(frames, durations, tilt)[0]
    report = builder.build('hq4-q3', output, avr_bin, node, stream=output.parent/'speech.hq', expected_samples=int(d.sum()))
    paths = (profile, CODEC/'hq4_q3.py', Path(__file__))
    report['q3Profile'] = dict(tilt_shift=tilt, code_bytes=420 if tilt else 408,
        sourcesSha256NormalizedLf={path.relative_to(ROOT).as_posix():hashlib.sha256(
            path.read_text(encoding='utf-8').encode()).hexdigest() for path in paths})
    (output/'build.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--stream', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--proposals', type=int, default=6000)
    p.add_argument('--seed', type=int, default=23173)
    p.add_argument('--tilt-shift', type=int, choices=(0, 1), default=0)
    p.add_argument('--spectrogram', action='store_true', help='Fit fine ridges and broad spectral envelopes jointly')
    p.add_argument('--resume-model', type=Path, help='Optional already-Q3 model; never infer Q3 from a Q4 stream')
    p.add_argument('--stream-budget', type=int, help='Optional smaller speech budget for a composite decoder')
    p.add_argument('--build', action='store_true')
    p.add_argument('--avr-bin', type=Path)
    p.add_argument('--node', default='node')
    a = p.parse_args()
    reference, sr = sf.read(a.reference)
    if sr != 7500 or reference.ndim != 1 or a.proposals < 0:
        p.error('Expected mono 7500-Hz reference and nonnegative proposal count')
    old_f, old_d = unpack_stream(a.stream.read_bytes())
    if int(old_d.sum()) != len(reference):
        p.error('Full reference and input stream sample counts must agree')
    objective = SpectralObjective(reference)
    if a.spectrogram:
        objective.spectrogram_objective = SpectrogramObjective(reference)
    budget = 603 if a.tilt_shift else 615
    if a.stream_budget is not None:
        if not 8 <= a.stream_budget <= budget:
            p.error('Stream budget must fit this Q3 profile')
        budget = a.stream_budget
    resume = None
    if a.resume_model:
        saved = json.loads(a.resume_model.read_text(encoding='utf-8'))
        if saved.get('schema') != 'hq4-q3-v1' or saved.get('tilt_shift') != a.tilt_shift:
            p.error('Resume requires an explicitly matching Q3 profile')
        resume = np.array(saved['frames'], np.uint8), np.array(saved['durations'], np.uint16)
        if int(resume[1].sum()) != len(reference):
            p.error('Resume model must preserve the complete reference')
    initial, trials = initial_models(reference, old_f, old_d, a.tilt_shift, budget, objective, resume)
    f, d, first, settings = initial
    best, current = (f, d, first), (f, d, first)
    rng = random.Random(a.seed)
    history = []
    for i in range(a.proposals):
        anchor = best if rng.random() < .7 else current
        nf, nd = proposal(anchor[0], anchor[1], rng)
        score = evaluate(objective, nf, nd, a.tilt_shift, budget)
        if score is None:
            continue
        if score['objective'] > best[2]['objective']:
            best = nf.copy(), nd.copy(), score.copy()
            history.append(dict(proposal=i+1, **score))
        delta = score['objective']-current[2]['objective']
        temperature = .0015*(.1**((i % 1500)/1499))
        if delta > 0 or rng.random() < math.exp(max(-700., min(0., delta/temperature))):
            current = nf, nd, score
        if (i+1) % 1500 == 0:
            current = best
            print(json.dumps(dict(proposal=i+1, **best[2])), flush=True)
    f, d, score = best
    score = evaluate(objective, f, d, a.tilt_shift, budget, True)
    pcm = render(f, d, a.tilt_shift)[0]
    baseline = decode(old_f, old_d, 0)
    before = (baseline.astype(float)-128)/128
    baseline_metrics = dict(**objective.spectrum(before), stoi=float(stoi(reference, before, 7500)),
                            estoi=deterministic_estoi(reference, before, 7500))
    a.output.mkdir(parents=True, exist_ok=True)
    model = dict(schema='hq4-q3-v1', sample_rate=sr, samples=len(reference), coefficient_scale=8,
                 coefficient_range=[-7, 7], tilt_shift=a.tilt_shift, frames=f.tolist(), durations=d.tolist())
    report = dict(reference_sha256=hashlib.sha256(a.reference.read_bytes()).hexdigest(),
                  input_stream_sha256=hashlib.sha256(a.stream.read_bytes()).hexdigest(), seed=a.seed,
                  proposals=a.proposals, baseline=baseline_metrics, initial=first, settings=settings,
                  final=score, trials=trials, history=history, avr_assembled=False,
                  objective='stoi - .35*spectrogram_loss' if a.spectrogram else 'stoi - .18*legacy_spectral_loss')
    paths = (Path(__file__), CODEC/'hq4_q3.py', CODEC/'spectrogram_objective.py',
             CODEC/'new_hq4_encoder.py', CODEC/'hq4_speech_search.py')
    report['sources_sha256_normalized_lf'] = {path.relative_to(ROOT).as_posix():hashlib.sha256(
        path.read_text(encoding='utf-8').encode()).hexdigest() for path in paths}
    for name, value in [('model.json', model), ('quality.json', report)]:
        (a.output/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8', newline='\n')
    (a.output/'speech.hq').write_bytes(pack_stream(f, d))
    (a.output/'expected.raw').write_bytes(pcm.tobytes())
    signals = [reference, before, (pcm.astype(float)-128)/128]
    signals = [sosfilt(objective.hp, x) for x in signals]
    signals = [x*objective.rms/(np.sqrt(np.mean(x*x))+1e-10) for x in signals]
    scale = .85/max(float(np.max(abs(x))) for x in signals)
    for name, x in zip(('original', 'before', 'after'), signals):
        sf.write(a.output/(name+'.wav'), x*scale, sr, subtype='PCM_16')
    sf.write(a.output/'comparison.wav', np.concatenate([part for j in (0, 1, 0, 2) for part in (signals[j]*scale, np.zeros(2250))]), sr, subtype='PCM_16')
    if a.build:
        report['build'] = build(a.output/'avr', f, d, a.tilt_shift, a.avr_bin, a.node)
        if report['build']['status'] != 'verified':
            raise ValueError('Q3 AVR image did not pass all three-engine checks')
        report['avr_assembled'] = True
        (a.output/'quality.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(score), flush=True)


if __name__ == '__main__':
    main()

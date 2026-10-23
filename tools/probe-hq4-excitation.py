"""Bounded joint fitting of voiced HQ4 pulse width and exact lattice parameters."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import sys

import numpy as np
import soundfile as sf
from pystoi import stoi
from scipy.signal import sosfilt

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from hq4_core import pack_stream, unpack_stream
from hq4_excitation import decode, code_bytes
from hq4_speech_search import proposal, deterministic_estoi

spec = importlib.util.spec_from_file_location('excitation_timbre_helper', ROOT/'tools/probe-hq4-natural-timbre.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def evaluate(objective, f, d, profile):
    pcm, wraps = decode(f, d, *profile)
    x = pcm.astype(np.int16)-128
    if wraps or np.max(abs(x)) > 115 or np.any(abs(np.diff(x)) >= 48):
        return None
    audio = x.astype(float)/128
    spectral = objective.spectrum(audio)
    intelligibility = float(stoi(objective.reference, audio, 7500))
    if not math.isfinite(intelligibility):
        return None
    return dict(**spectral, stoi=intelligibility,
                balanced_score=intelligibility-.12*spectral['loss'],
                peak_signed=int(np.max(abs(x))))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', required=True, type=Path)
    p.add_argument('--stream', required=True, type=Path)
    p.add_argument('--alternate-stream', type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--proposals', type=int, default=2000, help='Proposals for each shortlisted pulse profile')
    p.add_argument('--shortlist', type=int, default=3)
    p.add_argument('--seed', type=int, default=23160)
    a = p.parse_args()
    if a.proposals < 0 or not 1 <= a.shortlist <= 12:
        p.error('Invalid bounded search size')
    ref, sr = sf.read(a.reference)
    if sr != 7500 or ref.ndim != 1:
        p.error('Reference must be mono 7500 Hz')
    objective = SpectralObjective(ref, sr)
    f, d = unpack_stream(a.stream.read_bytes())
    if d.sum() != len(ref):
        p.error('Stream must retain the complete reference')
    baseline_profile = (0, -1, 1)
    baseline = evaluate(objective, f, d, baseline_profile)
    if baseline is None:
        p.error('The current T1 stream must pass peak/discontinuity guards')
    baseline_pcm = decode(f, d, *baseline_profile)[0]
    baseline['estoi'] = deterministic_estoi(ref, (baseline_pcm.astype(float)-128)/128, sr)
    starts = [('current-t1', f, d)]
    if a.alternate_stream:
        af, ad = unpack_stream(a.alternate_stream.read_bytes())
        if ad.sum() != len(ref):
            p.error('Alternate stream has another duration')
        starts.append(('ordinary-hq4', af, ad))
    selected, trials = {}, []
    for pulse_shift in (0, 1, 2):
        for fourth in (-1, 0):
            for tilt in (0, 1):
                profile = pulse_shift, fourth, tilt
                budget = 1024-code_bytes(*profile)-1
                for source, f, d in starts:
                    compressed = helper.fit_rate(f, d, budget)
                    for gain_scale in (.5, .75, 1., 1.25):
                        trial = compressed.copy()
                        trial[:, 1] = (trial[:, 1] & 48) | np.minimum(15, np.rint((trial[:, 1] & 15)*gain_scale)).astype(np.uint8)
                        score = evaluate(objective, trial, d, profile)
                        trials.append(dict(profile=profile, source=source, gain_scale=gain_scale, score=score))
                        if score is not None and (profile not in selected or score['balanced_score'] > selected[profile][2]['balanced_score']):
                            selected[profile] = trial, d.copy(), score
    ranked = sorted(selected, key=lambda profile: selected[profile][2]['balanced_score'], reverse=True)
    # The unchanged-width control remains in the audit, but cannot consume all
    # candidate search slots merely because it starts with trained coefficients.
    shortlist = [profile for profile in ranked if profile[0] or profile[1] == 0][:a.shortlist]
    results = []
    for index, profile in enumerate(shortlist):
        best = selected[profile]
        current = best
        rng = random.Random(a.seed+index)
        budget = 1024-code_bytes(*profile)-1
        history = []
        for step in range(a.proposals):
            anchor = best if rng.random() < .65 else current
            trial, durations = proposal(anchor[0], anchor[1], rng)
            if len(pack_stream(trial, durations)) > budget:
                continue
            score = evaluate(objective, trial, durations, profile)
            if score is None:
                continue
            delta = score['balanced_score']-current[2]['balanced_score']
            temperature = .0015*(.05**((step % 1500)/1499))
            if delta > 0 or rng.random() < math.exp(max(-700, delta/temperature)):
                current = trial, durations, score
            if score['balanced_score'] > best[2]['balanced_score']:
                best = trial.copy(), durations.copy(), score
                history.append(dict(proposal=step+1, **score))
            if (step+1) % 1000 == 0:
                print(json.dumps(dict(profile=profile, proposals=step+1, score=best[2])), flush=True)
        selected[profile] = best
        f, d, score = best
        pcm = decode(f, d, *profile)[0]
        score['estoi'] = deterministic_estoi(ref, (pcm.astype(float)-128)/128, sr)
        score['stream_bytes'] = len(pack_stream(f, d))
        score['estimated_flash_bytes'] = (code_bytes(*profile)+score['stream_bytes']+2)//2*2
        results.append(dict(profile=profile, score=score, history=history))
        directory = a.output/('pulse%d-fourth%d-tilt%d'%profile)
        directory.mkdir(parents=True, exist_ok=True)
        (directory/'speech.hq').write_bytes(pack_stream(f, d))
        (directory/'expected.raw').write_bytes(pcm.tobytes())
        model = dict(schema='hq4-excitation-v1', profile=profile, samples=len(ref), sample_rate=sr,
                     frames=f.tolist(), durations=d.tolist(), score=score)
        (directory/'model.json').write_text(json.dumps(model, indent=2)+'\n', encoding='utf-8')
        audio = (pcm.astype(float)-128)/128
        sf.write(directory/'decoded.wav', audio, sr, subtype='PCM_16')
        control = (decode(*starts[0][1:], *baseline_profile)[0].astype(float)-128)/128
        matched = [sosfilt(objective.hp, x) for x in (ref, control, audio)]
        matched = [x*objective.rms/(np.sqrt(np.mean(x*x))+1e-10) for x in matched]
        scale = .85/max(float(np.max(abs(x))) for x in matched)
        gap = np.zeros(round(.3*sr))
        for name, x in zip(('original-matched', 'before-matched', 'after-matched'), matched):
            sf.write(directory/(name+'.wav'), x*scale, sr, subtype='PCM_16')
        sf.write(directory/'comparison.wav', np.concatenate([v for x in matched for v in (x*scale, gap)]), sr, subtype='PCM_16')
    a.output.mkdir(parents=True, exist_ok=True)
    feasible = [x for x in results if
                x['score']['stoi'] >= baseline['stoi']-1e-12 and
                x['score']['estoi'] >= baseline['estoi']-1e-12 and
                x['score']['loss'] < baseline['loss']-1e-12 and
                x['score']['log_spectral_error'] <= baseline['log_spectral_error']+1e-12]
    sources = [Path(__file__), CODEC/'hq4_excitation.py', CODEC/'model.py', CODEC/'hq4_core.py',
               CODEC/'auto_encoder.py', CODEC/'hq4_speech_search.py',
               ROOT/'tools/probe-hq4-natural-timbre.py']
    report = dict(schema='hq4-excitation-search-v1', baseline_t1=baseline, initial_trials=trials,
                  results=results, proposals_per_profile=a.proposals, seed=a.seed,
                  reference_sha256=hashlib.sha256(a.reference.read_bytes()).hexdigest(),
                  input_stream_sha256=hashlib.sha256(a.stream.read_bytes()).hexdigest(),
                  selected_profile=max(feasible, key=lambda x: x['score']['balanced_score'])['profile'] if feasible else baseline_profile,
                  candidate_accepted=bool(feasible), avr_qualified=False,
                  source_sha256_normalized_lf={str(path.relative_to(ROOT)).replace('\\', '/'):
                      hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest() for path in sources},
                  hardware_tested=False, human_listening_verified=False)
    (a.output/'quality.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(stage='complete', baseline=baseline,
                         results=[dict(profile=x['profile'], score=x['score']) for x in results])), flush=True)


if __name__ == '__main__':
    main()

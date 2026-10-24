"""Matched-seed ablation of partial-frequency and partial-amplitude fitting.

Three profiles share the same frozen Q3 model, byte budget, proposal schedule,
and eligibility guards. Only the frequency/amplitude objective weights change.
No decoder or retained fitter is edited by this experiment.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import sys
import time

import numpy as np
from scipy.signal import sosfilt
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from hq4_core import pack_stream
from hq4_q3 import render
from hq4_speech_search import proposal

_spec = importlib.util.spec_from_file_location('frozen_q3_track_fit', ROOT/'tools/probe-hq4-q3-tracks.py')
frozen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(frozen)

PROFILES = {'frequency-priority': (1., 0.), 'amplitude-priority': (0., 1.), 'balanced': (.5, .5)}


def ratio(score, baseline, key):
    return score[key]/max(baseline[key], 1e-12)


def difference(score, baseline, weights):
    spectrum = ratio(score, baseline, 'spectrogram_loss')
    frequency = (.7*ratio(score, baseline, 'frequency_trajectory_error')
                 +.15*ratio(score, baseline, 'missing_reference_energy')
                 +.15*ratio(score, baseline, 'extra_candidate_energy'))
    amplitude = ratio(score, baseline, 'level_error')
    return .5*spectrum+.5*(weights[0]*frequency+weights[1]*amplitude)


def feasible(score, baseline):
    # Combined harmonic loss is deliberately absent: freezing it would mix the
    # two independent factors that this experiment is intended to compare.
    return (all(score[key]+1e-12 >= baseline[key] for key in frozen.FLOORS+frozen.TRACK_FLOORS)
            and all(score[key] <= baseline[key]+1e-12 for key in frozen.COMPONENTS+frozen.TRACK_CEILINGS))


def energy(score, baseline, weights):
    penalty = 8*sum(max(0., baseline[key]-score[key]) for key in frozen.FLOORS)
    penalty += 4*sum(max(0., score[key]-baseline[key]) for key in frozen.COMPONENTS+frozen.TRACK_CEILINGS)
    penalty += 4*sum(max(0., baseline[key]-score[key]) for key in frozen.TRACK_FLOORS)
    return difference(score, baseline, weights)+penalty


def schedule(seed, proposals):
    """Per-step seeds/draws never depend on acceptance or profile weights."""
    rng = random.Random(seed)
    return [(rng.getrandbits(64), rng.random(), rng.random(), rng.getrandbits(64))
            for _ in range(proposals)]


def fit(objective, frames, durations, baseline, weights, plan):
    best = frames.copy(), durations.copy(), baseline.copy()
    current = best
    history = []
    evaluated = accepted_working = eligible = changed_proposals = 0
    for step, (proposal_seed, anchor_draw, acceptance_draw, reuse_seed) in enumerate(plan):
        anchor = best if anchor_draw < .65 else current
        f, d = proposal(anchor[0], anchor[1], random.Random(proposal_seed))
        reuse_rng = random.Random(reuse_seed)
        if reuse_rng.random() < .12 and len(f) > 1:
            i = reuse_rng.randrange(1, len(f))
            half = slice(2, 4) if reuse_rng.randrange(2) else slice(4, 6)
            f[i, half] = f[i-1, half]
        changed_proposals += int(not (np.array_equal(f, anchor[0]) and np.array_equal(d, anchor[1])))
        score = objective.evaluate(f, d)
        if score is not None:
            evaluated += 1
            valid = feasible(score, baseline)
            eligible += int(valid)
            if valid and difference(score, baseline, weights) < difference(best[2], baseline, weights)-1e-12:
                best = f.copy(), d.copy(), score.copy()
                history.append(dict(proposal=step+1, objective=difference(score, baseline, weights), **score))
            temperature = .004*(.1**((step % 1500)/1499))
            delta = energy(score, baseline, weights)-energy(current[2], baseline, weights)
            if delta < 0 or acceptance_draw < math.exp(max(-700., min(0., -delta/temperature))):
                current = f, d, score
                accepted_working += 1
        if (step+1) % 1500 == 0:
            current = best
    return best, dict(evaluated_proposals=evaluated, eligible_proposals=eligible,
                      changed_proposals=changed_proposals, accepted_working_proposals=accepted_working,
                      accepted_elites=len(history), history=history)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', required=True, type=Path)
    p.add_argument('--model', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--proposals', default=1500, type=int, help='Equal proposal count for each profile')
    p.add_argument('--seed', default=23213, type=int)
    p.add_argument('--stream-budget', default=430, type=int)
    p.add_argument('--harmonic-tracks', default=10, type=int)
    a = p.parse_args()
    reference, sr = sf.read(a.reference)
    model = json.loads(a.model.read_text(encoding='utf-8'))
    if (sr != 7500 or reference.ndim != 1 or a.proposals < 0 or not 1 <= a.harmonic_tracks <= 10
            or model.get('schema') != 'hq4-q3-v1' or model.get('tilt_shift') not in (0, 1)):
        p.error('Expected complete mono7500 Q3 model and valid proposal/track counts')
    frames = np.asarray(model['frames'], np.uint8)
    durations = np.asarray(model['durations'], np.uint16)
    tilt = model['tilt_shift']
    if not 8 <= a.stream_budget <= (603 if tilt else 615) or int(durations.sum()) != len(reference):
        p.error('Invalid Q3 byte budget or changed complete reference duration')
    objective = frozen.Objective(reference, tilt, a.stream_budget, a.harmonic_tracks)
    baseline = objective.evaluate(frames, durations)
    if baseline is None:
        p.error('Frozen baseline fails physical decoder or byte guards')
    plan = schedule(a.seed, a.proposals)
    sha = lambda data: hashlib.sha256(data).hexdigest()
    a.output.mkdir(parents=True, exist_ok=True)
    sources = (Path(__file__), ROOT/'tools/probe-hq4-q3-tracks.py', CODEC/'harmonic_tracks.py',
               CODEC/'spectrogram_objective.py', CODEC/'hq4_q3.py', CODEC/'hq4_speech_search.py',
               CODEC/'hq4_core.py', CODEC/'auto_encoder.py')
    report = dict(schema='hq4-q3-influence-v1', input_model_sha256=sha(a.model.read_bytes()),
        reference_sha256=sha(a.reference.read_bytes()), samples=len(reference), stream_budget=a.stream_budget,
        seed=a.seed, proposals_per_profile=a.proposals,
        proposal_schedule_sha256=sha(json.dumps(plan, separators=(',', ':')).encode()),
        schedule_policy='One shared list of per-step proposal/reuse seeds and anchor/acceptance draws; score-dependent branching cannot advance the schedule',
        baseline=baseline, harmonic_track_config=objective.tracks.config,
        objective='0.5*spectrum/base_spectrum + 0.5*(wf*frequency_component + wa*level/base_level)',
        frequency_component='.7*trajectory/base_trajectory + .15*missing/base_missing + .15*extra/base_extra',
        guard_policy='Frozen STOI/eSTOI, four spectral components, coverage, missing/extra, continuity; combined harmonic loss is not a guard',
        human_listening_verified=False, hardware_tested=False, avr_assembled=False,
        sources_sha256_normalized_lf={path.relative_to(ROOT).as_posix():sha(path.read_text(encoding='utf-8').encode()) for path in sources},
        profiles={})
    decoded = [render(frames, durations, tilt)[0]]
    for name, weights in PROFILES.items():
        started = time.perf_counter()
        best, counters = fit(objective, frames, durations, baseline, weights, plan)
        f, d, score = best
        pcm = render(f, d, tilt)[0]
        payload = pack_stream(f, d)
        dest = a.output/name
        dest.mkdir(parents=True, exist_ok=True)
        final_model = dict(model, frames=f.tolist(), durations=d.tolist(), influence_profile=name)
        (dest/'model.json').write_text(json.dumps(final_model, indent=2)+'\n', encoding='utf-8', newline='\n')
        (dest/'speech.hq').write_bytes(payload)
        (dest/'expected.raw').write_bytes(pcm.tobytes())
        sf.write(dest/'decoded.wav', (pcm.astype(float)-128)/128, 7500, subtype='PCM_16')
        info = dict(frequency_weight=weights[0], amplitude_weight=weights[1], final=score,
                    normalized_objective=difference(score, baseline, weights),
                    changed=payload != pack_stream(frames, durations), selected_is_feasible=feasible(score, baseline),
                    stream_bytes=len(payload), stream_sha256=sha(payload), pcm_sha256=sha(pcm.tobytes()),
                    raw_audio_sha256=sha((dest/'decoded.wav').read_bytes()),
                    elapsed_seconds=time.perf_counter()-started, **counters)
        report['profiles'][name] = info
        decoded.append(pcm)
        print(json.dumps(dict(profile=name, **info)), flush=True)
    presentation = SpectralObjective(reference)
    signals = [reference]+[(pcm.astype(float)-128)/128 for pcm in decoded]
    signals = [sosfilt(presentation.hp, value) for value in signals]
    signals = [value*presentation.rms/(np.sqrt(np.mean(value*value))+1e-20) for value in signals]
    scale = .85/max(float(np.max(abs(value))) for value in signals)
    for name, value in zip(('original', 'baseline')+tuple(PROFILES), signals):
        dest = a.output/(name+'-matched.wav')
        sf.write(dest, value*scale, 7500, subtype='PCM_16')
        if name in report['profiles']:
            report['profiles'][name]['matched_audio_sha256'] = sha(dest.read_bytes())
    sf.write(a.output/'comparison.wav', np.concatenate([part for value in signals for part in (value*scale, np.zeros(2250))]), 7500, subtype='PCM_16')
    report['comparison_audio_sha256'] = sha((a.output/'comparison.wav').read_bytes())
    report['unique_evaluated_streams'] = len(objective.cache)
    (a.output/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()

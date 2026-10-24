"""Refit a frozen Q3 model against original-derived harmonic trajectories.

All decoder parameters remain searchable. Intelligibility is a hard guard;
the optimization target is original/output difference, not a larger STOI score.
No changes are made to the previous Q3 fitter or its retained model files.
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
from pystoi import stoi
from scipy.signal import sosfilt
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from harmonic_tracks import HarmonicTrackObjective
from hq4_core import pack_stream
from hq4_q3 import render
from hq4_speech_search import deterministic_estoi, proposal
from spectrogram_objective import SpectrogramObjective

COMPONENTS = ('fine_log_error', 'envelope_error', 'unsupported_energy', 'missing_energy')
FLOORS = ('stoi', 'estoi')
TRACK_CEILINGS = ('missing_reference_energy', 'extra_candidate_energy', 'continuity_break_rate')
TRACK_FLOORS = ('weighted_match_rate',)


def feasible(score, baseline):
    return (all(score[key]+1e-12 >= baseline[key] for key in FLOORS+TRACK_FLOORS)
            and all(score[key] <= baseline[key]+1e-12 for key in COMPONENTS+TRACK_CEILINGS)
            and score['harmonic_track_loss'] <= baseline['harmonic_track_loss']+1e-12)


def working_energy(score, baseline):
    """Infeasible working states can cross barriers; exported elites cannot."""
    penalty = 8*sum(max(0., baseline[key]-score[key]) for key in FLOORS)
    penalty += 4*sum(max(0., score[key]-baseline[key]) for key in COMPONENTS+TRACK_CEILINGS)
    penalty += 4*sum(max(0., baseline[key]-score[key]) for key in TRACK_FLOORS)
    return score['difference_loss']+penalty


class Objective:
    def __init__(self, reference, tilt_shift, budget, max_tracks):
        self.reference = np.asarray(reference, float)
        self.tilt_shift, self.budget = tilt_shift, budget
        self.spectral = SpectrogramObjective(reference)
        self.tracks = HarmonicTrackObjective(reference, max_tracks=max_tracks)
        self.cache = {}

    def evaluate(self, frames, durations):
        payload = pack_stream(frames, durations)
        if (int(durations.sum()) != len(self.reference) or len(payload) > self.budget
                or np.any((frames[:, 2:]&15) == 0) or np.any((frames[:, 2:]>>4) == 0)):
            return None
        if payload in self.cache:
            return self.cache[payload]
        pcm, wraps = render(frames, durations, self.tilt_shift)
        if np.any(wraps):
            return None
        signed = pcm.astype(np.int16)-128
        if np.max(abs(signed)) > 115 or np.any(abs(np.diff(signed)) >= 48):
            return None
        audio = signed.astype(float)/128
        spectrum = self.spectral.evaluate(audio)
        tracks = self.tracks.evaluate(audio)
        st = float(stoi(self.reference, audio, 7500))
        est = deterministic_estoi(self.reference, audio, 7500)
        if not math.isfinite(st) or not math.isfinite(est):
            return None
        result = dict(**spectrum, **tracks, stoi=st, estoi=est,
                    difference_loss=.5*(spectrum['spectrogram_loss']+tracks['harmonic_track_loss']),
                    stream_bytes=len(payload),
                    peak_signed=int(np.max(abs(signed))), steps_ge_48=0,
                    intermediate_wraps=wraps.tolist())
        self.cache[payload] = result
        return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--proposals', type=int, default=4000)
    p.add_argument('--seed', type=int, default=23193)
    p.add_argument('--harmonic-tracks', type=int, default=10, help='Maximum strongest partials per time frame, 1 through 10')
    p.add_argument('--stream-budget', type=int)
    p.add_argument('--build', action='store_true')
    p.add_argument('--avr-bin', type=Path)
    p.add_argument('--node', default='node')
    a = p.parse_args()
    if a.proposals < 0 or not 1 <= a.harmonic_tracks <= 10:
        p.error('Expected nonnegative proposal count and 1 through 10 tracks')
    reference, sr = sf.read(a.reference)
    if sr != 7500 or reference.ndim != 1:
        p.error('Expected mono 7500-Hz audio')
    model = json.loads(a.model.read_text(encoding='utf-8'))
    if model.get('schema') != 'hq4-q3-v1' or model.get('tilt_shift') not in (0, 1):
        p.error('Expected an explicitly identified supported Q3 model')
    frames = np.asarray(model['frames'], np.uint8)
    durations = np.asarray(model['durations'], np.uint16)
    tilt = model['tilt_shift']
    budget = 603 if tilt else 615
    if a.stream_budget is not None:
        if not 8 <= a.stream_budget <= budget:
            p.error('Invalid Q3 stream budget')
        budget = a.stream_budget
    if int(durations.sum()) != len(reference):
        p.error('Frozen model must preserve the complete reference duration')
    objective = Objective(reference, tilt, budget, a.harmonic_tracks)
    baseline = objective.evaluate(frames, durations)
    if baseline is None:
        p.error('Frozen model fails exact arithmetic, sample, or byte guards')
    best = frames.copy(), durations.copy(), baseline.copy()
    current = best
    rng = random.Random(a.seed)
    history = []
    evaluated = accepted_working = feasible_candidates = 0
    started = time.perf_counter()
    for step in range(a.proposals):
        anchor = best if rng.random() < .65 else current
        f, d = proposal(anchor[0], anchor[1], rng)
        # Existing coefficient-half sharing remains a rate-aware option; no
        # pitch, harmonic frequency, or coefficient is chosen manually.
        if rng.random() < .12 and len(f) > 1:
            i = rng.randrange(1, len(f))
            half = slice(2, 4) if rng.randrange(2) else slice(4, 6)
            f[i, half] = f[i-1, half]
        score = objective.evaluate(f, d)
        if score is not None:
            evaluated += 1
            is_feasible = feasible(score, baseline)
            feasible_candidates += int(is_feasible)
            if is_feasible and score['difference_loss'] < best[2]['difference_loss']-1e-12:
                best = f.copy(), d.copy(), score.copy()
                history.append(dict(proposal=step+1, **score))
            temperature = .004*(.1**((step % 1500)/1499))
            delta = working_energy(score, baseline)-working_energy(current[2], baseline)
            if delta < 0 or rng.random() < math.exp(max(-700., min(0., -delta/temperature))):
                current = f, d, score
                accepted_working += 1
        if (step+1) % 1500 == 0:
            current = best
            print(json.dumps(dict(proposal=step+1, elapsed_seconds=time.perf_counter()-started, best=best[2])), flush=True)
    f, d, score = best
    pcm = render(f, d, tilt)[0]
    a.output.mkdir(parents=True, exist_ok=True)
    payload = pack_stream(f, d)
    sha = lambda data: hashlib.sha256(data).hexdigest()
    final_model = dict(model, frames=f.tolist(), durations=d.tolist())
    final_model['fit_objective'] = 'mean of spectrogram_loss and harmonic_track_loss; guarded intelligibility'
    sources = (Path(__file__), CODEC/'harmonic_tracks.py', CODEC/'spectrogram_objective.py',
               CODEC/'hq4_q3.py', CODEC/'hq4_speech_search.py')
    report = dict(schema='hq4-q3-tracks-fit-v1', reference_sha256=sha(a.reference.read_bytes()),
                  input_model_sha256=sha(a.model.read_bytes()), baseline=baseline, final=score,
                  proposals=a.proposals, seed=a.seed, harmonic_tracks=a.harmonic_tracks,
                  harmonic_track_config=objective.tracks.config,
                  stream_budget=budget, stream_bytes=len(payload), stream_sha256=sha(payload),
                  pcm_sha256=sha(pcm.tobytes()), evaluated=evaluated,
                  feasible_candidates=feasible_candidates, accepted_working_states=accepted_working,
                  accepted_elites=len(history), history=history, elapsed_seconds=time.perf_counter()-started,
                  selected_is_feasible=feasible(score, baseline),
                  changed=payload != pack_stream(frames, durations),
                  objective='difference_loss = .5*(spectrogram_loss + harmonic_track_loss)',
                  intelligibility_policy='STOI and eSTOI are frozen-baseline hard floors, not reward terms',
                  working_states='May violate matching/intelligibility/spectral guards; never exported as elites',
                  candidate_requirements=list(FLOORS+TRACK_FLOORS)+list(COMPONENTS+TRACK_CEILINGS)+['harmonic_track_loss'],
                  human_listening_verified=False, hardware_tested=False, avr_assembled=False,
                  sources_sha256_normalized_lf={path.relative_to(ROOT).as_posix():sha(path.read_text(encoding='utf-8').encode()) for path in sources})
    for name, value in [('model.json', final_model), ('quality.json', report)]:
        (a.output/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8', newline='\n')
    (a.output/'speech.hq').write_bytes(payload)
    (a.output/'expected.raw').write_bytes(pcm.tobytes())
    sf.write(a.output/'decoded.wav', (pcm.astype(float)-128)/128, 7500, subtype='PCM_16')
    presentation = SpectralObjective(reference)
    before = render(frames, durations, tilt)[0]
    signals = [reference, (before.astype(float)-128)/128, (pcm.astype(float)-128)/128]
    signals = [sosfilt(presentation.hp, value) for value in signals]
    signals = [value*presentation.rms/(np.sqrt(np.mean(value*value))+1e-20) for value in signals]
    scale = .85/max(float(np.max(abs(value))) for value in signals)
    for name, value in zip(('original', 'before', 'after'), signals):
        sf.write(a.output/(name+'-matched.wav'), value*scale, 7500, subtype='PCM_16')
    sf.write(a.output/'comparison.wav', np.concatenate([part for value in signals for part in (value*scale, np.zeros(2250))]), 7500, subtype='PCM_16')
    if a.build:
        spec = importlib.util.spec_from_file_location('q3_frozen_builder', ROOT/'tools/probe-hq4-q3.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        built = builder.build(a.output/'avr', f, d, tilt, a.avr_bin, a.node)
        if built['status'] != 'verified':
            raise ValueError('Track-fit Q3 image failed exact AVR qualification')
        report['avr_assembled'] = True
        report['build_report'] = 'avr/build.json'
        (a.output/'quality.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(changed=report['changed'], baseline=baseline, final=score)), flush=True)


if __name__ == '__main__':
    main()

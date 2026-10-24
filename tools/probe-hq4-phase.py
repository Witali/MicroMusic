"""Audit and refit a separate 406-byte continuous-phase HQ4 experiment.

No public model or existing decoder is replaced. A lower spectral loss alone
does not qualify the candidate for promotion over its legacy speech baseline.
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
import soundfile as sf
from pystoi import stoi
from scipy.signal import butter, sosfilt

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from hq4_phase import audit, decode, render
from hq4_core import pack_stream, unpack_stream
from auto_encoder import SpectralObjective
from hq4_speech_search import deterministic_estoi, proposal, validate


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_case(case):
    if case == 'vinni':
        path = ROOT/'ATtiny13A/Sound/codec/release/vinni/speech.hq'
        frames, durations = unpack_stream(path.read_bytes())
        reference_path = ROOT.parent.parent/'build/hq4-preview/vinni/original.wav'
        reference, sr = sf.read(reference_path, dtype='float64')
    else:
        path = ROOT/'build/new-speech/bell-hybrid/voice-model.json'
        model = json.loads(path.read_text(encoding='utf-8'))
        frames, durations = np.asarray(model['frames'], np.uint8), np.asarray(model['durations'], np.uint16)
        reference_path = ROOT/'build/new-speech/tail-input/vhodit-i-vyhodit/reference.wav'
        reference, sr = sf.read(reference_path, dtype='float64')
        reference = reference[int(model['voice_offset_samples']):]
    if sr != 7500 or int(np.sum(durations)) != len(reference):
        raise ValueError('Model and reference duration/sample rate differ')
    return reference, frames, durations, dict(input_model=str(path.relative_to(ROOT)),
        input_model_sha256=sha(path.read_bytes()), reference_sha256=sha(reference_path.read_bytes()),
        samples=len(reference))


def roughness(audio):
    return float(np.sqrt(np.mean(np.diff(audio)**2))/(np.sqrt(np.mean(audio**2))+1e-12))


class Objective(SpectralObjective):
    def __init__(self, reference):
        super().__init__(reference)
        self.reference_roughness = roughness(reference)

    def evaluate(self, f, d, continuous=True, full=False):
        pcm, _, _, _, counts = render(f, d, continuous)
        if counts[0] or counts[1] or counts[2]:
            return None
        signed = pcm.astype(np.int16)-128
        peak = int(np.max(abs(signed)))
        steps = int(np.sum(abs(np.diff(signed)) >= 48))
        if peak > 115 or steps:
            return None
        audio = signed.astype(float)/128
        spectrum = self.spectrum(audio)
        intelligibility = float(stoi(self.reference, audio, 7500))
        if not math.isfinite(intelligibility):
            return None
        r = roughness(audio)
        difference = abs(math.log(max(r, 1e-9)/max(self.reference_roughness, 1e-9)))
        result = dict(stoi=intelligibility, **spectrum, peak_signed=peak, steps_ge_48=steps,
                      roughness=r, reference_roughness=self.reference_roughness,
                      roughness_log_error=difference,
                      objective=intelligibility-.1*spectrum['loss']-.015*difference,
                      stream_bytes=len(pack_stream(f, d)))
        if full:
            result['estoi'] = deterministic_estoi(self.reference, audio, 7500)
            result['mean_signed'] = float(np.mean(signed))
            result['rms_to_reference_ratio'] = float(np.sqrt(np.mean(audio**2))/np.sqrt(np.mean(self.reference**2)))
            frequencies = np.fft.rfftfreq(len(audio), 1/7500)
            high = frequencies >= 2500
            for name, signal in [('reference', self.reference), ('decoded', audio)]:
                power = abs(np.fft.rfft(signal-np.mean(signal)))**2
                result[name+'_high_frequency_power_fraction'] = float(np.sum(power[high])/max(np.sum(power), 1e-20))
        return result


def search(reference, frames, durations, proposals, seed, budget):
    objective = Objective(reference)
    baseline = objective.evaluate(frames, durations, continuous=False, full=True)
    first = objective.evaluate(frames, durations, continuous=True, full=True)
    if baseline is None or first is None:
        raise ValueError('Starting model exceeds safety/step constraints')
    rng = random.Random(seed)
    best = frames.copy(), durations.copy(), first.copy()
    current = best
    evaluated = improvements = 0
    history = []
    for i in range(proposals):
        if i % 1000 == 0:
            current = best
        anchor = best if rng.random() < .7 else current
        f, d = proposal(anchor[0], anchor[1], rng)
        if rng.random() < .15 and len(f) > 1:
            j, half = rng.randrange(1, len(f)), rng.choice((slice(2, 4), slice(4, 6)))
            f[j, half] = f[j-1, half]
        try:
            stream = validate(f, d, len(reference))
        except ValueError:
            continue
        if len(stream) > budget:
            continue
        evaluated += 1
        score = objective.evaluate(f, d)
        if score is None:
            continue
        # Search can recover the original model's intelligibility without
        # allowing a spectrally improved but less intelligible elite than its
        # own continuous-phase initialization.
        if (score['stoi'] >= first['stoi'] and score['loss'] <= first['loss']*1.03
                and score['objective'] > best[2]['objective']+1e-10):
            best = f.copy(), d.copy(), score.copy()
            improvements += 1
            history.append(dict(proposal=i+1, **score))
        temperature = .002*(.05**((i % 1000)/999))
        delta = score['objective']-current[2]['objective']
        if delta > 0 or rng.random() < math.exp(max(-700., min(0., delta/temperature))):
            current = f, d, score
        if (i+1) % 1000 == 0:
            print(json.dumps(dict(proposal=i+1, best=best[2])), flush=True)
    final = objective.evaluate(best[0], best[1], full=True)
    qualifies = (final['stoi'] >= baseline['stoi'] and final['estoi'] >= baseline['estoi']
                 and final['loss'] <= baseline['loss'] and final['roughness_log_error'] <= baseline['roughness_log_error'])
    return best[0], best[1], dict(baseline=baseline, initial=first, final=final,
        proposals=proposals, evaluated=evaluated, improvements=improvements,
        history=history, seed=seed, metric_guards_passed=bool(qualifies),
        promoted=False, note='Metric guards do not establish perceived naturalness; compare matched audio.')


def build(case, frames, durations, output, avr_bin, node):
    spec = importlib.util.spec_from_file_location('phase_build_helpers', ROOT/'tools/build-hq4-oneshot.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # A private module instance reuses the unchanged assembler/verification
    # harness with explicit alternate template and oracle; no files are edited.
    module.TEMPLATE = CODEC/'phase-oneshot/hq4.S'
    module.decode = lambda f, d, _: decode(f, d, True)
    stream = output/'speech.hq'
    stream.write_bytes(pack_stream(frames, durations))
    report = module.build('phase-'+case, output/'avr', avr_bin, node, stream, int(np.sum(durations)))
    report.update(schema='micromusic-hq4-phase-build-v1', continuousPhase=True,
                  initialCountdown='first-frame-period', promoted=False)
    for path in (CODEC/'hq4_phase.py', Path(__file__)):
        report['normalizedSourceSha256'][path.relative_to(ROOT).as_posix()] = sha(path.read_text(encoding='utf-8').encode('utf-8'))
    (output/'avr/build.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=('vinni', 'tail-voice'), required=True)
    parser.add_argument('--proposals', type=int, default=5000)
    parser.add_argument('--seed', type=int, default=23131)
    parser.add_argument('--stream-budget', type=int, default=617)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--avr-bin', type=Path)
    parser.add_argument('--node', default='node')
    parser.add_argument('--no-build', action='store_true')
    args = parser.parse_args()
    if args.proposals < 0 or not 8 <= args.stream_budget <= 617:
        raise ValueError('Invalid proposal/stream budget')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    reference, original_f, original_d, inputs = load_case(args.case)
    frames, durations, report = search(reference, original_f, original_d, args.proposals, args.seed, args.stream_budget)
    model = dict(schema='micromusic-hq4-continuous-phase-v1', frames=frames.tolist(), durations=durations.tolist(),
                 sample_rate=7500, **inputs)
    (output/'model.json').write_text(json.dumps(model, indent=2)+'\n', encoding='utf-8', newline='\n')
    report.update(inputs=inputs, audit_baseline=audit(original_f, original_d, False),
                  audit_initial=audit(original_f, original_d, True), audit_final=audit(frames, durations, True))
    (output/'quality.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    old = decode(original_f, original_d, False)
    new = decode(frames, durations, True)
    hp = butter(2, 70, fs=7500, btype='highpass', output='sos')
    tracks = [sosfilt(hp, reference), sosfilt(hp, (old.astype(float)-128)/128), sosfilt(hp, (new.astype(float)-128)/128)]
    rms = np.sqrt(np.mean(tracks[0]**2))
    tracks = [audio*rms/(np.sqrt(np.mean(audio**2))+1e-12) for audio in tracks]
    gain = min(1., .94/max(float(np.max(abs(a))) for a in tracks))
    for name, audio in zip(('original-matched', 'before-matched', 'after-matched'), tracks):
        sf.write(output/(name+'.wav'), audio*gain, 7500, subtype='PCM_16')
    sf.write(output/'comparison.wav', np.r_[tracks[0]*gain, np.zeros(2250), tracks[1]*gain,
                                           np.zeros(2250), tracks[2]*gain], 7500, subtype='PCM_16')
    if not args.no_build:
        built = build(args.case, frames, durations, output, args.avr_bin, args.node)
        print(json.dumps(dict(buildStatus=built['status'], flashBytes=built['flashBytes'])), flush=True)
        if built['status'] != 'verified':
            return 1
    print(json.dumps({k: report[k] for k in ('baseline', 'initial', 'final', 'metric_guards_passed')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

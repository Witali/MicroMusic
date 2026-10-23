"""Bounded LPC2-guided offline search for the unchanged 1 KB Q3 decoder.

LPC2 parameters suggest local moves only. Original PCM remains the target, and
the frozen incumbent's intelligibility, spectral and coverage guards decide
eligibility. Whole-trajectory transfers are retained as negative controls.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import shutil
import sys
import time

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from hq4_core import pack_stream
from hq4_q3 import render
from hq4_speech_search import proposal
from lpc2_excitation import Lpc2Bridge, default_node

_spec = importlib.util.spec_from_file_location('q3_lpc2_frozen_guards', ROOT/'tools/probe-hq4-q3-tracks.py')
frozen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(frozen)

GUARDED_KEYS = (frozen.FLOORS+frozen.TRACK_FLOORS+frozen.COMPONENTS
                +frozen.TRACK_CEILINGS+('harmonic_track_loss', 'difference_loss'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')


def console_summary(report):
    """Select existing fields without duplicating baseline from fit counters."""
    return {key: report[key] for key in ('changed', 'baseline', 'final',
        'estimated_full_flash_bytes', 'proposals', 'seed', 'counts', 'accepted_elites')}


def eligible(score, baseline):
    """Missing/nonfinite scores never pass a scalar or component guard."""
    return bool(isinstance(score, dict) and isinstance(baseline, dict)
            and all(key in score and math.isfinite(score[key]) for key in GUARDED_KEYS)
            and all(key in baseline and math.isfinite(baseline[key]) for key in GUARDED_KEYS)
            and frozen.feasible(score, baseline))


def validate_fields(frames, durations, samples):
    """Validate the common stream fields without imposing a Flash-only cap."""
    if (frames.ndim != 2 or frames.shape[1] != 6 or not len(frames)
            or durations.ndim != 1 or len(frames) != len(durations)
            or frames.dtype.kind not in 'ui' or durations.dtype.kind not in 'ui'
            or np.any(frames[:, 0] > 126) or np.any(frames[:, 1] > 63)
            or int(durations.sum()) != samples
            or any(int(n) not in (64, 128, 192, 256) for n in durations)
            or np.any((frames[:, 2:] & 15) == 0) or np.any((frames[:, 2:] >> 4) == 0)):
        raise ValueError('Invalid Q3 fields or changed complete source duration')
    return pack_stream(frames, durations)


def step_down(coefficients):
    """Convert the full stable AR polynomial to reflection coefficients."""
    values = np.asarray(coefficients, dtype=float)
    if values.ndim != 1 or not len(values) or not np.all(np.isfinite(values)):
        raise ValueError('Expected a finite nonempty AR coefficient vector excluding a0')
    a = np.r_[1., values]
    result = np.empty(len(values), dtype=float)
    for order in range(len(values), 0, -1):
        k = float(a[order])
        if abs(k) >= 1.-1e-10:
            raise ValueError('Unstable or singular LPC2 predictor cannot be a reflection prior')
        result[order-1] = k
        if order > 1:
            a = np.r_[1., (a[1:order]-k*a[order-1:0:-1])/(1-k*k)]
    return result


class Prior:
    """Source-only teacher trajectories, sampled at current Q3 frame centres."""
    def __init__(self, native, incumbent, durations):
        meta = native['meta']
        self.sr, self.hop, self.samples = int(meta['sr']), int(meta['H']), int(meta['samples'])
        self.reflections = np.asarray([step_down(a)[:8] for a in native['frameCoefficients']])
        self.f0 = np.asarray(native['frameF0'], dtype=float)
        self.gains = np.asarray(native['frameGain'], dtype=float)
        if (self.sr != 7500 or self.hop < 1 or self.reflections.shape != (len(self.f0), 8)
                or self.gains.shape != self.f0.shape or not len(self.f0)
                or len(self.f0) != math.ceil(self.samples/self.hop)
                or not np.all(np.isfinite(self.f0)) or not np.all(np.isfinite(self.gains))
                or np.any(self.f0 < 0) or np.any(self.gains < 0)
                or self.samples != int(np.sum(durations))):
            raise ValueError('LPC2 trajectory descriptor disagrees with the unchanged Q3 source')
        indices = self.indices(durations)
        gain = (np.asarray(incumbent)[:, 1] & 15).astype(float)
        mask = (gain > 0) & (self.gains[indices] > 0)
        self.gain_scale = float(np.median(gain[mask]/self.gains[indices][mask])) if np.any(mask) else 0.

    def indices(self, durations):
        durations = np.asarray(durations, dtype=int)
        if (durations.ndim != 1 or not len(durations) or np.any(durations <= 0)
                or int(durations.sum()) != self.samples):
            raise ValueError('Prior sampling must preserve every source sample')
        centres = np.cumsum(durations)-durations/2
        return np.clip((centres/self.hop).astype(int), 0, len(self.f0)-1)

    def mapped(self, durations):
        indices = self.indices(durations)
        f0 = self.f0[indices]
        periods = np.where(f0 > 0, np.clip(np.rint(self.sr/np.maximum(f0, 1.)), 1, 126), 0).astype(np.uint8)
        coefficients = np.clip(np.rint(self.reflections[indices]*8), -7, 7).astype(int)
        gains = np.clip(np.rint(self.gains[indices]*self.gain_scale), 0, 15).astype(int)
        return coefficients, periods, gains


def shared_run(frames, index, half):
    """A common half-update run can change without adding update bytes."""
    left = right = index
    while left > 0 and np.array_equal(frames[left-1, half], frames[index, half]):
        left -= 1
    while right+1 < len(frames) and np.array_equal(frames[right+1, half], frames[index, half]):
        right += 1
    return slice(left, right+1)


def soft_proposal(frames, durations, prior, rng, kind=None):
    """One quantization step toward a teacher; voicing toggles stay separate."""
    f, d = frames.copy(), durations.copy()
    coefficients, periods, gains = prior.mapped(d)
    kind = kind or rng.choices(('reflection', 'pitch', 'gain', 'voicing'), (.4, .3, .15, .15))[0]
    index = rng.randrange(len(f))
    if kind == 'reflection':
        component = rng.randrange(8)
        byte, shift = 2+component//2, 4*(component % 2)
        current = ((int(f[index, byte]) >> shift) & 15)-8
        delta = int(np.sign(int(coefficients[index, component])-current))
        target = int(np.clip(current+delta, -7, 7))+8
        half = slice(2, 4) if component < 4 else slice(4, 6)
        group = shared_run(f, index, half)
        f[group, byte] = (f[group, byte] & (255 ^ (15 << shift))) | (target << shift)
    elif kind == 'pitch':
        current, target = int(f[index, 0]), int(periods[index])
        if current and target:
            f[index, 0] = current+int(np.sign(target-current))
    elif kind == 'gain':
        current = int(f[index, 1] & 15)
        target = current+int(np.sign(int(gains[index])-current))
        f[index, 1] = (int(f[index, 1]) & 48) | target
    elif kind == 'voicing':
        current, target = int(f[index, 0]), int(periods[index])
        if bool(current) != bool(target):
            f[index, 0] = target
    else:
        raise ValueError('Unknown soft-prior proposal kind')
    return f, d, kind


def whole_transfer_screen(objective, frames, durations, prior, baseline):
    """The reproducible 48 global controls are not blindly used as seeds."""
    reflections, periods, _ = prior.mapped(durations)
    old = np.column_stack([part for j in range(4) for part in
        ((frames[:, j+2] & 15).astype(int)-8, (frames[:, j+2] >> 4).astype(int)-8)])
    rows = []
    for alpha in (0., .25, .5, 1.):
        k = np.clip(np.rint(old*(1-alpha)+reflections*alpha), -7, 7).astype(int)+8
        packed = (k[:, ::2] | (k[:, 1::2] << 4)).astype(np.uint8)
        for i in range(1, len(frames)):
            for half in (slice(0, 2), slice(2, 4)):
                if np.array_equal(frames[i, 2:][half], frames[i-1, 2:][half]):
                    packed[i, half] = packed[i-1, half]
        for policy in ('old', 'f0-both-voiced', 'lpc2-voicing', 'lpc2-all'):
            for scale in (.75, 1., 1.25):
                f = frames.copy()
                f[:, 2:] = packed
                both = (frames[:, 0] > 0) & (periods > 0)
                if policy == 'f0-both-voiced':
                    f[both, 0] = periods[both]
                elif policy == 'lpc2-voicing':
                    f[periods == 0, 0] = 0
                elif policy == 'lpc2-all':
                    f[:, 0] = periods
                f[:, 1] = (f[:, 1] & 48) | np.clip(np.rint((frames[:, 1] & 15)*scale), 0, 15).astype(np.uint8)
                score = objective.evaluate(f, durations)
                rows.append(dict(reflection_blend=alpha, pitch_policy=policy, gain_scale=scale,
                    physical_valid=score is not None, eligible=eligible(score, baseline), score=score,
                    improved=bool(eligible(score, baseline) and score['difference_loss'] < baseline['difference_loss']-1e-12)))
    return rows


def fit(objective, frames, durations, prior, *, proposals=2000, seed=23261, progress=None):
    if not 0 <= proposals <= 2000:
        raise ValueError('This bounded probe permits 0 through 2000 proposals')
    baseline = objective.evaluate(frames, durations)
    if not eligible(baseline, baseline):
        raise ValueError('Incumbent must be finite and pass exact Q3 physical/byte guards')
    best = frames.copy(), durations.copy(), baseline.copy()
    current = best
    rng = random.Random(seed)
    counts, history = Counter(), []
    for step in range(proposals):
        anchor = best if rng.random() < .65 else current
        if rng.random() < .5:
            f, d = proposal(anchor[0], anchor[1], rng)
            kind = 'existing'
        else:
            f, d, kind = soft_proposal(anchor[0], anchor[1], prior, rng)
        counts[kind] += 1
        if np.array_equal(f, anchor[0]) and np.array_equal(d, anchor[1]):
            counts['unchanged'] += 1
            continue
        score = objective.evaluate(f, d)
        if score is None or not all(key in score and math.isfinite(score[key]) for key in GUARDED_KEYS):
            counts['rejected_physical_or_nonfinite'] += 1
            continue
        counts['evaluated'] += 1
        passed = eligible(score, baseline)
        counts['eligible'] += int(passed)
        if passed and score['difference_loss'] < best[2]['difference_loss']-1e-12:
            best = f.copy(), d.copy(), score.copy()
            history.append(dict(proposal=step+1, kind=kind, **score))
        temperature = .004*(.1**((step % 500)/499))
        delta = frozen.working_energy(score, baseline)-frozen.working_energy(current[2], baseline)
        if delta < 0 or rng.random() < math.exp(max(-700., min(0., -delta/temperature))):
            current = f, d, score
            counts['accepted_working'] += 1
        if (step+1) % 500 == 0:
            current = best
            if progress:
                progress(step+1, best[2])
    return best, dict(baseline=baseline, proposals=proposals, seed=seed,
                     counts=dict(counts), accepted_elites=len(history), history=history)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--proposals', type=int, default=2000)
    p.add_argument('--seed', type=int, default=23261)
    p.add_argument('--stream-budget', type=int, default=602)
    p.add_argument('--control-stream-budget', type=int,
                   help='Optional smaller byte cap for the 48 historical whole-transfer controls')
    p.add_argument('--storage', choices=('flash', 'eeprom-prefix'), default='flash',
                   help='EEPROM-prefix uses the independently built 64-byte EEPROM reader, T1 only')
    p.add_argument('--node')
    p.add_argument('--build', action='store_true', help='Assemble and verify an improved export in all three engines')
    p.add_argument('--avr-bin', type=Path)
    p.add_argument('--baseline-build', type=Path, help='Optional existing qualification, checked against incumbent stream and PCM')
    p.add_argument('--retain', type=Path, help='Retain reports and selected model only; audio/build artifacts stay ignored')
    a = p.parse_args()
    reference, sr = sf.read(a.reference, dtype='float64')
    model = json.loads(a.model.read_text(encoding='utf-8'))
    if (sr != 7500 or reference.ndim != 1 or len(reference) < 3072 or not np.all(np.isfinite(reference))
            or model.get('schema') != 'hq4-q3-v1' or model.get('tilt_shift') not in (0, 1)
            or not 0 <= a.proposals <= 2000):
        p.error('Expected complete finite mono7500 Q3 source/model and 0 through 2000 proposals')
    frames = np.asarray(model['frames'], np.uint8)
    durations = np.asarray(model['durations'], np.uint16)
    tilt = model['tilt_shift']
    maximum = 639 if a.storage == 'eeprom-prefix' else (603 if tilt else 615)
    minimum = 64 if a.storage == 'eeprom-prefix' else 8
    if (a.storage == 'eeprom-prefix' and tilt != 1) or not minimum <= a.stream_budget <= maximum:
        p.error('Byte budget must leave space for exact Q3 decoder, EOF and linker padding')
    incumbent_payload = validate_fields(frames, durations, len(reference))
    control_budget = a.control_stream_budget or a.stream_budget
    if not len(incumbent_payload) <= control_budget <= a.stream_budget:
        p.error('Control cap must contain the incumbent and not exceed the search cap')
    objective = frozen.Objective(reference, tilt, a.stream_budget, 10)
    baseline = objective.evaluate(frames, durations)
    if not eligible(baseline, baseline):
        p.error('Incumbent does not satisfy the unchanged decoder and byte limits')
    node = a.node or default_node()
    a.output.mkdir(parents=True, exist_ok=True)
    bridge = Lpc2Bridge(a.output/'coefficient-cache', node=node)
    base, native = bridge.encode(reference, sr, a.output/'native')
    prior = Prior(native, frames, durations)
    started = time.perf_counter()
    control_objective = (objective if control_budget == a.stream_budget else
                         frozen.Objective(reference, tilt, control_budget, 10))
    screen = whole_transfer_screen(control_objective, frames, durations, prior, baseline)
    save(a.output/'seed-screen.json', dict(schema='q3-lpc2-whole-transfer-screen-v1',
        reference_sha256=sha(a.reference.read_bytes()), stream_budget=control_budget, trials=screen,
        physical_valid=sum(row['physical_valid'] for row in screen),
        improved=sum(row['improved'] for row in screen),
        policy='Controls are inspected only; they cannot replace the guarded incumbent'))
    best, counters = fit(objective, frames, durations, prior, proposals=a.proposals, seed=a.seed,
        progress=lambda step, score: print(json.dumps(dict(proposal=step, final=score)), flush=True))
    f, d, score = best
    payload, before_payload = pack_stream(f, d), pack_stream(frames, durations)
    pcm, before_pcm = render(f, d, tilt)[0], render(frames, durations, tilt)[0]
    changed = payload != before_payload
    if not changed:
        shutil.copyfile(a.model, a.output/'model.json')
        if not np.array_equal(pcm, before_pcm):
            raise AssertionError('Baseline fallback changed exact integer PCM')
    else:
        save(a.output/'model.json', dict(model, frames=f.tolist(), durations=d.tolist()))
    (a.output/'speech.hq').write_bytes(payload)
    (a.output/'expected.raw').write_bytes(pcm.tobytes())
    sf.write(a.output/'decoded.wav', (pcm.astype(float)-128)/128, sr, subtype='PCM_16')
    baseline_qualification = None
    if a.baseline_build:
        qualification = json.loads(a.baseline_build.read_text(encoding='utf-8'))
        profile = qualification.get('q3Profile', {})
        if (qualification['status'] != 'verified' or qualification['flashBytes'] > 1024
                or qualification['streamSha256'] != sha(before_payload)
                or qualification['phrasePcmSha256'] != sha(before_pcm.tobytes())
                or qualification['eepromUsedBytes'] > 64 or profile.get('tilt_shift') != tilt
                or profile.get('code_bytes') != (420 if tilt else 408)):
            raise ValueError('Existing build report does not qualify this exact incumbent')
        for name, fingerprint in profile['sourcesSha256NormalizedLf'].items():
            if sha((ROOT/name).read_text(encoding='utf-8').encode()) != fingerprint:
                raise ValueError('Existing Q3 qualification source no longer matches: '+name)
        baseline_qualification = {key: qualification[key] for key in
            ('status', 'flashBytes', 'codeBytes', 'streamBytes', 'eofBytes', 'linkerPaddingBytes',
             'eepromUsedBytes', 'streamSha256', 'phrasePcmSha256', 'imageSha256')}
        baseline_qualification['report_sha256'] = sha(a.baseline_build.read_bytes())
    sources = [Path(__file__), ROOT/'tools/probe-hq4-q3-tracks.py', ROOT/'tools/lpc2-reference-cli.mjs',
        CODEC/'hq4_q3.py', CODEC/'hq4_core.py', CODEC/'hq4_speech_search.py', CODEC/'lpc2_excitation.py',
        CODEC/'harmonic_tracks.py', CODEC/'spectrogram_objective.py', CODEC/'auto_encoder.py',
        ROOT/'ATmega328/Sound/reference/lpx3/lpc2_v2_reference.html',
        ROOT/'ATmega328/Sound/reference/lpx3/lpx3_decoder.js',
        ROOT/'ATmega328/Sound/reference/lpx3/hybrid_codec.py']
    code_bytes = 448 if a.storage == 'eeprom-prefix' else (420 if tilt else 408)
    eeprom_bytes = min(64, len(payload)) if a.storage == 'eeprom-prefix' else 0
    object_bytes = code_bytes+len(payload)-eeprom_bytes+1
    report = dict(schema='q3-soft-lpc2-prior-v1', reference_sha256=sha(a.reference.read_bytes()),
        reference=(a.reference.resolve().relative_to(ROOT).as_posix() if a.reference.resolve().is_relative_to(ROOT) else 'external/'+a.reference.name),
        samples=len(reference), sample_rate=sr, input_model_sha256=sha(a.model.read_bytes()),
        selected_model_sha256=sha((a.output/'model.json').read_bytes()),
        selected_stream_sha256=sha(payload), selected_pcm_sha256=sha(pcm.tobytes()),
        changed=changed, baseline_fallback=not changed, selected_is_feasible=eligible(score, baseline),
        final=score, **counters, stream_budget=a.stream_budget, stream_bytes=len(payload),
        decoder_profile_bytes_estimate=code_bytes, estimated_full_flash_bytes=(object_bytes+1) & ~1,
        decoder_arithmetic_changed=False,
        storage=a.storage, storage_code_changed=a.storage != 'flash',
        selected_eeprom_bytes=eeprom_bytes, selected_stream_flash_bytes=len(payload)-eeprom_bytes,
        avr_assembled=False, hardware_tested=False, human_listening_verified=False,
        baseline_qualification=baseline_qualification,
        baseline_qualification_applies_to_selected=bool(not changed and baseline_qualification and a.storage == 'flash'),
        whole_transfer_controls=48, whole_transfer_stream_budget=control_budget,
        whole_transfer_improved=sum(row['improved'] for row in screen),
        lpc2_base_bytes=len(base), lpc2_base_sha256=sha(base),
        lpc2_prior_gain_calibration=prior.gain_scale,
        prior_policy='Full order-ten step-down, first eight reflection coefficients, Q3 quantization; F0/voicing and median-calibrated gain are soft local suggestions only',
        input_policy='Complete current reference at7500Hz, raw gain/DC/timing unchanged; LPC2 encodes Float32 as its browser path does',
        search_policy='Half existing proposals, half one-step reflection/F0/gain or separate voicing proposals; frozen incumbent never replaced by ineligible working states',
        guard_policy='STOI/eSTOI and coverage floors; four spectral, missing/extra, continuity and harmonic-loss ceilings; exact integer wraps, steps, peak, samples and actual stream bytes',
        source_sha256_normalized_lf={path.relative_to(ROOT).as_posix():sha(path.read_text(encoding='utf-8').encode()) for path in sources},
        elapsed_seconds=time.perf_counter()-started)
    signals = [reference, (before_pcm.astype(float)-128)/128, (pcm.astype(float)-128)/128]
    presentation = objective.spectral
    signals = [presentation.matched(audio) for audio in signals]
    scale = .85/max(float(np.max(abs(audio))) for audio in signals)
    for name, audio in zip(('original', 'before', 'after'), signals):
        sf.write(a.output/(name+'-matched.wav'), audio*scale, sr, subtype='PCM_16')
    sf.write(a.output/'comparison.wav', np.concatenate([part for audio in signals for part in
        (audio*scale, np.zeros(2250))]), sr, subtype='PCM_16')
    report['listening_processing'] = 'Diagnostic only: common70Hz highpass/globalRMSmatch/shared peak scale; decoded.wav remains raw'
    # A missing compiler/runtime must not discard the completed search history.
    save(a.output/'quality.json', report)
    if a.build and (changed or a.storage == 'eeprom-prefix'):
        builder_path = ROOT/('tools/build-q3-rounded-eeprom.py' if a.storage == 'eeprom-prefix' else 'tools/probe-hq4-q3.py')
        spec = importlib.util.spec_from_file_location('q3_soft_prior_builder', builder_path)
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        if a.storage == 'eeprom-prefix':
            built = builder.build(a.output/'speech.hq', a.output/'avr', a.avr_bin, node,
                                  expected_samples=int(d.sum()), rounded=False)
        else:
            built = builder.build(a.output/'avr', f, d, tilt, a.avr_bin, node)
        if built['status'] != 'verified' or built['flashBytes'] > 1024 or built['eepromUsedBytes'] > 64:
            raise ValueError('Improved stream failed actual AVR budget or three-engine qualification')
        report['avr_assembled'] = True
        report['build_report'] = 'avr/build.json'
        report['actual_full_flash_bytes'] = built['flashBytes']
        report['actual_eeprom_used_bytes'] = built['eepromUsedBytes']
        report['source_sha256_normalized_lf'][builder_path.relative_to(ROOT).as_posix()] = sha(builder_path.read_text(encoding='utf-8').encode())
    save(a.output/'quality.json', report)
    if a.retain:
        save(a.retain/'quality.json', report)
        shutil.copyfile(a.output/'seed-screen.json', a.retain/'seed-screen.json')
        shutil.copyfile(a.output/'model.json', a.retain/'model.json')
        if report['avr_assembled']:
            shutil.copyfile(a.output/'avr/build.json', a.retain/'build.json')
    print(json.dumps(console_summary(report)), flush=True)


if __name__ == '__main__':
    main()

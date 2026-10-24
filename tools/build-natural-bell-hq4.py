"""Build a compact T1 voice with a fixed or automatically balanced bell prelude."""
import argparse
import copy
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, stft

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from bell_model import decode_bell
from model import decode as legacy_decode


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def balance_bell(source, reference, voice_pcm):
    """Fit only the three integer gains; preserve frequencies and event timing."""
    n = int(source['prefix_samples'])
    voice = (voice_pcm.astype(float)-128)/128
    reference = np.asarray(reference, dtype=float)
    if (reference.ndim != 1 or len(reference) != n+len(voice)
            or not np.all(np.isfinite(reference))):
        raise ValueError('Bell balance requires the exact complete reference and voice duration')
    voice_rms = float(np.sqrt(np.mean(voice**2)))
    reference_voice_rms = float(np.sqrt(np.mean(reference[n:]**2)))
    if min(voice_rms, reference_voice_rms) < 1e-6:
        raise ValueError('Cannot balance a bell against a silent voice')
    level = voice_rms/reference_voice_rms
    target = reference[:n]*level
    target_rms = float(np.sqrt(np.mean(target**2)))
    if target_rms < 1e-6:
        raise ValueError('Cannot fit bell amplitude to a silent reference event')
    targets = [(size, abs(stft(target, nperseg=size, noverlap=size//2)[2])) for size in (128, 256, 512)]
    best = None
    # Exhaustive bounded integer search: at most 343 gain triples, no listening
    # choices and no new bytes in the decoder or descriptor structure.
    for gains in itertools.product(range(1, 8), repeat=3):
        if sum(gains) > 15:
            continue
        trial = copy.deepcopy(source)
        for partial, gain in zip(trial['partials'], gains):
            partial['amplitude'] = gain
        audio = (decode_bell(trial).astype(float)-128)/128
        rms = float(np.sqrt(np.mean(audio**2)))
        error = 0.
        for size, spectrum in targets:
            actual = abs(stft(audio, nperseg=size, noverlap=size//2)[2])
            error += float(np.linalg.norm(actual-spectrum)/(np.linalg.norm(spectrum)+1e-12))
        error = error/3 + .15*abs(np.log((rms+1e-12)/(target_rms+1e-12)))
        if best is None or error < best[0]:
            best = error, trial, rms
    error, selected, rms = best
    selected.pop('level_matched_mse', None)
    selected.pop('spectral_fit_objective', None)
    selected['voice_level_scale'] = level
    selected['balanced_bell_objective'] = error
    selected['target_bell_rms'] = target_rms
    selected['decoded_bell_rms'] = rms
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--bell-model', required=True, type=Path)
    parser.add_argument('--voice-model', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--avr-bin', type=Path)
    parser.add_argument('--node', default='node')
    parser.add_argument('--balance-bell', action='store_true',
                        help='Refit only bell integer amplitudes to the source bell/voice level relationship')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_bell = json.loads(args.bell_model.read_text(encoding='utf-8'))
    voice = json.loads(args.voice_model.read_text(encoding='utf-8'))
    if voice['tilt_shift'] != 1:
        raise ValueError('The compact assembled hybrid implements T1 only')
    voice['voice_offset_samples'] = source_bell['prefix_samples']
    (output/'voice-input.json').write_text(json.dumps(voice, indent=2)+'\n', encoding='utf-8', newline='\n')
    natural = load_module('natural_voice_oracle', ROOT/'tools/probe-hq4-natural-timbre.py')
    reference, sr = sf.read(args.reference, dtype='float64')
    raw = legacy_decode(np.asarray(voice['frames'], np.uint8), np.asarray(voice['durations'], np.uint16), 0)
    new_voice, wraps = natural.tilt(raw, 1)
    if wraps:
        raise ValueError('Tilt restoration overflows signed-byte arithmetic')
    selected_bell = balance_bell(source_bell, reference, new_voice) if args.balance_bell else source_bell
    builder = load_module('natural_bell_private_builder', ROOT/'tools/encode-bell-hq4.py')
    builder.TEMPLATE = CODEC/'natural-bell-oneshot/hq4.S'
    builder.decode = lambda f, d, _: natural.tilt(legacy_decode(f, d, 0), 1)[0]
    # Preserve every prelude sample. Its frequencies, envelope, onset, sine
    # table and integer gains are held constant for this controlled comparison.
    builder.fit = lambda reference, voice_pcm, boundary: copy.deepcopy(selected_bell)
    report = builder.build(args.reference, output/'voice-input.json', None, output, args.avr_bin, args.node)
    model = json.loads((output/'model.json').read_text(encoding='utf-8'))
    old_voice = source_bell['voice']
    old_pcm = np.r_[decode_bell(source_bell), legacy_decode(np.asarray(old_voice['frames'], np.uint8),
                                                         np.asarray(old_voice['durations'], np.uint16), 0)]
    new_pcm = np.r_[decode_bell(selected_bell), new_voice]
    n = int(source_bell['prefix_samples'])
    same_bell = bool(np.array_equal(old_pcm[:n], new_pcm[:n]))
    if not args.balance_bell and not same_bell:
        raise ValueError('Bell prelude changed during voice comparison')
    scores = dict(baseline_hybrid=builder.quality(reference, old_pcm, n),
                  natural_hybrid=builder.quality(reference, new_pcm, n),
                  lattice=natural.audit(np.asarray(voice['frames'], np.uint8), np.asarray(voice['durations'], np.uint16)),
                  tilt_wraps=int(wraps), bell_prefix_identical=same_bell,
                  bell_level_policy='source-relative-voice-rms' if args.balance_bell else 'fixed-original-PCM')
    (output/'quality.json').write_text(json.dumps(scores, indent=2)+'\n', encoding='utf-8', newline='\n')
    hp = butter(2, 70, fs=sr, btype='highpass', output='sos')
    tracks = [sosfilt(hp, reference), sosfilt(hp, (old_pcm.astype(float)-128)/128),
              sosfilt(hp, (new_pcm.astype(float)-128)/128)]
    rms = float(np.sqrt(np.mean(tracks[0]**2)))
    tracks = [x*rms/(np.sqrt(np.mean(x*x))+1e-12) for x in tracks]
    gain = min(1., .94/max(float(np.max(abs(x))) for x in tracks))
    for name, track in zip(('original-matched', 'before-matched', 'after-matched'), tracks):
        sf.write(output/(name+'.wav'), track*gain, sr, subtype='PCM_16')
    sf.write(output/'comparison.wav', np.r_[tracks[0]*gain, np.zeros(2250), tracks[1]*gain,
                                           np.zeros(2250), tracks[2]*gain], sr, subtype='PCM_16')
    model.update(schema='micromusic-bell-hq4-t1-v1', tilt_shift=1,
                 bell_unchanged_source_sha256=sha(args.bell_model.read_bytes()),
                 voice_level_scale=selected_bell['voice_level_scale'] if args.balance_bell else None,
                 bell_level_policy=scores['bell_level_policy'],
                 level_note='Only bell amplitudes may change; see measured bell/voice ratios in quality.json.')
    (output/'model.json').write_text(json.dumps(model, indent=2)+'\n', encoding='utf-8', newline='\n')
    report.update(schema='micromusic-bell-hq4-t1-build-v1', tiltShift=1,
                  modelSha256=sha((output/'model.json').read_bytes()),
                  sourceBellModelSha256=sha(args.bell_model.read_bytes()),
                  sourceVoiceModelSha256=sha(args.voice_model.read_bytes()),
                  bellPrefixPcmSha256=sha(new_pcm[:n].tobytes()),
                  sourceBellPrefixPcmSha256=sha(old_pcm[:n].tobytes()), bellPrefixIdentical=same_bell,
                  bellLevelPolicy=scores['bell_level_policy'])
    for path in (Path(__file__), ROOT/'tools/probe-hq4-natural-timbre.py', CODEC/'hq4_phase.py'):
        report['normalizedSourceSha256'][path.relative_to(ROOT).as_posix()] = sha(path.read_text(encoding='utf-8').encode('utf-8'))
    (output/'build.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({key: report[key] for key in ('status', 'flashBytes', 'codeBytes', 'streamBytes',
                                                  'phraseSamples', 'bellPrefixIdentical')}, indent=2))
    return 0 if report['status'] == 'verified' else 1


if __name__ == '__main__':
    raise SystemExit(main())

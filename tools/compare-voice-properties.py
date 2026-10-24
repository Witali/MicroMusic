"""Describe reference speech properties without assigning character-specific modes.

F0 and periodicity are estimates, not annotated voice/noise ground truth.
This analysis does not change the source or select a decoder automatically.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.signal import butter, sosfilt
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from speech_pitch import track_speech_pitch


def describe(audio, sr):
    centres, f0, quality, pitch = track_speech_pitch(audio, sr)
    raw = np.asarray(pitch['raw_f0_hz'])
    rms = np.asarray(pitch['rms'])
    active = rms > max(float(np.sqrt(np.mean(audio**2)))*.06, 1e-8)
    voiced = raw > 0
    positive = raw[voiced & active]
    same = voiced[1:] & voiced[:-1] & active[1:] & active[:-1]
    jumps = 1200*abs(np.log2(raw[1:][same]/raw[:-1][same]))
    # Whole-file band powers include effects and consonants, not just vowels.
    filtered = sosfilt(butter(2, 70, fs=sr, btype='highpass', output='sos'), audio)
    power = abs(np.fft.rfft(filtered))**2
    frequency = np.fft.rfftfreq(len(filtered), 1/sr)
    total = max(float(power.sum()), 1e-20)
    weights = rms**2
    return dict(samples=len(audio), duration_seconds=len(audio)/sr,
        frames=len(raw), active_frames=int(active.sum()),
        raw_voiced_active_frames=int((voiced & active).sum()),
        raw_voiced_active_frame_fraction=float((voiced & active).sum()/max(1, active.sum())),
        raw_unvoiced_active_frame_energy_fraction=float(weights[active & ~voiced].sum()/max(weights[active].sum(), 1e-20)),
        raw_voiced_f0_p05_p50_p95_hz=np.percentile(positive, [5, 50, 95]).tolist() if len(positive) else None,
        raw_adjacent_voiced_step_p50_p95_cents=np.percentile(jumps, [50, 95]).tolist() if len(jumps) else None,
        persistent_prior_hz=pitch['prior_hz'],
        persistent_accepted_runs=[run for run in pitch['prior_runs'] if run['accepted']],
        strict_voiced_frames=int(np.count_nonzero(f0)),
        power_below_800_hz=float(power[frequency < 800].sum()/total),
        power_above_2500_hz=float(power[frequency >= 2500].sum()/total),
        raw_f0_hz=raw.tolist(), raw_periodicity=pitch['raw_periodicity'],
        frame_centres_seconds=(centres/sr).tolist())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', action='append', required=True, help='Unique name=mono7500.wav')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    rows = {}
    for item in a.reference:
        name, separator, filename = item.partition('=')
        if not separator or not name or name in rows:
            p.error('Each reference needs a unique name=path')
        source = Path(filename)
        audio, sr = sf.read(source)
        if sr != 7500 or audio.ndim != 1 or not np.isfinite(audio).all():
            p.error('Expected finite mono7500.wav')
        rows[name] = dict(reference_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                          **describe(audio, sr))
        print(json.dumps(dict(id=name, **{key: value for key, value in rows[name].items()
            if key in ('duration_seconds', 'raw_voiced_f0_p05_p50_p95_hz',
                       'raw_unvoiced_active_frame_energy_fraction', 'persistent_prior_hz',
                       'raw_voiced_active_frame_fraction', 'power_above_2500_hz')})), flush=True)
    report = dict(schema='reference-voice-properties-v1', sample_rate=7500,
        definition='Same generic pitch analysis on every recording; no manual interval or character-specific thresholds.',
        limitations=['Estimated pitch can confuse harmonics/subharmonics, attacks and rough voice.',
                     'Unvoiced frames are not semantic labels; band powers include retained sound effects.',
                     'This comparison cannot isolate perception from codec family, phrase length or training history.',
                     'No source is trimmed, resynthesized or normalized to hide differences.'],
        source_sha256_normalized_lf={path.relative_to(ROOT).as_posix():
            hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            for path in (Path(__file__), CODEC/'speech_pitch.py', CODEC/'period_wave.py')},
        references=rows)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()

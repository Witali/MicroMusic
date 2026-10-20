"""Measure the retained stereo FluidR3 Violin captures; requires NumPy."""
from pathlib import Path
import argparse
import hashlib
import json
import wave
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def analyze(directory):
    capture = json.loads((directory / 'capture.json').read_text(encoding='utf-8'))
    notes = []
    ages = [.18, .26, .34, .42, .50, .58]
    for entry in capture['notes']:
        path = directory / entry['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']
        with wave.open(str(path), 'rb') as f:
            sr, channels = f.getframerate(), f.getnchannels()
            pcm = np.frombuffer(f.readframes(f.getnframes()), dtype='<i2').reshape(-1, channels) / 32768.
        n = round(.08 * sr)
        time, window = np.arange(n) / sr, np.hanning(n)
        nominal = 440 * 2 ** ((entry['midi'] - 69) / 12)
        frames = []
        for age in ages:
            segment = pcm[round(age * sr):round(age * sr) + n]
            weighted = (segment - segment.mean(axis=0)) * window[:, None]
            candidates = nominal * np.linspace(.98, 1.02, 81)
            a = np.exp(-2j * np.pi * candidates[:, None] * time) @ weighted
            b = np.exp(-4j * np.pi * candidates[:, None] * time) @ weighted
            f0 = candidates[np.argmax(np.sum(abs(a) ** 2 + .25 * abs(b) ** 2, axis=1))]
            cs = np.exp(-2j * np.pi * np.arange(1, 16)[:, None] * f0 * time) @ weighted
            # Stereo power, rather than L+R cancellation, defines the target.
            amplitudes = np.sqrt(np.mean(abs(cs) ** 2, axis=1))
            loudest = int(np.argmax(np.sum(abs(cs[:7]) ** 2, axis=0)))
            phase = np.angle(cs[:, loudest]) - np.arange(1, 16) * np.angle(cs[0, loudest])
            frames.append(dict(ageSeconds=age, f0Hz=float(f0),
                               amplitudes=(amplitudes / np.linalg.norm(amplitudes[:7])).tolist(),
                               relativePhases=phase.tolist()))
        env_times = np.arange(.005, .845, .005)
        rms = np.array([np.sqrt(np.mean(pcm[round(max(0, t - .005) * sr):round((t + .005) * sr)] ** 2)) for t in env_times])
        normalized = rms / max(rms)
        gate = capture['gateSeconds']
        tail_times = np.arange(gate - .05, gate + capture['tailSeconds'] - .005, .005)
        tail_rms = np.array([np.sqrt(np.mean(pcm[round((t - .005) * sr):round((t + .005) * sr)] ** 2)) for t in tail_times])
        reference_rms = float(np.mean(tail_rms[tail_times < gate]))
        after = tail_times >= gate - 1e-9
        release = tail_rms[after] / reference_rms
        release_age = (tail_times[after] - gate) * 1000
        thresholds = {str(level): float(release_age[np.flatnonzero(release <= level)[0]])
                      if np.any(release <= level) else None for level in [.85, .5, .25, .1, .05]}
        notes.append(dict(midi=entry['midi'], source=entry['file'], sha256=entry['sha256'],
                          attack85PercentMs=float(env_times[np.flatnonzero(normalized >= .85)[0]] * 1000),
                          envelopeTimesMs=(env_times * 1000).round(3).tolist(),
                          envelopeRms=normalized.tolist(),
                          releaseTimesMs=release_age.round(3).tolist(), releaseRms=release.tolist(),
                          releaseThresholdMs=thresholds, frames=frames))
    return dict(schema=1, capture=capture, measurement=dict(
        window='80-ms Hann; six sustain ages 180–580 ms; 15 partials; stereo power',
        frequencySearch='81 frequencies over nominal +/-2%; H1 power + 0.25 H2 power',
        envelope='10-ms stereo RMS every 5 ms; attack normalized to pre-note-off maximum, release to mean RMS in final 50 ms before note-off',
        reference='FluidR3 sample-bank synthesis, not an acoustic violin measurement'), notes=notes)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference_directory', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    data = analyze(args.reference_directory)
    args.output.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8', newline='\n')
    for note in data['notes']:
        amps = np.median([f['amplitudes'] for f in note['frames']], axis=0)
        print(note['midi'], 'attack85_ms', note['attack85PercentMs'], 'H1..7', np.round(amps[:7] / amps[0], 3))

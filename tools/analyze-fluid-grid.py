"""Measure all tonal FluidR3 references, including attack, sustain and release."""
from pathlib import Path
import hashlib
import json
import wave
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'ATtiny13A/Music/reference/fluidr3'


def analyze(profile):
    folder = ROOT / 'build/fluid-grid' / profile
    capture = json.loads((folder / 'capture.json').read_text(encoding='utf-8'))
    result = []
    ages = [.30, .46, .62, .78] if profile == 'violin' else [.12, .20, .30, .45, .65, .85]
    for note in capture['notes']:
        raw = (folder / note['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == note['sha256']
        with wave.open(str(folder / note['file'])) as f:
            sr = f.getframerate()
            x = np.frombuffer(f.readframes(f.getnframes()), dtype='<i2').reshape(-1, 2) / 32768.
        n = round(.08 * sr); t = np.arange(n) / sr; window = np.hanning(n)
        nominal = 440 * 2 ** ((note['midi'] - 69) / 12)
        frames = []
        for age in ([.005, .020, .040] if profile != 'violin' else []) + ages:
            segment = x[round(age * sr):round(age * sr) + n]
            y = (segment - segment.mean(axis=0)) * window[:, None]
            candidates = nominal * np.linspace(.98, 1.02, 81)
            z = np.exp(-2j * np.pi * candidates[:, None] * t) @ y
            z2 = np.exp(-4j * np.pi * candidates[:, None] * t) @ y
            f0 = candidates[np.argmax(np.sum(abs(z) ** 2 + .25 * abs(z2) ** 2, axis=1))]
            partials = np.exp(-2j * np.pi * np.arange(1, 16)[:, None] * f0 * t) @ y
            power = np.sqrt(np.mean(abs(partials) ** 2, axis=1))
            channel = int(np.argmax(np.sum(abs(partials[:7]) ** 2, axis=0)))
            phase = np.angle(partials[:, channel]) - np.arange(1, 16) * np.angle(partials[0, channel])
            frames.append(dict(ageSeconds=age, stage='attack' if age < .1 else 'sustain',
                f0Hz=round(float(f0), 5), amplitudes=(power / np.linalg.norm(power)).round(7).tolist(),
                relativePhases=phase.round(7).tolist()))
        times = np.arange(.005, len(x) / sr - .005, .01)
        rms = np.array([np.sqrt(np.mean(x[round((a - .005) * sr):round((a + .005) * sr)] ** 2)) for a in times])
        peak = max(rms[times < capture['gateSeconds']])
        result.append(dict(midi=note['midi'], frames=frames, rms=(rms / peak).round(6).tolist()))
    return dict(capture=capture, envelopeTimesSeconds=times.round(4).tolist(), notes=result)


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    measurements = dict(schema=1, method='Original SF2 -> 48 kHz stereo; 80-ms Hann, 15 partials, nominal +/-2% F0 search. 10-ms RMS; no effects or normalization before measurement.',
                        instruments={p: analyze(p) for p in ['violin', 'piano', 'guitar']})
    (OUT / 'measurements.json').write_text(json.dumps(measurements, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8', newline='\n')
    for name, instrument in measurements['instruments'].items():
        t = np.array(instrument['envelopeTimesSeconds'])
        env = np.array([n['rms'] for n in instrument['notes']])
        print(name, len(env), 'notes, median RMS:', {str(a): round(float(np.median(env[:, np.argmin(abs(t-a))])), 3) for a in [.02,.05,.1,.2,.5,1,2,3,4.05,4.1,4.2,4.4]})

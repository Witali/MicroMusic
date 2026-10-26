#!/usr/bin/env python3
"""Fit 256-point, age-dependent waves from pinned native FluidR3 captures.

NumPy is needed only for authoring this retained bank. Firmware builds read JSON.
External captures come from tools/render-fluid-violin.mjs; no SF2/MIDI is copied.
"""
from pathlib import Path
import argparse
import hashlib
import json
import wave
import numpy as np

ROOT = Path(__file__).resolve().parent
FONT_SHA = '74594e8f4250680adf590507a306655a299935343583256f3b722c48a1bc1cb0'
ENGINE_SHA = 'd7d74edf4056b1be835cfd717c8cfb579440ee5c741d087d684b84041d861035'
SPECS = [('piano-low', 'piano', 60, 8), ('piano-high', 'piano', 74, 3), ('guitar', 'guitar', 52, 8)]
AGES = {'piano': [(.008, .032), (.040, .072), (.10, .164), (.20, .32)],
        'guitar': [(.008, .040), (.080, .18)]}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--captures', type=Path)
    parser.add_argument('--cpu-hz', type=int, choices=[2000000, 2500000, 3500000], default=3500000)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    target_root = ROOT if args.cpu_hz == 3500000 else ROOT/'clocks'/str(args.cpu_hz)
    if not args.check:
        target_root.mkdir(parents=True, exist_ok=True)
    limits = {2000000: [4, 1, 5], 2500000: [5, 2, 6], 3500000: [8, 3, 8]}[args.cpu_hz]
    specs = [(label, profile, note, limit) for (label, profile, note, _), limit in zip(SPECS, limits)]

    def save(name, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        if args.check:
            actual = (target_root/name).read_bytes()
            if name.endswith('.json'):
                actual = actual.replace(b'\r\n', b'\n')
            assert actual == data, f'Stale: {name}'
        else:
            (target_root/name).write_bytes(data)

    if args.captures:
        assert args.cpu_hz == 3500000, 'Import canonical captures at the default clock first'
        sources = []
        for label, profile, note, harmonics in SPECS:
            folder = args.captures/profile
            meta = json.loads((folder/'capture.json').read_text())
            assert meta['soundfont']['sha256'] == FONT_SHA
            assert meta['renderer']['sourceSha256'] == ENGINE_SHA
            item = next(n for n in meta['notes'] if n['midi'] == note)
            original = (folder/item['file']).read_bytes()
            assert sha(original) == item['sha256']
            with wave.open(str(folder/item['file']), 'rb') as f:
                assert (f.getframerate(), f.getnchannels(), f.getsampwidth()) == (48000, 2, 2)
                pcm = f.readframes(19200)
            import io
            out = io.BytesIO()
            with wave.open(out, 'wb') as f:
                f.setnchannels(2); f.setsampwidth(2); f.setframerate(48000); f.writeframes(pcm)
            retained = 'source-'+label+'.wav'
            save(retained, out.getvalue())
            sources.append({'id': label, 'program': meta['program'], 'preset': meta['preset'], 'midi': note,
                'full_capture_file': item['file'], 'full_capture_sha256': item['sha256'],
                'file': retained, 'sha256': sha(out.getvalue()), 'frames': 19200,
                'soundfont': meta['soundfont'], 'renderer': meta['renderer'], 'velocity': meta['velocity']})
        provenance = {'soundfont_sha256': FONT_SHA, 'license': 'MIT', 'notice': 'FluidR3-MIT.txt',
            'capture_script': '../../../tools/render-fluid-violin.mjs',
            'crop': 'First 0.4 seconds, stereo 48000 Hz PCM16, unchanged source samples', 'sources': sources}
        save('SOURCE.json', json.dumps(provenance, indent=2)+'\n')
    provenance = json.loads((ROOT/'SOURCE.json').read_text())
    banks = []
    for label, profile, note, harmonics in specs:
        source = next(s for s in provenance['sources'] if s['id'] == label)
        data = (ROOT/source['file']).read_bytes()
        assert sha(data) == source['sha256']
        with wave.open(str(ROOT/source['file']), 'rb') as f:
            samples = np.frombuffer(f.readframes(f.getnframes()), '<i2').reshape(-1, 2).mean(axis=1)/32768
        times = np.arange(len(samples))/48000
        # Measure the sustained fundamental, then remove its phase/tuning from
        # each capture. Playback pitch follows the score's 16-bit DDS, not SF2 tuning.
        mask = (times >= .10) & (times < .32)
        target = samples[mask]*np.hanning(mask.sum())
        nominal = 440*2**((note-69)/12)
        candidates = nominal*2**(np.arange(-25, 25.001, .25)/1200)
        frequency = float(max(candidates, key=lambda f: abs(np.dot(target, np.exp(-2j*np.pi*f*times[mask])))))
        waves, measured = [], []
        for begin, end in AGES[profile]:
            mask = (times >= begin) & (times < end)
            window = np.hanning(mask.sum()); t = times[mask]; x = samples[mask]
            coeff = np.array([2*np.dot(x*window, np.exp(-2j*np.pi*frequency*h*t))/window.sum()
                              for h in range(1, harmonics+1)])
            coeff *= np.exp(-1j*np.arange(1, harmonics+1)*(np.angle(coeff[0])+np.pi/2))
            def value(phase):
                return float(np.real(np.sum(coeff*np.exp(2j*np.pi*np.arange(1, harmonics+1)*phase))))
            grid = np.arange(4096)/4096-.5
            crossing = min((i for i in range(len(grid)-1) if value(grid[i]) <= 0 < value(grid[i+1])),
                           key=lambda i: abs(grid[i]))
            lo, hi = float(grid[crossing]), float(grid[crossing+1])
            for _ in range(35):
                mid = (lo+hi)/2
                if value(mid) > 0: hi = mid
                else: lo = mid
            phase = np.arange(256)/256+(lo+hi)/2
            result = np.real(np.sum(coeff[:, None]*np.exp(2j*np.pi*np.arange(1, harmonics+1)[:, None]*phase), axis=0))
            result[0] = 0
            waves.append(result)
            measured.append({'window_seconds': [begin, end], 'fundamental_hz': frequency,
                             'source_peak': float(np.max(np.abs(result))), 'rms': float(np.sqrt(np.mean(result**2)))})
        low = min(float(v.min()) for v in waves); high = max(float(v.max()) for v in waves)
        scale = min(8/-low, 7/high)
        quantized = [np.floor(8+w*scale+.5).clip(0, 15).astype(int).tolist() for w in waves]
        assert all(w[0] == 8 for w in quantized)
        banks.append({'id': label, 'program': source['program'], 'source_midi': note,
            'source_sha256': source['sha256'], 'harmonics': harmonics, 'samples_per_wave': 256,
            'peak_scale_levels_per_unit': scale, 'silence_level': 8,
            'ages_seconds': [sum(v)/2 for v in AGES[profile]], 'measurements': measured, 'waves': quantized})
    bank = {'format': 1, 'soundfont': 'FluidR3 GM 3.1', 'soundfont_sha256': FONT_SHA,
            'samples_per_wave': 256, 'piano_register_split_midi': 72,
            'piano_stage_boundaries_seconds': [.032, .095, .20], 'guitar_stage_boundaries_seconds': [.064],
            'normalization': 'One peak gain per register across all ages, preserving captured decay; zero is code 8',
            'method': 'Phase-aligned measured complex harmonics, 256 points, explicit harmonic limits then PCM4 quantization; reduced wavetable model, not full SF2 playback',
            'banks': banks}
    if args.cpu_hz != 3500000:
        bank['cpu_hz'] = args.cpu_hz
        bank['synthesis_rate_hz'] = args.cpu_hz/432
        bank['harmonic_limit_scope'] = 'Before PCM4 quantization; quantization still adds distortion. Limits respect each register maximum score pitch.'
    save('bank.json', json.dumps(bank, indent=2)+'\n')
    print('FluidR3: two piano registers, four piano ages, two guitar ages, 256 samples/wave')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Prepare confirmed speech sources as 16 kHz WAV and packed 4-bit PCM.

MP3 is an external input. Rebuild the retained PCM from source-16000.wav with
FFmpeg 8.1.1 / libsoxr; no network access is performed by this script.
"""
from pathlib import Path
import argparse
import array
import hashlib
import io
import json
import math
import os
import subprocess
import wave

ROOT = Path(__file__).resolve().parent
SOURCE_SHA = 'a47154ee2060b9166d6b44dfcc92a78466006f5e7430138407bcc24fc8859392'
CPU_HZ, PERIOD_T, REPEATS = 3500000, 109, 2


def digest(data):
    return hashlib.sha256(data).hexdigest()


def resample(path, rate):
    return subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path),
        '-ac', '1', '-af', f'aresample={rate}:resampler=soxr:precision=28:cheby=1',
        '-f', 's16le', '-acodec', 'pcm_s16le', '-'])


def wav_bytes(pcm, rate):
    out = io.BytesIO()
    with wave.open(out, 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(pcm)
    return out.getvalue()


def quantize(samples, scale, offset):
    return [max(0, min(15, math.floor(offset + value * scale + .5))) for value in samples]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='External, unmodified vinn.mp3')
    parser.add_argument('--profile', choices=['balloon', 'owl'], default='balloon')
    parser.add_argument('--cpu-hz', type=int, choices=[2000000, 2500000, 3500000], default=CPU_HZ)
    parser.add_argument('--pwm-profile', choices=['legacy', 'fast82'], default='legacy')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    source_root = ROOT if args.profile == 'balloon' else ROOT / args.profile
    base = source_root if args.pwm_profile == 'legacy' else ROOT.parent/'voice-pwm82'/('owl' if args.profile == 'owl' else '')
    target_root = base if args.cpu_hz == CPU_HZ else base / 'clocks' / str(args.cpu_hz)
    period, repeats = (PERIOD_T, REPEATS) if args.pwm_profile == 'legacy' else (82, 2)
    if not args.check:
        target_root.mkdir(parents=True, exist_ok=True)
    original = {
        'quote': 'С воздушным шаром можно кого хочешь утешить.',
        'source_page': 'https://zvukipro.com/mult/2937-zvuki-iz-sovetskogo-multfilma-vinni-puh.html',
        'download_url': 'https://zvukipro.com/index.php?do=download&id=56332',
        'original_filename': 'vinn.mp3', 'original_bytes': 81589, 'original_sha256': SOURCE_SHA,
        'original_sample_rate_hz': 48000, 'original_channels': 2, 'decoded_original_frames': 135995}
    if args.profile != 'balloon':
        original = json.loads((source_root / 'profile.json').read_text(encoding='utf-8'))['source']
    original_seconds = original['decoded_original_frames'] / original['original_sample_rate_hz']

    def save(name, data):
        path = target_root / name
        data = data.encode('utf-8') if isinstance(data, str) else data
        if args.check:
            actual = path.read_bytes()
            if path.suffix == '.json':
                actual = actual.replace(b'\r\n', b'\n')
            assert actual == data, f'Stale: {path}'
        else:
            path.write_bytes(data)

    canonical = source_root / 'source-16000.wav'
    if args.source:
        assert args.pwm_profile == 'legacy', 'Import canonical sources with the legacy preparation first'
        assert args.cpu_hz == CPU_HZ, 'Import the canonical source at the default clock first'
        assert digest(args.source.read_bytes()) == original['original_sha256'], 'Unexpected original audio'
        save(canonical.name, wav_bytes(resample(args.source, 16000), 16000))
    assert canonical.exists(), 'First run requires --source /path/to/vinn.mp3'
    with wave.open(str(canonical), 'rb') as f:
        assert (f.getnchannels(), f.getsampwidth(), f.getframerate()) == (1, 2, 16000)
        frames = f.getnframes()
    actual_rate = args.cpu_hz / (period * repeats)
    resampler_rate = round(actual_rate)
    raw = resample(canonical, resampler_rate)
    samples = [v / 32768 for v in array.array('h', raw)]
    # Normalize the ORIGINAL resampled signal into the entire PCM4 range.
    # Unlike the former minimum-MSE gain search, no source peak is clipped.
    energy = sum(x*x for x in samples)
    minimum, maximum = min(samples), max(samples)
    scale = 15 / (maximum-minimum)
    offset = -minimum*scale
    levels = quantize(samples, scale, offset)
    assert min(levels) == 0 and max(levels) == 15
    error = sum((x - (q-offset)/scale)**2 for x, q in zip(samples, levels))
    silence = max(0, min(15, math.floor(offset+.5)))
    valid_samples = len(levels)
    levels += [silence] * (-len(levels) % 4)
    packed = bytes(levels[n] | levels[n+1] << 4 for n in range(0, len(levels), 2))
    data = {'format': 'pcm4-low-nibble-first', 'cpu_hz': args.cpu_hz,
        'period_t': period, 'pulses_per_sample': repeats,
        'sample_rate_hz': actual_rate, 'valid_samples': valid_samples,
        'sample_count': len(levels), 'silence_level': silence, 'packed_hex': packed.hex()}
    save('pcm4.json', json.dumps(data, indent=2) + '\n')
    report = {**original, 'decoded_original_seconds': original_seconds,
        'canonical_wav': os.path.relpath(canonical, target_root).replace('\\', '/'),
        'canonical_sha256': digest(canonical.read_bytes()),
        'canonical_rate_hz': 16000, 'canonical_frames': frames,
        'ffmpeg_version': subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0],
        'resampler': 'libsoxr, precision=28, cheby=1, mono s16le',
        'firmware_resampler_rate_hz': resampler_rate, 'firmware_playback_rate_hz': actual_rate,
        'resampler_clock_error_ppm': (actual_rate/resampler_rate-1)*1e6,
        'normalization': 'Affine peak normalization: source minimum -> 0, maximum -> 15; no source clipping',
        'source_minimum': minimum, 'source_maximum': maximum,
        'scale_levels_per_unit': scale, 'zero_offset_levels': offset,
        'silence_level': silence, 'minimum_level': min(levels), 'maximum_level': max(levels),
        'clipped_source_samples': 0,
        'quantization': 'nearest integer, 16 linear levels; normalization precedes quantization',
        'quantization_snr_db': 10*math.log10(energy/error),
        'valid_samples': valid_samples, 'padding_samples': len(levels)-valid_samples,
        'packed_bytes': len(packed), 'packed_sha256': digest(packed),
        'playback_seconds_with_padding': len(levels)/actual_rate,
        'source_duration_error_seconds': len(levels)/actual_rate-original_seconds,
        'snr_scope': 'Quantized baseband versus resampled source, excluding PWM/filter/hardware.'}
    save('SOURCE.json', json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'{frames} samples at 16000 Hz; firmware {len(levels)} samples / {len(packed)} bytes; '
          f'full range 0..15, no clipping; PCM quantization SNR {report["quantization_snr_db"]:.2f} dB')


if __name__ == '__main__':
    main()

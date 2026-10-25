#!/usr/bin/env python3
"""Prepare the confirmed balloon quote as 16 kHz WAV and packed 4-bit PCM.

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


def quantize(samples, gain):
    # Silence is exactly level 8; no random dither or DC noise in quiet tails.
    return [max(0, min(15, math.floor(8 + value * gain * 7 + .5))) for value in samples]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='External, unmodified vinn.mp3')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()

    def save(name, data):
        path = ROOT / name
        data = data.encode('utf-8') if isinstance(data, str) else data
        if args.check:
            actual = path.read_bytes()
            if path.suffix == '.json':
                actual = actual.replace(b'\r\n', b'\n')
            assert actual == data, f'Stale: {path}'
        else:
            path.write_bytes(data)

    canonical = ROOT / 'source-16000.wav'
    if args.source:
        assert digest(args.source.read_bytes()) == SOURCE_SHA, 'Unexpected original MP3'
        save(canonical.name, wav_bytes(resample(args.source, 16000), 16000))
    assert canonical.exists(), 'First run requires --source /path/to/vinn.mp3'
    with wave.open(str(canonical), 'rb') as f:
        assert (f.getnchannels(), f.getsampwidth(), f.getframerate()) == (1, 2, 16000)
        frames = f.getnframes()
    actual_rate = CPU_HZ / (PERIOD_T * REPEATS)
    resampler_rate = round(actual_rate)
    raw = resample(canonical, resampler_rate)
    samples = [v / 32768 for v in array.array('h', raw)]
    # Minimize linear signal error, including both clipping and quantization.
    energy = sum(x*x for x in samples)
    best = None
    for step in range(150, 601):
        gain = step / 100
        levels = quantize(samples, gain)
        error = sum((x - (q-8)/(7*gain))**2 for x, q in zip(samples, levels))
        if best is None or error < best[0]:
            best = (error, gain, levels)
    error, gain, levels = best
    valid_samples = len(levels)
    levels += [8] * (-len(levels) % 4)
    packed = bytes(levels[n] | levels[n+1] << 4 for n in range(0, len(levels), 2))
    data = {'format': 'pcm4-low-nibble-first', 'cpu_hz': CPU_HZ,
        'period_t': PERIOD_T, 'pulses_per_sample': REPEATS,
        'sample_rate_hz': actual_rate, 'valid_samples': valid_samples,
        'sample_count': len(levels), 'packed_hex': packed.hex()}
    save('pcm4.json', json.dumps(data, indent=2) + '\n')
    report = {'quote': 'С воздушным шаром можно кого хочешь утешить.',
        'source_page': 'https://zvukipro.com/mult/2937-zvuki-iz-sovetskogo-multfilma-vinni-puh.html',
        'download_url': 'https://zvukipro.com/index.php?do=download&id=56332',
        'original_filename': 'vinn.mp3', 'original_bytes': 81589, 'original_sha256': SOURCE_SHA,
        'original_sample_rate_hz': 48000, 'original_channels': 2,
        'decoded_original_frames': 135995, 'decoded_original_seconds': 135995/48000,
        'canonical_wav': canonical.name, 'canonical_sha256': digest(canonical.read_bytes()),
        'canonical_rate_hz': 16000, 'canonical_frames': frames,
        'ffmpeg_version': subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0],
        'resampler': 'libsoxr, precision=28, cheby=1, mono s16le',
        'firmware_resampler_rate_hz': resampler_rate, 'firmware_playback_rate_hz': actual_rate,
        'resampler_clock_error_ppm': (actual_rate/resampler_rate-1)*1e6,
        'gain': gain, 'gain_search': '1.50..6.00, step 0.01, minimum unweighted squared error',
        'quantization': 'nearest integer, silence 8, 16 linear levels, clamp 0..15',
        'quantization_snr_db': 10*math.log10(energy/error),
        'valid_samples': valid_samples, 'padding_samples': len(levels)-valid_samples,
        'packed_bytes': len(packed), 'packed_sha256': digest(packed),
        'playback_seconds_with_padding': len(levels)/actual_rate,
        'source_duration_error_seconds': len(levels)/actual_rate-135995/48000,
        'snr_scope': 'Quantized baseband versus resampled source, excluding PWM/filter/hardware.'}
    save('SOURCE.json', json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'{frames} samples at 16000 Hz; firmware {len(levels)} samples / {len(packed)} bytes; '
          f'gain {gain:.2f}; PCM quantization SNR {report["quantization_snr_db"]:.2f} dB')


if __name__ == '__main__':
    main()

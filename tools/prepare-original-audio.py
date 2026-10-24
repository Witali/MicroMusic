#!/usr/bin/env python3
"""Prepare mobile-compatible listening copies without changing canonical WAVs."""
import argparse
import hashlib
import io
import json
import subprocess
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGINALS = ROOT / 'web-player/audio/originals'
OUTPUT = ORIGINALS / 'playback'
SAMPLE_RATE = 44100
RESAMPLER = 'aresample=44100:resampler=swr:filter_size=64:phase_shift=10:exact_rational=1:dither_method=none'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def wav_format(data):
    with wave.open(io.BytesIO(data), 'rb') as audio:
        return (audio.getnframes(), audio.getframerate(), audio.getnchannels(),
                audio.getsampwidth() * 8, audio.getcomptype())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--check', action='store_true', help='Verify retained assets without FFmpeg')
    args = parser.parse_args()
    clips = json.loads((ROOT / 'ATtiny13A/Sound/audio-references.json').read_text(encoding='utf-8'))['clips']
    if args.check:
        manifest = json.loads((OUTPUT / 'manifest.json').read_text(encoding='utf-8'))
        if {entry['id'] for entry in manifest['clips']} != {clip['id'] for clip in clips}:
            raise ValueError('Playback manifest does not match canonical clips')
    else:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        version = subprocess.check_output([args.ffmpeg, '-version'], text=True).splitlines()[0]
        manifest = dict(schema=1, generator='tools/prepare-original-audio.py',
                        ffmpeg=version, resampler=RESAMPLER, clips=[])
    for clip in clips:
        source = ORIGINALS / (clip['id'] + '.wav')
        data = source.read_bytes()
        if len(data) != clip['bytes'] or digest(data) != clip['sha256']:
            raise ValueError('Canonical original has changed: ' + clip['id'])
        if wav_format(data) != (clip['samples'], clip['sample_rate'], clip['channels'], clip['bits_per_sample'], 'NONE'):
            raise ValueError('Unexpected canonical WAV format: ' + clip['id'])
        target = OUTPUT / source.name
        if not args.check:
            subprocess.run([args.ffmpeg, '-v', 'error', '-y', '-i', str(source),
                            '-map_metadata', '-1', '-af', RESAMPLER, '-ac', '1',
                            '-c:a', 'pcm_s16le', '-fflags', '+bitexact', '-flags:a', '+bitexact',
                            str(target)], check=True)
        data = target.read_bytes()
        samples, rate, channels, bits, compression = wav_format(data)
        if (rate, channels, bits, compression) != (SAMPLE_RATE, 1, 16, 'NONE'):
            raise ValueError('Unexpected playback WAV format: ' + clip['id'])
        if abs(samples / rate - clip['samples'] / clip['sample_rate']) > 1 / rate:
            raise ValueError('Playback duration changed: ' + clip['id'])
        entry = dict(id=clip['id'], sourceSha256=clip['sha256'],
                     url='./audio/originals/playback/' + source.name,
                     sha256=digest(data), bytes=len(data), samples=samples, sampleRate=rate)
        if args.check:
            if entry != next(row for row in manifest['clips'] if row['id'] == clip['id']):
                raise ValueError('Stale playback asset: ' + clip['id'])
        else:
            manifest['clips'].append(entry)
    if not args.check:
        (OUTPUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('Verified three canonical originals and 44.1 kHz listening copies.')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Encode the project's existing public human-voice samples as Codec2 3200."""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path
import wave

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
BUILD = REPO / 'build/codec2/existing-speech'
OUT = ROOT / 'validation/existing-speech-3200'
FIXTURE = ROOT / 'fixtures/existing-speech.json'
CLIPS = [
    ('balloon', 'С воздушным шаром можно кого хочешь утешить.',
     'i8080/Sound/voice32/source-16000.wav', 'i8080/Sound/voice32/SOURCE.json',
     '004e4fa2415038b7c74901728cb76c795e7420df324752ac043bcceeae7fd149'),
    ('owl', 'Сова! Открывай! Медведь пришёл!',
     'i8080/Sound/voice32/owl/source-16000.wav', 'i8080/Sound/voice32/owl/SOURCE.json',
     'f9e3c280848bd6496895bbaf7dc1e876362d63f870a3bac13e3fd8419edfa244'),
    ('chego', 'Чего тебе нужно?', 'web-player/audio/originals/chego.wav',
     'web-player/audio/originals/README.md',
     'c6cdbd26696bdd11695f2491f1558dd246a6f8109fd400e37d292a4d38cdb08c'),
    ('otvechaesh', 'Что ж ты не отвечаешь?', 'web-player/audio/originals/otvechaesh.wav',
     'web-player/audio/originals/README.md',
     '96c09f80396643dd80efb9c5c8557d83359eeb829a0b855a7f8f5c32bbff0b96'),
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', action='store_true', required=True,
                        help='Explicitly save the new public-source fixture and source WAVs')
    parser.parse_args()
    ffmpeg = shutil.which('ffmpeg')
    assert ffmpeg, 'FFmpeg with libcodec2 and libsoxr is required'
    version = subprocess.check_output([ffmpeg, '-version'], text=True).splitlines()[0]
    BUILD.mkdir(parents=True, exist_ok=True)
    records = []
    for name, title, relative, provenance, wanted in CLIPS:
        source = REPO / relative
        assert digest(source.read_bytes()) == wanted, relative
        with wave.open(str(source), 'rb') as w:
            assert (w.getnchannels(), w.getsampwidth()) == (1, 2)
            source_rate, source_frames = w.getframerate(), w.getnframes()
        raw = BUILD / (name + '.resampled.pcm')
        subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
            '-map_metadata', '-1', '-af', 'aresample=8000:resampler=soxr:precision=28:cheby=1:dither_method=none',
            '-ac', '1', '-ar', '8000', '-c:a', 'pcm_s16le', '-f', 's16le', str(raw)], check=True)
        pcm = raw.read_bytes()
        assert len(pcm) % 2 == 0
        samples = len(pcm) // 2
        # Preserve the final speech through encoder analysis and synthesis delay.
        # No speed/pitch change, normalization, denoising or automatic trimming.
        padding = (-samples) % 160
        pcm += bytes(2 * (padding + 5 * 160))
        raw.write_bytes(pcm)
        packets_file = BUILD / (name + '.packets')
        subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
            '-f', 's16le', '-ar', '8000', '-ac', '1', '-i', str(raw),
            '-c:a', 'libcodec2', '-mode', '0', '-f', 'codec2raw', str(packets_file)], check=True)
        packets = packets_file.read_bytes()
        frames = len(pcm) // 320
        assert len(packets) == frames * 8, (name, len(packets), frames)
        folder = OUT / name
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / 'source-8k.wav'
        with wave.open(str(path), 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(pcm)
        records.append({'id': name, 'title': title, 'source_path': relative,
            'source_provenance_path': provenance, 'source_sha256': wanted,
            'source_rate_hz': source_rate, 'source_samples': source_frames,
            'resampled_samples': samples, 'partial_frame_padding_samples': padding,
            'flush_frames': 5, 'frames': frames, 'input_pcm_sha256': digest(pcm),
            'source_8k_wav': path.relative_to(ROOT).as_posix(), 'source_8k_wav_sha256': digest(path.read_bytes()),
            'packet_sha256': digest(packets), 'packets_hex': [packets[i:i+8].hex() for i in range(0, len(packets), 8)]})
        print(f'{name}: {frames} frames from existing human speech', flush=True)
    data = {'schema': 'micromusic-codec2-existing-speech-v1', 'clips': records,
        'source_scope': 'Existing public human-performance source recordings already retained in this project; no new private voice recording and no TTS.',
        'encoder': {'tool': version, 'ffmpeg_binary_sha256': digest(Path(ffmpeg).read_bytes()),
            'codec': 'FFmpeg libcodec2, mode=0 (3200), raw muxer, 8-byte/160-sample frames',
            'library_version_scope': 'Embedded libcodec2 version is not separately exposed. Retained packet bytes and the FFmpeg binary hash identify this encoding; no claim of bit equality to the pinned 1.2.0 encoder.'},
        'preprocessing': 'Mono PCM16/8kHz, libsoxr precision=28 cheby=1 dither_method=none; unchanged speed/pitch/gain. Zero-pad partial final frame then append five zero frames. No automatic latency alignment or trimming.',
        'generator_sha256': digest(Path(__file__).read_bytes())}
    FIXTURE.parent.mkdir(exist_ok=True)
    FIXTURE.write_bytes((json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


if __name__ == '__main__':
    main()

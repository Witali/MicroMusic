#!/usr/bin/env python3
"""Prepare continuous voice streams larger than AVR program Flash."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus', type=Path, default=ROOT/'build/low-corpus')
    p.add_argument('--legacy-root', type=Path, required=True)
    p.add_argument('--oracle', type=Path, required=True)
    p.add_argument('--out', type=Path, default=ROOT/'build/spi-corpus')
    args = p.parse_args()
    rows = []
    for label, width, frames in [('nb11', 28, 1200), ('wb395', 10, 3600),
                                 ('wb575', 15, 2200), ('wb775', 20, 1800), ('wb128', 32, 2200)]:
        source = args.corpus/label/'streams'
        if label == 'nb11': source = args.legacy_root/'build/higher-corpus/nb4/streams'
        if label == 'wb128': source = args.legacy_root/'build/higher-corpus/wb128/streams'
        clips = sorted(path for path in source.glob('*.spxraw') if path.stem.startswith(('ru_', 'en_')))
        # Interleave languages so every continuous file contains both RU and EN.
        english = [path for path in clips if path.stem.startswith('en_')]
        russian = [path for path in clips if path.stem.startswith('ru_')]
        assert len(english) == len(russian) == 8
        clips = [path for pair in zip(russian, english) for path in pair]
        payload = bytearray()
        sources = []
        for path in clips:
            raw = path.read_bytes()
            take = min(len(raw), frames*width-len(payload))
            assert take % width == 0
            payload += raw[:take]
            sources.append(dict(clip=path.stem, sourceSha256=sha(raw), frames=take//width))
            if len(payload) == frames*width: break
        assert len(payload) == frames*width and len(payload) > 32768
        out = args.out/label
        out.mkdir(parents=True, exist_ok=True)
        stream, oracle = out/'long.spxraw', out/'long.pcm'
        stream.write_bytes(payload)
        subprocess.run([str(args.oracle), str(int(label.startswith('wb'))), str(width), stream, oracle], check=True)
        row = dict(profile=label, frames=frames, packetBytes=width, bytes=len(payload),
                   inputSha256=sha(payload), pcmSha256=sha(oracle.read_bytes()),
                   fullHistoryWithoutReset=True, sources=sources)
        rows.append(row)
        print('Prepared', label, frames, 'frames /', len(payload), 'bytes', flush=True)
    (args.out/'manifest.json').write_bytes((json.dumps(dict(streams=rows), indent=2)+'\n').encode())


if __name__ == '__main__':
    main()

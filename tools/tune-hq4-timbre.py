#!/usr/bin/env python3
"""Deterministic HQ4-T encoder search on an external canonical WAV.

Writes temporary outputs only to the specified directory; never edits the frozen
HQ4 release or its training snapshots. Requires codec/requirements.txt.
"""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ATtiny13A/Sound/codec'))
from hq4_core import unpack_stream, pack_stream
from hq4_timbre import decode, metrics, normalized_spectral_error
from pystoi import stoi


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--passes', type=int, default=8)
    parser.add_argument('--seed', type=int, default=23061)
    parser.add_argument('--floor', type=float, default=.9005)
    args = parser.parse_args()
    expected = json.loads((ROOT / 'ATtiny13A/Sound/audio-references.json').read_text(encoding='utf-8'))['clips'][0]
    if hashlib.sha256(args.reference.read_bytes()).hexdigest() != expected['sha256']:
        raise ValueError('Reference must be the canonical chego WAV in audio-references.json')
    ref, sr = sf.read(args.reference)
    if sr != 7500 or ref.ndim != 1 or len(ref) != 9216:
        raise ValueError('Expected 9216 mono samples at 7500 Hz')
    stream_path = ROOT / 'ATtiny13A/Sound/codec/release/chego/speech.hq'
    frames, durations = unpack_stream(stream_path.read_bytes())
    rng = random.Random(args.seed)
    baseline = metrics(ref, decode(frames, durations))
    score, spectral = baseline['stoi'], baseline['spectral_error']
    start_spectral = spectral
    checks = accepted = 0
    history = []

    def assess():
        pcm = decode(frames, durations)
        if np.max(abs(pcm.astype(np.int16) - 128)) > 115 or np.any(abs(np.diff(pcm.astype(np.int16))) >= 48):
            return -1., 9.
        return (float(stoi(ref, (pcm.astype(np.float64) - 128) / 128, sr)),
                normalized_spectral_error(ref, pcm, sr))

    for iteration in range(args.passes):
        order = list(range(len(frames)))
        rng.shuffle(order)
        for idx in order:
            for dim in rng.sample(list(range(11)), 11):
                old = frames[idx].copy()
                candidates = []
                if dim < 8:
                    j, shift = 2 + dim // 2, 4 * (dim & 1)
                    q = (int(old[j]) >> shift) & 15
                    for v in (q - 2, q - 1, q + 1, q + 2):
                        if 0 <= v <= 15:
                            row = old.copy()
                            row[j] = (int(row[j]) & (15 if shift else 240)) | (v << shift)
                            candidates.append(row)
                elif dim == 8:
                    for v in range(max(0, (int(old[1]) & 15) - 2), min(15, (int(old[1]) & 15) + 2) + 1):
                        row = old.copy(); row[1] = (int(old[1]) & 48) | v; candidates.append(row)
                elif dim == 9:
                    for v in range(4):
                        row = old.copy(); row[1] = (int(old[1]) & 15) | v << 4; candidates.append(row)
                else:
                    pitch = int(old[0])
                    for v in (pitch - 2, pitch - 1, pitch + 1, pitch + 2):
                        if 16 <= v <= 126:
                            row = old.copy(); row[0] = v; candidates.append(row)
                best, bs, bsp = old, score, spectral
                recover = score < args.floor
                for row in candidates:
                    frames[idx] = row
                    # 422 decoder bytes, end marker and even link-section padding.
                    if len(pack_stream(frames, durations)) > 600:
                        continue
                    st, ss = assess(); checks += 1
                    better = ((st > bs + .000003 and ss < start_spectral * 1.04) if recover
                              else (st >= args.floor and ss < bsp - .00001))
                    if better:
                        best, bs, bsp = row.copy(), st, ss
                frames[idx] = best
                if not np.array_equal(old, best):
                    score, spectral = bs, bsp; accepted += 1
        item = dict(pass_number=iteration + 1, stoi=score, spectral_error=spectral,
                    stream_bytes=len(pack_stream(frames, durations)), checks=checks, accepted=accepted)
        history.append(item)
        print(json.dumps(item), flush=True)
    if score < args.floor:
        raise RuntimeError('Search did not reach the requested STOI floor; do not publish this candidate')
    args.output.mkdir(parents=True, exist_ok=True)
    pcm = decode(frames, durations)
    (args.output / 'speech.hq').write_bytes(pack_stream(frames, durations))
    (args.output / 'expected.raw').write_bytes(pcm.tobytes())
    sf.write(args.output / 'decoded.wav', (pcm.astype(np.float64) - 128) / 128, sr, subtype='PCM_16')
    report = dict(reference_sha256=expected['sha256'], baseline_stream_sha256=hashlib.sha256(stream_path.read_bytes()).hexdigest(),
                  seed=args.seed, passes=args.passes, stoi_floor=args.floor, initial_filtered=baseline,
                  final=metrics(ref, pcm), history=history, pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest())
    (args.output / 'training.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()

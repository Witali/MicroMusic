#!/usr/bin/env python3
"""Research: clip-trained waveform VQ, 32-sample blocks, 32 four-bit vectors.

This measures a different source representation, not an assembled AVR decoder.
Data budget: 512 codebook bytes + 9 bits per 32-sample block. Decoder budget
must be measured separately; no claim of ATtiny13 compatibility is made here.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ATtiny13A/Sound/codec'))
from auto_encoder import SpectralObjective
from pystoi import stoi


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--starts', type=int, default=12)
    a = p.parse_args()
    reference, sr = sf.read(a.reference)
    objective = SpectralObjective(reference, sr)
    if len(reference) % 32:
        raise ValueError('Reference length must be divisible by 32')
    blocks = (reference * 128).reshape(-1, 32)
    rng = np.random.default_rng(23064)
    best = None
    gains = np.arange(16)
    for start in range(a.starts):
        selected = rng.choice(len(blocks), 32, replace=False)
        book = blocks[selected].copy()
        book = np.rint(book / np.maximum(np.max(abs(book), axis=1, keepdims=True), 1e-9) * 7).clip(-8, 7)
        previous = float('inf')
        for iteration in range(100):
            vectors = (book[:, None, :] * gains[None, :, None]).reshape(-1, 32)
            errors = np.sum(blocks * blocks, axis=1)[:, None] + np.sum(vectors * vectors, axis=1)[None, :] - 2 * blocks @ vectors.T
            assignment = np.argmin(errors, axis=1)
            loss = float(np.mean(errors[np.arange(len(blocks)), assignment]))
            if previous - loss < 1e-8:
                break
            previous = loss
            ids, amps = assignment // 16, assignment % 16
            for j in range(32):
                mask = (ids == j) & (amps > 0)
                if np.any(mask):
                    weighted = np.sum(blocks[mask] * amps[mask, None], axis=0) / np.sum(amps[mask] ** 2)
                    book[j] = np.rint(weighted).clip(-8, 7)
        # Re-evaluate final assignments after the last codebook update.
        vectors = (book[:, None, :] * gains[None, :, None]).reshape(-1, 32)
        errors = np.sum(blocks * blocks, axis=1)[:, None] + np.sum(vectors * vectors, axis=1)[None, :] - 2 * blocks @ vectors.T
        assignment = np.argmin(errors, axis=1)
        x = vectors[assignment].reshape(-1) / 128
        score = dict(**objective.spectrum(x), stoi=float(stoi(reference, x, sr)))
        if best is None or score['loss'] < best[0]['loss']:
            best = score, book.copy(), assignment.copy(), x.copy()
    score, book, assignment, x = best
    model = dict(schema='wave-vq-probe-v1', sample_rate=sr, samples=len(reference), block_samples=32,
                 codebook=book.astype(int).tolist(), indices=(assignment // 16).tolist(),
                 gains=(assignment % 16).tolist(),
                 reference_sha256=hashlib.sha256(a.reference.read_bytes()).hexdigest())
    data_bytes = 512 + (len(assignment) * 9 + 7) // 8
    report = dict(**score, reference_sha256=model['reference_sha256'],
                  source_sha256=hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode('utf-8')).hexdigest(),
                  data_bytes=data_bytes, remaining_flash_for_decoder=1024-data_bytes,
                  hardware_verified=False, avr_decoder_assembled=False, starts=a.starts,
                  waveform_snr_db=float(10*np.log10(np.sum(reference**2)/np.sum((reference-x)**2))))
    a.output.mkdir(parents=True, exist_ok=True)
    for name, value in [('model.json', model), ('quality.json', report)]:
        (a.output / name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8', newline='\n')
    sf.write(a.output / 'decoded.wav', x, sr, subtype='PCM_16')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

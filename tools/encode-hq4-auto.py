#!/usr/bin/env python3
"""Optimize a HQ4-T stream against an external WAV; checkpoint and resume.

Example: python tools/encode-hq4-auto.py --reference external.wav --output build/search
The input stream must already fit the decoder and meet the requested STOI floor.
"""
import argparse
import hashlib
import importlib.metadata
import json
import sys
import time
from pathlib import Path
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ATtiny13A/Sound/codec'))
from auto_encoder import EncoderSearch, SpectralObjective, VERSION, DECODER_BYTES
from hq4_core import unpack_stream, pack_stream
from hq4_timbre import decode


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')
    temporary.replace(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--input-stream', type=Path, default=ROOT / 'ATtiny13A/Sound/codec/timbre/chego/speech.hq')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--proposals', type=int, default=30000, help='Total proposal count, including a resumed run')
    p.add_argument('--floor', type=float, default=.9005)
    p.add_argument('--seed', type=int, default=23062)
    p.add_argument('--restart-every', type=int, default=3000)
    p.add_argument('--temperature', type=float, default=.008)
    p.add_argument('--checkpoint-every', type=int, default=500)
    p.add_argument('--resume', type=Path)
    p.add_argument('--reference-sha256')
    a = p.parse_args()
    if a.proposals < 0 or a.checkpoint_every < 1:
        p.error('Proposal count must be nonnegative and checkpoint interval positive')
    reference_hash = digest(a.reference.read_bytes())
    if a.reference_sha256 and a.reference_sha256 != reference_hash:
        p.error('Reference SHA-256 mismatch')
    reference, sr = sf.read(a.reference)
    objective = SpectralObjective(reference, sr)
    source_paths = ['ATtiny13A/Sound/codec/model.py', 'ATtiny13A/Sound/codec/hq4_timbre.py',
                    'ATtiny13A/Sound/codec/auto_encoder.py', 'tools/encode-hq4-auto.py']
    inputs = dict(reference_sha256=reference_hash, input_stream_sha256=digest(a.input_stream.read_bytes()),
                  source_sha256={path: digest((ROOT / path).read_text(encoding='utf-8').encode('utf-8'))
                                 for path in source_paths})
    saved = json.loads(a.resume.read_text(encoding='utf-8')) if a.resume else None
    if saved and saved['inputs'] != inputs:
        p.error('Checkpoint reference, input stream or encoder sources have changed')
    f, d = unpack_stream(a.input_stream.read_bytes())
    search = EncoderSearch(objective, f, d, floor=a.floor, seed=a.seed,
                           restart_every=a.restart_every, temperature=a.temperature,
                           checkpoint=saved['search'] if saved else None)
    a.output.mkdir(parents=True, exist_ok=True)
    versions = {name: importlib.metadata.version(name) for name in ('numpy', 'scipy', 'numba', 'pystoi', 'soundfile')}
    start = time.monotonic()

    def save(status):
        f, d, score = search.best
        if not search.feasible(score):
            raise RuntimeError('Refusing to export an infeasible elite')
        stream = pack_stream(f, d)
        pcm = decode(f, d)
        report = dict(schema=VERSION, inputs=inputs, runtime=versions, sample_rate=sr,
                      samples=len(reference), config=search.config, status=status,
                      proposals=search.proposals, evaluated=search.evaluated,
                      accepted=search.accepted, improvements=search.improvements,
                      initial=search.initial, final=score, flash_bytes=DECODER_BYTES + len(stream) + 1,
                      stream_sha256=digest(stream), pcm_sha256=digest(pcm.tobytes()), history=search.history)
        (a.output / 'speech.hq').write_bytes(stream)
        (a.output / 'expected.raw').write_bytes(pcm.tobytes())
        sf.write(a.output / 'decoded.wav', (pcm.astype(float) - 128) / 128, sr, subtype='PCM_16')
        atomic_json(a.output / 'training.json', report)
        atomic_json(a.output / 'checkpoint.json', dict(inputs=inputs, search=search.checkpoint()))
        print(json.dumps(dict(proposals=search.proposals, evaluated=search.evaluated,
                              improvements=search.improvements, seconds=round(time.monotonic()-start, 1),
                              **score)), flush=True)

    print(json.dumps(dict(start=search.proposals, initial=search.initial, versions=versions)), flush=True)
    try:
        while search.proposals < a.proposals:
            search.step()
            if search.proposals % a.checkpoint_every == 0:
                save('searching')
    except KeyboardInterrupt:
        save('interrupted')
        return
    save('complete')


if __name__ == '__main__':
    main()

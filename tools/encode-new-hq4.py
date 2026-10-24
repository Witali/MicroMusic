"""Encode a complete external prepared WAV for the original 406-byte HQ4 core.

The input must be mono PCM at 7500 Hz with a multiple-of-64 sample count. This
tool never trims, time-stretches, transposes or silently drops any input sample.
Generated audio and firmware intermediates belong in an ignored build folder.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

import numpy as np
import soundfile as sf
from scipy.signal import sosfilt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from new_hq4_encoder import (VERSION, DECODER_BYTES, MAX_STREAM_BYTES, Objective,
                             initial_model, search, validate_reference)
from hq4_core import pack_stream
from hq4_speech_search import validate
from model import decode


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--proposals', type=int, default=2500)
    p.add_argument('--seed', type=int, default=23105)
    p.add_argument('--stream-budget', type=int, default=MAX_STREAM_BYTES)
    p.add_argument('--initial-model', type=Path, help='Resume from an exported model.json instead of reanalysis')
    a = p.parse_args()
    reference, sr = sf.read(a.reference, dtype='float64')
    validate_reference(reference, sr)
    if a.proposals < 0 or not 8 <= a.stream_budget <= MAX_STREAM_BYTES:
        p.error('Invalid proposal count or stream budget (maximum 617 bytes)')
    a.output.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    if a.initial_model:
        model = json.loads(a.initial_model.read_text(encoding='utf-8'))
        if model['reference_sha256'] != sha(a.reference.read_bytes()):
            p.error('Initial model belongs to a different reference')
        # Validate wide integers before conversion, so malformed values cannot
        # wrap to apparently valid byte fields or durations.
        frames = np.asarray(model['frames'], np.int64)
        durations = np.asarray(model['durations'], np.int64)
        validate(frames, durations, len(reference))
        frames = frames.astype(np.uint8)
        durations = durations.astype(np.uint16)
        initializer = dict(imported_model_sha256=sha(a.initial_model.read_bytes()))
        trials = []
    else:
        (frames, durations, score, initializer), trials = initial_model(reference, stream_budget=a.stream_budget)
        print(json.dumps(dict(stage='initialized', settings=initializer, **score)), flush=True)
    initial_pcm = decode(frames, durations, 0)
    def progress(count, score):
        print(json.dumps(dict(stage='search', proposals=count,
                              elapsed_seconds=round(time.monotonic()-start, 2), **score)), flush=True)
    frames, durations, training = search(reference, frames, durations, proposals=a.proposals,
                                         seed=a.seed, stream_budget=a.stream_budget, progress=progress)
    payload = pack_stream(frames, durations)
    pcm = decode(frames, durations, 0)
    if len(pcm) != len(reference) or len(payload) > a.stream_budget:
        raise RuntimeError('Export violates full-recording or stream-budget contract')
    model = dict(schema=VERSION, sample_rate=sr, samples=len(reference),
                 reference_sha256=sha(a.reference.read_bytes()), frames=frames.tolist(),
                 durations=durations.tolist(), stream_sha256=sha(payload),
                 decoder='original HQ4 signed eight-bit lattice', stream_budget=a.stream_budget)
    sources = ['tools/encode-new-hq4.py', 'ATtiny13A/Sound/codec/new_hq4_encoder.py',
               'ATtiny13A/Sound/codec/model.py', 'ATtiny13A/Sound/codec/hq4_core.py',
               'ATtiny13A/Sound/codec/hq4_speech_search.py', 'ATtiny13A/Sound/codec/auto_encoder.py']
    report = dict(schema=VERSION, samples=len(reference), sample_rate=sr,
                  complete_recording=True, assembled=False, hardware_tested=False,
                  reference_sha256=model['reference_sha256'], initializer=initializer,
                  seed=a.seed, stream_budget=a.stream_budget, decoder_bytes=DECODER_BYTES,
                  stream_bytes=len(payload), estimated_flash_bytes=(DECODER_BYTES+len(payload)+2)//2*2,
                  stream_sha256=sha(payload), pcm_sha256=sha(pcm.tobytes()),
                  elapsed_seconds=round(time.monotonic()-start, 3),
                  runtime={n: importlib.metadata.version(n) for n in ('numpy', 'scipy', 'numba', 'soundfile', 'pystoi')},
                  sources_sha256_normalized_lf={name: sha((ROOT/name).read_text(encoding='utf-8').encode('utf-8')) for name in sources},
                  **training)
    for name, value in (('model.json', model), ('training.json', report), ('initialization.json', trials)):
        (a.output/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8', newline='\n')
    (a.output/'speech.hq').write_bytes(payload)
    (a.output/'expected.raw').write_bytes(pcm.tobytes())
    sf.write(a.output/'decoded.wav', (pcm.astype(float)-128)/128, sr, subtype='PCM_16')
    objective = Objective(reference)
    filtered = [sosfilt(objective.hp, x) for x in (reference, (initial_pcm.astype(float)-128)/128, (pcm.astype(float)-128)/128)]
    matched = [x*objective.rms/(np.sqrt(np.mean(x*x))+1e-10) for x in filtered]
    scale = .85/max(float(np.max(abs(x))) for x in matched)
    matched = [x*scale for x in matched]
    for name, audio in zip(('original-matched', 'initial-matched', 'after-matched'), matched):
        sf.write(a.output/(name+'.wav'), audio, sr, subtype='PCM_16')
    gap = np.zeros(round(.3*sr))
    sf.write(a.output/'comparison.wav', np.concatenate([part for i in (0, 2) for part in (matched[i], gap)]), sr, subtype='PCM_16')
    print(json.dumps(dict(stage='complete', output=str(a.output), **report['final'])), flush=True)


if __name__ == '__main__':
    main()

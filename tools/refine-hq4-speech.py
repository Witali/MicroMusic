"""Improve an existing original HQ4 stream under its baseline STOI/eSTOI guards.

Generated WAV, checkpoints and firmware candidates belong in ignored build/.
The frozen release and public catalog are not modified by this tool.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.signal import sosfilt
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_core import pack_stream, unpack_stream
from hq4_speech_search import SpeechObjective, SpeechSearch, DECODER_BYTES, VERSION
from model import decode
from speech_spectrum import PersistentSpectrumObjective


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8', newline='\n')
    temporary.replace(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--clip', required=True, choices=('chego', 'otvechaesh', 'vinni'))
    p.add_argument('--reference', required=True, type=Path)
    p.add_argument('--input-stream', type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--proposals', type=int, default=6000)
    p.add_argument('--seed', type=int, default=23101)
    p.add_argument('--restart-every', type=int, default=1500)
    p.add_argument('--temperature', type=float, default=.004)
    p.add_argument('--band-weight', type=float, default=.2)
    p.add_argument('--checkpoint-every', type=int, default=500)
    p.add_argument('--resume', type=Path)
    a = p.parse_args()
    if a.proposals < 0 or a.checkpoint_every < 1:
        p.error('Invalid proposal or checkpoint count')
    source = a.input_stream or ROOT/'ATtiny13A/Sound/codec/release'/a.clip/'speech.hq'
    frozen = ROOT/'ATtiny13A/Sound/codec/release'/a.clip/'speech.hq'
    source_bytes = source.read_bytes()
    reference_bytes = a.reference.read_bytes()
    reference, sr = sf.read(a.reference)
    band_objective = PersistentSpectrumObjective(reference, sr)
    objective = SpeechObjective(reference, sr, band_objective=band_objective, band_weight=a.band_weight)
    f, d = unpack_stream(source_bytes)
    if pack_stream(f, d) != source_bytes:
        p.error('Input HQ4 stream must be canonical, without an embedded EOF marker')
    paths = ['tools/refine-hq4-speech.py', 'ATtiny13A/Sound/codec/hq4_speech_search.py',
             'ATtiny13A/Sound/codec/model.py', 'ATtiny13A/Sound/codec/hq4_core.py',
             'ATtiny13A/Sound/codec/auto_encoder.py', 'ATtiny13A/Sound/codec/speech_spectrum.py']
    inputs = dict(reference_sha256=sha(reference_bytes), input_stream_sha256=sha(source_bytes),
                  frozen_stream_sha256=sha(frozen.read_bytes()),
                  sources_sha256_normalized_lf={path: sha((ROOT/path).read_text(encoding='utf-8').encode('utf-8'))
                                                for path in paths})
    saved = json.loads(a.resume.read_text(encoding='utf-8')) if a.resume else None
    if saved and saved['inputs'] != inputs:
        p.error('Checkpoint input or encoder sources changed')
    search = SpeechSearch(objective, f, d, seed=a.seed, restart_every=a.restart_every,
                          temperature=a.temperature, checkpoint=saved['search'] if saved else None)
    runtime = {name: importlib.metadata.version(name) for name in ('numpy', 'scipy', 'numba', 'soundfile', 'pystoi')}
    a.output.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()

    def save(status):
        frames, durations, score = search.best
        if not search.feasible(score):
            raise RuntimeError('Refusing an elite that weakens the baseline guards')
        payload = pack_stream(frames, durations)
        pcm = decode(frames, durations, 0)
        report = dict(schema=VERSION, clip=a.clip, status=status, runtime=runtime,
                      inputs=inputs, samples=len(reference), sample_rate=sr,
                      decoder='original HQ4 signed eight-bit lattice',
                      assembled=False, hardware_tested=False,
                      config=search.config, initial=search.initial, final=score,
                      proposals=search.proposals, evaluated=search.evaluated,
                      accepted=search.accepted, improvements=search.improvements,
                      decoder_bytes=DECODER_BYTES, stream_bytes=len(payload),
                      estimated_flash_bytes=(DECODER_BYTES+len(payload)+2)//2*2,
                      stream_sha256=sha(payload), pcm_sha256=sha(pcm.tobytes()),
                      history=search.history)
        (a.output/'speech.hq').write_bytes(payload)
        (a.output/'expected.raw').write_bytes(pcm.tobytes())
        sf.write(a.output/'decoded.wav', (pcm.astype(float)-128)/128, sr, subtype='PCM_16')
        baseline = (decode(f, d, 0).astype(float)-128)/128
        candidate = (pcm.astype(float)-128)/128
        filtered = [sosfilt(objective.hp, x) for x in (reference, baseline, candidate)]
        matched = [x*objective.rms/(np.sqrt(np.mean(x*x))+1e-10) for x in filtered]
        scale = .85/max(float(np.max(abs(x))) for x in matched)
        matched = [x*scale for x in matched]
        for label, audio in zip(('original-matched', 'before-matched', 'after-matched'), matched):
            sf.write(a.output/(label+'.wav'), audio, sr, subtype='PCM_16')
        gap = np.zeros(round(.3*sr))
        comparison = np.concatenate([part for i in (0, 1, 0, 2) for part in (matched[i], gap)])
        sf.write(a.output/'comparison.wav', comparison, sr, subtype='PCM_16')
        write_json(a.output/'training.json', report)
        write_json(a.output/'checkpoint.json', dict(inputs=inputs, search=search.checkpoint()))
        print(json.dumps(dict(proposals=search.proposals, evaluated=search.evaluated,
                              improvements=search.improvements,
                              elapsed_seconds=round(time.monotonic()-start, 1), **score)), flush=True)

    print(json.dumps(dict(clip=a.clip, start=search.proposals, initial=search.initial,
                          guards=search.config)), flush=True)
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

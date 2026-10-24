#!/usr/bin/env python3
"""Measure high-band noise-envelope extension over retained period-wave models."""
import argparse
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import sosfilt
from pystoi import stoi

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT / 'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from period_wave import decode_model, packed_bytes
from period_residual import decode_residual, fit_residual, pack_residual, unpack_residual


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--references', type=Path, required=True)
    p.add_argument('--models', type=Path, default=ROOT / 'ATtiny13A/Sound/research/period-wave')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--proposals', type=int, default=3000)
    a = p.parse_args()
    if a.proposals < 0:
        p.error('Proposal count must be nonnegative')
    manifest = json.loads((ROOT / 'ATtiny13A/Sound/audio-references.json').read_text(encoding='utf-8'))
    results = []
    for clip in manifest['clips']:
        source = a.references / clip['id'] / 'original.wav'
        if digest(source.read_bytes()) != clip['sha256']:
            raise ValueError('Reference hash mismatch')
        reference, sr = sf.read(source)
        objective = SpectralObjective(reference, sr)
        model_path = a.models / clip['id'] / 'model.json'
        base = json.loads(model_path.read_text(encoding='utf-8'))
        if base['samples'] != len(reference):
            raise ValueError('Duration mismatch')
        model, search = fit_residual(base, objective, a.proposals)
        payload = pack_residual(model)
        output = a.output / clip['id']
        output.mkdir(parents=True, exist_ok=True)
        decoded = decode_residual(unpack_residual(payload))
        if not np.array_equal(decoded, decode_residual(model)):
            raise AssertionError('Residual payload changed audio')
        report = dict(clip_id=clip['id'], reference_sha256=clip['sha256'], base_model_sha256=digest(model_path.read_bytes()),
                      payload_sha256=digest(payload), data_bytes=len(payload), extra_data_bytes=len(payload)-len(packed_bytes(base)),
                      available_flash_after_data=1024-len(payload), avr_assembled=False, hardware_verified=False, search=search, metrics={})
        audio = dict(Original=reference, Period=decode_model(base), Residual=decoded)
        for name in ('Period', 'Residual'):
            report['metrics'][name] = dict(**objective.spectrum(audio[name]), stoi=float(stoi(reference, audio[name], sr)))
        write_json(output / 'model.json', model)
        write_json(output / 'quality.json', report)
        (output / 'speech.pwr').write_bytes(payload)
        balanced = {name: sosfilt(objective.hp, x) for name, x in audio.items()}
        balanced = {name: x*objective.rms/(np.sqrt(np.mean(x*x))+1e-12) for name, x in balanced.items()}
        scale = .85/max(np.max(abs(x)) for x in balanced.values())
        for name in balanced:
            sf.write(output / (name.lower()+'.wav'), balanced[name]*scale, sr, subtype='PCM_16')
        sequence = np.concatenate([np.r_[balanced[name]*scale, np.zeros(round(sr*.3))] for name in ('Original', 'Period', 'Original', 'Residual')])
        sf.write(output / 'comparison.wav', sequence, sr, subtype='PCM_16')
        results.append(report)
        print(json.dumps(report), flush=True)
    sources = [CODEC / 'period_residual.py', CODEC / 'period_wave.py', CODEC / 'auto_encoder.py', Path(__file__)]
    fingerprints = {str(path.relative_to(ROOT)).replace('\\', '/'):digest(path.read_text(encoding='utf-8').encode()) for path in sources}
    runtime = {name:importlib.metadata.version(name) for name in ('numpy', 'scipy', 'pystoi', 'soundfile')}
    runtime['python'] = sys.version.split()[0]
    write_json(a.output / 'quality.json', dict(schema='period-residual-experiment-v1', runtime=runtime,
               sources_sha256_normalized_lf=fingerprints, clips=results))


if __name__ == '__main__':
    main()

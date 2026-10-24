#!/usr/bin/env python3
"""Jointly refine retained period/residual models; preserve byte budget and resume."""
import argparse
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import sosfilt

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT / 'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from joint_period import JointSearch
from period_residual import decode_residual, pack_residual, unpack_residual


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')
    temporary.replace(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--references', type=Path, required=True)
    p.add_argument('--models', type=Path, default=ROOT / 'ATtiny13A/Sound/research/period-wave')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--clip', choices=['all', 'chego', 'otvechaesh', 'vinni'], default='all')
    p.add_argument('--proposals', type=int, default=12000)
    p.add_argument('--weight', type=float, default=6.)
    p.add_argument('--resume', action='store_true')
    a = p.parse_args()
    if a.proposals < 0 or a.weight <= 0:
        p.error('Invalid proposals or weight')
    sources = [CODEC / 'joint_period.py', CODEC / 'period_residual.py', CODEC / 'period_wave.py',
               CODEC / 'auto_encoder.py', Path(__file__)]
    fingerprints = {str(path.relative_to(ROOT)).replace('\\', '/'):digest(path.read_text(encoding='utf-8').encode()) for path in sources}
    runtime = {name:importlib.metadata.version(name) for name in ('numpy', 'scipy', 'pystoi', 'soundfile')}
    runtime['python'] = sys.version.split()[0]
    manifest = json.loads((ROOT / 'ATtiny13A/Sound/audio-references.json').read_text(encoding='utf-8'))
    reports = []
    for clip in manifest['clips']:
        if a.clip != 'all' and a.clip != clip['id']:
            continue
        source = a.references / clip['id'] / 'original.wav'
        if digest(source.read_bytes()) != clip['sha256']:
            raise ValueError('Reference hash mismatch')
        reference, sr = sf.read(source)
        objective = SpectralObjective(reference, sr)
        model_path = a.models / clip['id'] / 'residual-model.json'
        model = json.loads(model_path.read_text(encoding='utf-8'))
        if model['base']['samples'] != len(reference):
            raise ValueError('Duration mismatch')
        output = a.output / clip['id']
        output.mkdir(parents=True, exist_ok=True)
        inputs = dict(reference_sha256=clip['sha256'], initial_model_sha256=digest(model_path.read_bytes()), sources_sha256_normalized_lf=fingerprints)
        saved = json.loads((output / 'checkpoint.json').read_text(encoding='utf-8')) if a.resume else None
        if saved and saved['inputs'] != inputs:
            raise ValueError('Checkpoint input/source hashes differ')
        search = JointSearch(model, objective, stoi_weight=a.weight, checkpoint=saved['search'] if saved else None)

        def save(status):
            elite = search.export()
            payload = pack_residual(elite)
            score = search.score(decode_residual(unpack_residual(payload)))
            report = dict(schema='joint-period-report-v1', clip_id=clip['id'], inputs=inputs, runtime=runtime,
                          config=search.config, initial=search.initial, final=score, proposals=search.proposals,
                          evaluated=search.evaluated, improvements=search.improvements, history=search.history,
                          data_bytes=len(payload), available_flash_after_data=1024-len(payload),
                          payload_sha256=digest(payload), avr_assembled=False, hardware_verified=False, status=status)
            atomic_json(output / 'model.json', elite)
            atomic_json(output / 'quality.json', report)
            atomic_json(output / 'checkpoint.json', dict(inputs=inputs, search=search.checkpoint()))
            print(json.dumps(dict(clip=clip['id'], proposals=search.proposals, **score)), flush=True)
            return report

        try:
            while search.proposals < a.proposals:
                search.step()
                if search.proposals % 3000 == 0:
                    save('searching')
        except KeyboardInterrupt:
            save('interrupted')
            return
        report = save('complete')
        reports.append(report)
        clips = dict(Original=reference, Before=decode_residual(model), Joint=decode_residual(search.export()))
        balanced = {name:sosfilt(objective.hp, audio) for name,audio in clips.items()}
        balanced = {name:audio*objective.rms/(np.sqrt(np.mean(audio*audio))+1e-12) for name,audio in balanced.items()}
        scale = .85/max(np.max(abs(audio)) for audio in balanced.values())
        for name,audio in balanced.items():
            sf.write(output / (name.lower()+'.wav'), audio*scale, sr, subtype='PCM_16')
        sequence = np.concatenate([np.r_[balanced[name]*scale, np.zeros(round(sr*.3))] for name in ('Original', 'Before', 'Original', 'Joint')])
        sf.write(output / 'comparison.wav', sequence, sr, subtype='PCM_16')
    if any(digest(path.read_text(encoding='utf-8').encode()) != fingerprints[str(path.relative_to(ROOT)).replace('\\', '/')] for path in sources):
        raise RuntimeError('Encoder sources changed during the experiment')
    atomic_json(a.output / 'quality.json', dict(schema='joint-period-experiment-v1', clips=reports))


if __name__ == '__main__':
    main()

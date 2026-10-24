#!/usr/bin/env python3
"""Automatically reduce spectral error without losing attained speech STOI."""
import argparse
import importlib.metadata
import json
import sys
from pathlib import Path
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT / 'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from balanced_period import SpectralFrameSearch, SpectralBookSearch
from colored_period import ColoredSynthesis, decode_colored, pack_colored, unpack_colored
from refine_period_helpers import digest, atomic_json, matched_audio


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--references', type=Path, required=True)
    p.add_argument('--models', type=Path, default=ROOT / 'ATtiny13A/Sound/research/period-book')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--frame-proposals', type=int, default=4000)
    p.add_argument('--book-proposals', type=int, default=6000)
    p.add_argument('--resume', action='store_true')
    a = p.parse_args()
    if a.frame_proposals < 0 or a.book_proposals < 0:
        p.error('Invalid proposal count')
    sources = [CODEC / name for name in ('balanced_period.py', 'period_book_search.py', 'colored_period.py', 'joint_period.py', 'period_residual.py', 'period_wave.py', 'auto_encoder.py')]
    sources += [Path(__file__), ROOT / 'tools/refine_period_helpers.py']
    fingerprints = {str(path.relative_to(ROOT)).replace('\\', '/'):digest(path.read_text(encoding='utf-8').encode()) for path in sources}
    runtime = {name:importlib.metadata.version(name) for name in ('numpy', 'scipy', 'pystoi', 'soundfile')}
    runtime['python'] = sys.version.split()[0]
    manifest = json.loads((ROOT / 'ATtiny13A/Sound/audio-references.json').read_text(encoding='utf-8'))
    reports = []
    for clip in manifest['clips']:
        source = a.references / clip['id'] / 'original.wav'
        if digest(source.read_bytes()) != clip['sha256']:
            raise ValueError('Reference hash mismatch')
        reference, sr = sf.read(source)
        objective = SpectralObjective(reference, sr)
        path = a.models / clip['id'] / 'model.json'
        initial = model = json.loads(path.read_text(encoding='utf-8'))
        if model['base']['samples'] != len(reference):
            raise ValueError('Duration mismatch')
        output = a.output / clip['id']
        output.mkdir(parents=True, exist_ok=True)
        floor, stages = None, []
        for kind, cls, count in [('frames', SpectralFrameSearch, a.frame_proposals), ('book', SpectralBookSearch, a.book_proposals)]:
            inputs = dict(reference_sha256=clip['sha256'], input_model_sha256=digest(json.dumps(model, sort_keys=True).encode()), sources_sha256_normalized_lf=fingerprints)
            checkpoint_path = output / (kind+'-checkpoint.json')
            saved = json.loads(checkpoint_path.read_text(encoding='utf-8')) if a.resume and checkpoint_path.exists() else None
            if saved and saved['inputs'] != inputs:
                raise ValueError('Checkpoint input/source hashes differ')
            kwargs = dict(seed=23072 if kind=='frames' else 23073, stoi_floor=floor,
                          checkpoint=saved['search'] if saved else None)
            if kind == 'frames':
                kwargs['cache_factory'] = ColoredSynthesis
            search = cls(model, objective, **kwargs)
            if floor is None:
                floor = search.config['stoi_floor']

            def save(status):
                elite = search.export()
                payload = pack_colored(elite)
                score = search.score(decode_colored(unpack_colored(payload)))
                if score['stoi'] < floor-1e-12 or score['loss'] > search.initial['loss']+1e-12:
                    raise AssertionError('Balanced export loses intelligibility or increases spectral loss')
                report = dict(stage=kind, inputs=inputs, config=search.config, initial=search.initial, final=score,
                              proposals=search.proposals, evaluated=search.evaluated, improvements=search.improvements,
                              data_bytes=len(payload), payload_sha256=digest(payload), history=search.history, status=status)
                atomic_json(output / (kind+'-quality.json'), report)
                atomic_json(checkpoint_path, dict(inputs=inputs, search=search.checkpoint()))
                print(json.dumps(dict(clip=clip['id'], stage=kind, proposals=search.proposals, **score)), flush=True)
                return report

            try:
                while search.proposals < count:
                    search.step()
                    if search.proposals % 2000 == 0:
                        save('searching')
            except KeyboardInterrupt:
                save('interrupted')
                return
            stages.append(save('complete'))
            model = search.export()
        report = dict(schema='balanced-period-report-v1', clip_id=clip['id'], runtime=runtime,
                      reference_sha256=clip['sha256'], initial_model_sha256=digest(path.read_bytes()),
                      stoi_floor=floor, stages=stages, initial=stages[0]['initial'], final=stages[-1]['final'],
                      avr_assembled=False, hardware_verified=False)
        atomic_json(output / 'model.json', model)
        atomic_json(output / 'quality.json', report)
        reports.append(report)
        matched_audio(output, dict(Original=reference, Before=decode_colored(initial), Balanced=decode_colored(model)), objective,
                      ('Original', 'Before', 'Original', 'Balanced'))
    if any(digest(path.read_text(encoding='utf-8').encode()) != fingerprints[str(path.relative_to(ROOT)).replace('\\', '/')] for path in sources):
        raise RuntimeError('Encoder sources changed during the experiment')
    atomic_json(a.output / 'quality.json', dict(schema='balanced-period-experiment-v1', clips=reports))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Refine signed four-bit period dictionaries using intelligibility feedback."""
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
from period_book_search import BookSearch
from colored_period import decode_colored, pack_colored, unpack_colored
from refine_period_helpers import digest, atomic_json, matched_audio


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--references', type=Path, required=True)
    p.add_argument('--models', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--clip', choices=['all', 'chego', 'otvechaesh', 'vinni'], default='all')
    p.add_argument('--proposals', type=int, default=12000)
    p.add_argument('--resume', action='store_true')
    a = p.parse_args()
    if a.proposals < 0:
        p.error('Invalid proposal count')
    sources = [CODEC / name for name in ('period_book_search.py', 'colored_period.py', 'joint_period.py', 'period_residual.py', 'period_wave.py', 'auto_encoder.py')]
    sources += [Path(__file__), ROOT / 'tools/refine_period_helpers.py']
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
        path = a.models / clip['id'] / 'model.json'
        model = json.loads(path.read_text(encoding='utf-8'))
        if model['base']['samples'] != len(reference):
            raise ValueError('Duration mismatch')
        inputs = dict(reference_sha256=clip['sha256'], initial_model_sha256=digest(path.read_bytes()), sources_sha256_normalized_lf=fingerprints)
        output = a.output / clip['id']
        output.mkdir(parents=True, exist_ok=True)
        saved = json.loads((output / 'checkpoint.json').read_text(encoding='utf-8')) if a.resume else None
        if saved and saved['inputs'] != inputs:
            raise ValueError('Checkpoint input/source hashes differ')
        search = BookSearch(model, objective, seed=23071, stoi_weight=8., checkpoint=saved['search'] if saved else None)

        def save(status):
            elite = search.export()
            payload = pack_colored(elite)
            score = search.score(decode_colored(unpack_colored(payload)))
            report = dict(schema='period-book-report-v1', clip_id=clip['id'], inputs=inputs, runtime=runtime,
                          config=search.config, initial=search.initial, final=score, proposals=search.proposals,
                          evaluated=search.evaluated, improvements=search.improvements, history=search.history,
                          data_bytes=len(payload), payload_sha256=digest(payload), status=status,
                          avr_assembled=False, hardware_verified=False)
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
        reports.append(save('complete'))
        matched_audio(output, dict(Original=reference, Before=decode_colored(model), Book=decode_colored(search.export())), objective,
                      ('Original', 'Before', 'Original', 'Book'))
    if any(digest(path.read_text(encoding='utf-8').encode()) != fingerprints[str(path.relative_to(ROOT)).replace('\\', '/')] for path in sources):
        raise RuntimeError('Encoder sources changed during the experiment')
    atomic_json(a.output / 'quality.json', dict(schema='period-book-experiment-v1', clips=reports))


if __name__ == '__main__':
    main()

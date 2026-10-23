#!/usr/bin/env python3
"""Prepare exact voiced/white speech automatically from the retained float model."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
sys.path.insert(0, str(ROOT/'tools'))
import soundfile as sf
from auto_encoder import SpectralObjective
from fixed_period import from_colored, decode_fixed
from fixed_search import FixedSearch
from refine_period_helpers import atomic_json, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    source = ROOT/'ATtiny13A/Sound/research/period-balanced/otvechaesh/model.json'
    manifest = ROOT/'ATtiny13A/Sound/audio-references.json'
    clip = next(c for c in json.loads(manifest.read_text(encoding='utf8'))['clips'] if c['id']=='otvechaesh')
    if digest(args.reference.read_bytes()) != clip['sha256']:
        raise ValueError('Reference SHA-256 does not match canonical otvechaesh')
    reference, sr = sf.read(args.reference)
    objective = SpectralObjective(reference, sr)
    model = from_colored(json.loads(source.read_text(encoding='utf8')))
    model['dc_block_shift'] = 7
    search = FixedSearch(model, objective, stoi_floor=0., spectral_ceiling=1.,
                         max_data_bytes=65535, dc_choices=(7,))
    args.output.mkdir(parents=True, exist_ok=True)
    initial = search.initial
    removed = []
    for index, frame in enumerate(model['frames']):
        if frame[1] & 112 and not frame[1] & 128:
            frame[1] &= 143
            removed.append(index)
        frame[2] &= 15
    before = search.score(model)
    evaluated = 0
    history = []
    for index in range(len(model['frames'])):
        best = None
        for level in range(16):
            candidate = deepcopy(model)
            candidate['frames'][index][2] = level
            score = search.score(candidate)
            evaluated += 1
            if search.feasible(score) and (best is None or search.energy(score) < best[0]):
                best = search.energy(score), candidate, score
        if best is None:
            raise RuntimeError('No valid white residual level for frame '+str(index))
        _, model, score = best
        history.append(dict(frame=index, level=model['frames'][index][2], **score))
        if index % 16 == 15:
            print(json.dumps(dict(frame=index, **score)), flush=True)
    sources = [Path(__file__), ROOT/'tools/refine_period_helpers.py']
    sources += [ROOT/'ATtiny13A/Sound/codec'/name for name in (
        'fixed_period.py','fixed_search.py','dc_blocker.py','colored_period.py','compact_period.py','auto_encoder.py')]
    report = dict(schema='tiny-otvechaesh-preparation-v1', clip_id='otvechaesh',
                  source_model=str(source.relative_to(ROOT)).replace('\\','/'),
                  source_model_sha256=digest(source.read_bytes()), reference_sha256=clip['sha256'],
                  sources_sha256_normalized_lf={str(p.relative_to(ROOT)).replace('\\','/'):
                    digest(p.read_text(encoding='utf8').encode()) for p in sources},
                  config=search.config, initial=initial, removed_unvoiced_base_frames=removed,
                  before_residual_retuning=before, final=search.score(model), evaluated=evaluated,
                  history=history, hardware_verified=False)
    atomic_json(args.output/'prepared-model.json', model)
    atomic_json(args.output/'preparation.json', report)
    (args.output/'expected.raw').write_bytes(decode_fixed(model).tobytes())
    print(json.dumps(dict(stage='complete', **report['final'])), flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Automatically retune speech against the exact integer target decoder."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import sys

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from fixed_period import decode_fixed, from_colored, pack_fixed
from fixed_search import FixedSearch
from refine_period_helpers import atomic_json, digest, matched_audio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--clip', choices=('chego', 'otvechaesh', 'vinni'), default='chego')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--proposals', type=int, default=30000)
    parser.add_argument('--seed', type=int, default=23074)
    parser.add_argument('--weight', type=float, default=8.)
    parser.add_argument('--stoi-floor', type=float)
    parser.add_argument('--spectral-ceiling', type=float)
    parser.add_argument('--max-peak', type=float, default=.95)
    parser.add_argument('--max-data-bytes', type=int)
    parser.add_argument('--dc-shift', choices=(0, 5, 6, 7), type=int, default=7)
    parser.add_argument('--dc-choices', default='5,6,7')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.proposals < 0:
        parser.error('Proposal count must be nonnegative')
    sources = [CODEC/name for name in ('fixed_search.py', 'fixed_period.py', 'dc_blocker.py',
                                      'compact_period.py', 'colored_period.py', 'period_wave.py', 'auto_encoder.py')]
    sources += [Path(__file__), ROOT/'tools/refine_period_helpers.py']
    fingerprints = {str(path.relative_to(ROOT)).replace('\\', '/'):digest(path.read_text(encoding='utf-8').encode()) for path in sources}
    clips = json.loads((ROOT/'ATtiny13A/Sound/audio-references.json').read_text(encoding='utf-8'))['clips']
    clip = next(value for value in clips if value['id'] == args.clip)
    if digest(args.reference.read_bytes()) != clip['sha256']:
        raise ValueError('Reference SHA-256 does not match canonical '+args.clip)
    reference, sr = sf.read(args.reference)
    objective = SpectralObjective(reference, sr)
    model = json.loads(args.model.read_text(encoding='utf-8'))
    if model['schema'] == 'period-colored-v1':
        model = from_colored(model)
    model['dc_block_shift'] = args.dc_shift
    inputs = dict(reference_sha256=clip['sha256'], initial_model_file_sha256=digest(args.model.read_bytes()),
                  sources_sha256_normalized_lf=fingerprints)
    args.output.mkdir(parents=True, exist_ok=True)
    saved = json.loads((args.output/'checkpoint.json').read_text(encoding='utf-8')) if args.resume else None
    if saved and saved['inputs'] != inputs:
        raise ValueError('Checkpoint source/input hashes differ')
    search = FixedSearch(model, objective, seed=args.seed, stoi_weight=args.weight,
                         stoi_floor=args.stoi_floor, spectral_ceiling=args.spectral_ceiling,
                         max_peak=args.max_peak, max_data_bytes=args.max_data_bytes,
                         dc_choices=tuple(int(value) for value in args.dc_choices.split(',')),
                         checkpoint=saved['search'] if saved else None)
    runtime = {name:importlib.metadata.version(name) for name in ('numpy', 'scipy', 'pystoi', 'soundfile', 'numba')}
    runtime['python'] = sys.version.split()[0]

    def save(status):
        elite = search.export()
        payload = pack_fixed(elite)
        score = search.score(elite)
        changed = [str(path.relative_to(ROOT)).replace('\\', '/') for path in sources
                   if digest(path.read_text(encoding='utf-8').encode()) != fingerprints[str(path.relative_to(ROOT)).replace('\\', '/')]]
        report = dict(schema='fixed-speech-training-v1', clip_id=args.clip, inputs=inputs,
                      runtime=runtime, config=search.config, initial=search.initial, final=score,
                      proposals=search.proposals, evaluated=search.evaluated, accepted=search.accepted,
                      improvements=search.improvements, history=search.history,
                      data_bytes=len(payload), payload_sha256=digest(payload),
                      source_files_changed_during_run=changed, avr_assembled=False,
                      hardware_verified=False, status=status)
        atomic_json(args.output/'retuned-model.json', elite)
        atomic_json(args.output/'quality.json', report)
        atomic_json(args.output/'checkpoint.json', dict(inputs=inputs, search=search.checkpoint()))
        (args.output/'speech.bin').write_bytes(payload)
        (args.output/'expected.raw').write_bytes(decode_fixed(elite).tobytes())
        print(json.dumps(dict(proposals=search.proposals, improvements=search.improvements, **score)), flush=True)
        return report

    try:
        while search.proposals < args.proposals:
            search.step()
            if search.proposals % 2000 == 0:
                save('searching')
    except KeyboardInterrupt:
        save('interrupted')
        return
    report = save('complete')
    audio = lambda value:(decode_fixed(value).astype(np.float64)-128)/128
    matched_audio(args.output, dict(Original=reference, Before=audio(model), Fixed=audio(search.export())), objective,
                  ('Original', 'Before', 'Original', 'Fixed'))
    if report['source_files_changed_during_run']:
        raise RuntimeError('Sources changed during search; rescore the saved model before using it')


if __name__ == '__main__':
    main()

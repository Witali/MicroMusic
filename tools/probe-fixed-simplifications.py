#!/usr/bin/env python3
"""Measure integer-decoder simplifications with automatic local gain retuning."""
import argparse
from copy import deepcopy
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
import soundfile as sf
from auto_encoder import SpectralObjective
from fixed_search import FixedSearch
from fixed_period import decode_fixed
from refine_period_helpers import atomic_json, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--variants', choices=('all', 'compact'), default='all')
    args = parser.parse_args()
    original_bytes = args.model.read_bytes()
    model = json.loads(original_bytes)
    clips = json.loads((ROOT/'ATtiny13A/Sound/audio-references.json').read_text(encoding='utf-8'))['clips']
    source_hash = digest(args.reference.read_bytes())
    clip = next((value for value in clips if value['sha256'] == source_hash), None)
    if clip is None:
        raise ValueError('Reference hash is not in canonical manifest')
    reference, sr = sf.read(args.reference)
    objective = SpectralObjective(reference, sr)
    search = FixedSearch(model, objective, dc_choices=(model.get('dc_block_shift', 0),))
    sources = [Path(__file__), ROOT/'tools/refine_period_helpers.py']
    sources += [ROOT/'ATtiny13A/Sound/codec'/name for name in (
        'fixed_period.py', 'fixed_search.py', 'dc_blocker.py', 'auto_encoder.py', 'compact_period.py')]
    fingerprints = {str(path.relative_to(ROOT)).replace('\\', '/'):
                    digest(path.read_text(encoding='utf-8').encode()) for path in sources}
    runtime = {name:importlib.metadata.version(name) for name in ('numpy', 'scipy', 'pystoi', 'soundfile', 'numba')}
    runtime['python'] = sys.version.split()[0]
    score = search.score
    energy = search.energy
    args.output.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output/'source-model.json', model)
    reports = []

    def save(name, value, raw=None):
        result = score(value)
        atomic_json(args.output/(name+'-model.json'), value)
        sf.write(args.output/(name+'.wav'), (decode_fixed(value).astype(float)-128)/128, 7500, subtype='PCM_U8')
        reports.append(dict(variant=name, metrics=result, raw_metrics=raw,
                            stoi_change=result['stoi']-search.initial['stoi'],
                            log_error_change=result['log_spectral_error']-search.initial['log_spectral_error']))
        print(json.dumps(reports[-1]), flush=True)
        atomic_json(args.output/'quality.json', dict(schema='fixed-speech-simplifications-v1',
                    clip_id=clip['id'], source_model_sha256=digest(original_bytes),
                    reference_sha256=source_hash, baseline=search.initial,
                    sources_sha256_normalized_lf=fingerprints, runtime=runtime,
                    objective='spectral_loss+8*(1-STOI)', variants=reports,
                    avr_assembled=False, hardware_verified=False))

    def tune_residual(value, indices, colors):
        for i in sorted(set(indices)):
            choices = []
            for color in colors:
                for level in range(16):
                    candidate = deepcopy(value)
                    candidate['frames'][i][2] = color << 4 | level
                    metrics = score(candidate)
                    if (metrics['peak'] <= .95 and not metrics['clips'] and not metrics['pre_dc_clips'] and
                            metrics['data_bytes'] <= search.config['max_data_bytes']):
                        choices.append((energy(metrics), candidate))
            if choices:
                value = min(choices, key=lambda choice:choice[0])[1]
        return value

    save('baseline', model)
    unvoiced = [i for i,(_,header,_) in enumerate(model['frames']) if not header & 128 and header & 112]
    value = deepcopy(model)
    for i in unvoiced:
        value['frames'][i][1] &= 143
    raw = score(value)
    affected = [j for i in unvoiced for j in range(max(0, i-1), min(len(value['frames']), i+2))]
    value = tune_residual(value, affected, range(4))
    save('no-unvoiced-base', value, raw)
    no_unvoiced = deepcopy(value)

    value = deepcopy(no_unvoiced)
    for frame in value['frames']:
        if frame[2] & 15 and frame[2] >> 4:
            frame[2] = 16 | (frame[2] & 15)
    raw = score(value)
    value = tune_residual(value, range(len(value['frames'])), (0, 1))
    value['noise_filters'] = [deepcopy(value['noise_filters'][0]) for _ in range(3)]
    save('no-unvoiced-single-fir1', value, raw)

    value = deepcopy(no_unvoiced)
    for frame in value['frames']:
        frame[2] &= 15
    raw = score(value)
    value = tune_residual(value, range(len(value['frames'])), (0,))
    save('no-unvoiced-white-only', value, raw)
    if args.variants == 'compact':
        return

    value = deepcopy(model)
    gain6 = [i for i,(_,header,_) in enumerate(value['frames']) if (header >> 4) & 7 == 6]
    for i in gain6:
        choices = []
        for gain in (5, 7):
            candidate = deepcopy(value)
            candidate['frames'][i][1] = (candidate['frames'][i][1] & 143) | gain << 4
            choices.append((energy(score(candidate)), candidate))
        value = min(choices, key=lambda choice:choice[0])[1]
    raw = score(value)
    value = tune_residual(value, gain6, range(4))
    save('no-gain6', value, raw)

    colored = [i for i,(_,_,residual) in enumerate(model['frames']) if residual & 15 and residual >> 4]
    for color in (1, 2, 3):
        value = deepcopy(model)
        for i in colored:
            value['frames'][i][2] = color << 4 | (value['frames'][i][2] & 15)
        raw = score(value)
        value = tune_residual(value, colored, (0, color))
        # Copying the selected FIR makes the number of distinct filters explicit;
        # the current general decoder still renders its usual three-filter loop.
        value['noise_filters'] = [deepcopy(value['noise_filters'][color-1]) for _ in range(3)]
        save('single-fir-'+str(color), value, raw)


if __name__ == '__main__':
    main()

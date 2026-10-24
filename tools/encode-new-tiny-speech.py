#!/usr/bin/env python3
"""Fit an arbitrary 7500 Hz mono WAV into the existing 1 KB tiny decoder.

Generated candidates and listening WAVs stay in the ignored output directory.
No time compression or speech trimming is performed. A fit is a measured code
plus packed-data budget; only build-tiny-speech.py can certify runnable HEX.
"""
import argparse
from copy import deepcopy
import hashlib
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
from fixed_period import decode_fixed
from new_tiny_encoder import (analyze_reference, initialize_model, simplify_regions,
                              attenuate, measure_code, load_tiny_search, lossless_roundtrip)
from tiny_period import pack_tiny
from refine_period_helpers import atomic_json, matched_audio


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_model(model):
    for _ in range(10):
        pcm = decode_fixed(model)
        raw = decode_fixed(dict(model, dc_block_shift=0))
        if np.max(abs(pcm.astype(int)-128)) <= 121 and not np.any((raw==0)|(raw==255)):
            return model
        model = attenuate(model)
    raise RuntimeError('Could not initialize a non-clipping tiny model')


def run(reference_path, output, avr_bin, *, proposals=3000, starts=4, seed=23120,
        pitch_mode='legacy', words_choices=(1,2,4,8)):
    original, sr = sf.read(reference_path, dtype='float64')
    if sr != 7500:
        raise ValueError('Reference must be mono 7500 Hz; resample before encoding')
    output.mkdir(parents=True, exist_ok=True)
    reference, base, analysis = analyze_reference(original, starts=starts, seed=seed, pitch_mode=pitch_mode)
    sf.write(output/'reference.wav', reference, sr, subtype='PCM_16')
    objective = SpectralObjective(reference, sr)
    TinySearch = load_tiny_search()
    candidates, measurements = [], {}
    for words in words_choices:
        model = safe_model(initialize_model(reference, base, analysis, words, starts=starts, seed=seed))
        measured = deepcopy(model)
        measured['frames'][0][1] = 128 | 16 | (words-1)
        measurement = measure_code(measured, output/f'measure-{words}', avr_bin)
        measurements[str(words)] = measurement
        options = dict(words=words, stoi_floor=-1., spectral_ceiling=10., max_peak=.95,
                       max_data_bytes=65535, dc_choices=(7,), voiced_only=True,
                       residual_colors=(0,), allow_gain6=False, seed=seed+words,
                       target_flash_data_bytes=measurement['flash_data_budget'], compression_level=9)
        scorer = TinySearch(model, objective, **options)
        seen = set()
        best_fit = best_quality = None
        for width in (1,2,3,4,6,8,12,16,24,32,48,64):
            for preserve in ((True,) if width==1 else (True,False)):
                candidate = safe_model(simplify_regions(model, width, preserve_phase=preserve))
                packed = pack_tiny(candidate)
                key = packed['flash_data']+packed['eeprom']
                if key in seen:
                    continue
                seen.add(key)
                score = scorer.score(candidate)
                energy = score['loss']+8*(1-score['stoi'])
                item = dict(model=candidate, score=score, energy=energy, words=words,
                            region_blocks=width, preserve_phase=preserve,
                            flash_bytes=(measurement['code_bytes']+len(packed['flash_data'])+1)&~1)
                if best_quality is None or energy<best_quality['energy']:
                    best_quality = item
                if item['flash_bytes']<=1024 and (best_fit is None or energy<best_fit['energy']):
                    best_fit = item
        for kind,item in (('quality',best_quality),('fit',best_fit)):
            if item:
                item = deepcopy(item)
                item['kind'] = kind
                candidates.append(item)
                atomic_json(output/f'initial-{words}-{kind}-model.json', item['model'])
        print(json.dumps(dict(stage='initialized', words=words, code_bytes=measurement['code_bytes'],
                              quality=best_quality['score'], fit=best_fit['score'] if best_fit else None)), flush=True)
    quality = min((item for item in candidates if item['kind']=='quality'), key=lambda item:item['energy'])
    fits = [item for item in candidates if item['kind']=='fit']
    fit = min(fits, key=lambda item:item['energy']) if fits else None
    selected = [('quality',quality)] + ([('fit',fit)] if fit else [])
    # Total effort is bounded per clip and split between unconstrained quality
    # and hard-budget searches. A failed fit is reported, never hidden by cuts.
    searches = {}
    for kind,item in selected:
        words = item['words']
        budget = measurements[str(words)]['flash_data_budget']
        options = dict(words=words, stoi_floor=item['score']['stoi']-.03,
                       spectral_ceiling=item['score']['log_spectral_error']*1.3+.02,
                       max_peak=.95, max_data_bytes=65535, dc_choices=(7,), voiced_only=True,
                       residual_colors=(0,), allow_gain6=False, seed=seed+words,
                       max_flash_data_bytes=budget if kind=='fit' else None)
        search = TinySearch(item['model'], objective, **options)
        count = proposals//len(selected) + int(kind=='quality' and proposals%len(selected)>0)
        for _ in range(count):
            search.step()
        model = search.export()
        packed = lossless_roundtrip(model)
        score = search.score(model)
        flash = (measurements[str(words)]['code_bytes']+len(packed['flash_data'])+1)&~1
        atomic_json(output/f'{kind}-model.json', model)
        atomic_json(output/f'{kind}-checkpoint.json', search.checkpoint())
        (output/f'{kind}.raw').write_bytes(decode_fixed(model).tobytes())
        searches[kind] = dict(words=words, initial=item['score'], final=score,
                              initial_region_blocks=item['region_blocks'],
                              initial_preserve_phase=item['preserve_phase'],
                              proposals=search.proposals, evaluated=search.evaluated,
                              accepted=search.accepted, improvements=search.improvements,
                              code_bytes=measurements[str(words)]['code_bytes'],
                              data_bytes=len(packed['flash_data']), flash_bytes=flash,
                              eeprom_bytes=len(packed['eeprom']),
                              eeprom_used_bytes=packed['constants']['EEPROM_USED_BYTES'],
                              size_fits=flash<=1024, model_sha256=sha((output/f'{kind}-model.json').read_bytes()),
                              pcm_sha256=sha(decode_fixed(model).tobytes()), avr_verified=False)
        item['model'] = model
        print(json.dumps(dict(stage='refined', kind=kind, **searches[kind])), flush=True)
    audio = lambda model:(decode_fixed(model).astype(float)-128)/128
    clips = dict(Original=reference, Quality=audio(quality['model']))
    order = ['Original','Quality']
    if fit:
        clips['Fit'] = audio(fit['model'])
        order += ['Original','Fit']
    matched_audio(output, clips, objective, order)
    source_paths = [Path(__file__), CODEC/'new_tiny_encoder.py', ROOT/'tools/train-tiny-speech.py',
                    CODEC/'period_wave.py', CODEC/'fixed_search.py', CODEC/'fixed_period.py',
                    CODEC/'tiny_period.py', CODEC/'dc_blocker.py', CODEC/'tiny/firmware.S']
    report = dict(schema='new-tiny-speech-encoding-v1', reference_sha256=sha(reference_path.read_bytes()),
                  reference_samples=len(original), encoded_samples=len(reference), padding_samples=len(reference)-len(original),
                  sample_rate=sr, seed=seed, starts=starts, proposals=proposals, pitch_mode=pitch_mode,
                  entire_recording_preserved=True, time_compression=False, measurements=measurements,
                  candidates=[{k:v for k,v in item.items() if k!='model'} for item in candidates], searches=searches,
                  runtime={name:importlib.metadata.version(name) for name in ('numpy','scipy','pystoi','soundfile','numba')},
                  source_sha256_normalized_lf={str(path.relative_to(ROOT)).replace('\\','/'):
                    sha(path.read_text(encoding='utf-8').encode()) for path in source_paths},
                  status='fit-candidate' if fit else 'no-fit', hardware_tested=False)
    atomic_json(output/'quality.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--avr-bin', required=True, type=Path)
    p.add_argument('--proposals', type=int, default=3000)
    p.add_argument('--starts', type=int, default=4)
    p.add_argument('--seed', type=int, default=23120)
    p.add_argument('--pitch-mode', choices=('legacy','voice-priority'), default='legacy')
    a = p.parse_args()
    if a.proposals<0 or a.starts<1:
        p.error('Proposals must be nonnegative and starts positive')
    report = run(a.reference.resolve(), a.output.resolve(), a.avr_bin.resolve(), proposals=a.proposals,
                 starts=a.starts, seed=a.seed, pitch_mode=a.pitch_mode)
    print(json.dumps(dict(status=report['status'], searches=report['searches'])), flush=True)


if __name__=='__main__':
    main()

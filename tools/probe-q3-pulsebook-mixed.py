"""Fit frame parameters, waveform entries and binary voiced-noise flags.

The mixed-source AVR profiles leave605/603 stream bytes in a full1KB image.
The search preserves the whole reference and all arithmetic/peak guards.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q3_pulsebook as base
import q3_pulsebook_mixed as codec

spec = importlib.util.spec_from_file_location('pulsebook_mixed_search',ROOT/'tools/probe-q3-pulsebook.py')
search = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = search
spec.loader.exec_module(search)
original_mutate = search.mutate
search.render,search.validate,search.SCHEMA = codec.render,codec.validate,codec.SCHEMA
search.legacy_tables = codec.legacy_tables


def mutate(anchor,rng):
    coefficients,flags = codec.decode_book(anchor.book)
    decoded = search.State(anchor.frames,anchor.durations,coefficients,anchor.nearest,anchor.tilt)
    if rng.random() < .18:
        flags[rng.randrange(4)] ^= 1
        candidate = search.State(anchor.frames.copy(),anchor.durations.copy(),coefficients,
                                 anchor.nearest,anchor.tilt)
    else:
        candidate = original_mutate(decoded,rng)
    candidate.book = codec.encode_book(candidate.book,flags)
    return candidate


search.mutate = mutate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--model',required=True,type=Path,action='append')
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--proposals',type=int,default=6000)
    p.add_argument('--seed',type=int,default=23419)
    a = p.parse_args()
    reference,sr = sf.read(a.reference,dtype='float64')
    if sr != 7500 or reference.ndim != 1 or a.proposals < 0:
        p.error('Expected unchanged mono7500Hz reference and nonnegative proposals')
    objective = search.Objective(reference,rounded_budget=603,floor_budget=605)
    seeds,trials = [],[]
    for path in a.model:
        model = json.loads(path.read_text(encoding='utf-8'))
        if model['schema'] == 'hq4-q3-pulsebook-pole-v1':
            raise ValueError('Extended-pole coefficients are a different format')
        nearest = bool(model.get('nearest',model['schema'] == 'hq4-q3-rounded-v1'))
        frames,durations = np.asarray(model['frames'],np.uint8),np.asarray(model['durations'],np.uint16)
        book = np.asarray(model.get('pulsebook',base.legacy_tables()),np.int8)
        if model['schema'] == codec.SCHEMA:
            book,_ = codec.decode_book(book)
        frames,reuse = search.fit_budget(frames,durations,603 if nearest else 605)
        for mask in range(16):
            encoded = codec.encode_book(book,[(mask >> row)&1 for row in range(4)])
            for scale in ((1.,) if not mask else (.65,.85,1.)):
                trial = frames.copy()
                trial[:,1] = (trial[:,1]&48)|np.minimum(15,np.rint((trial[:,1]&15)*scale)).astype(np.uint8)
                state = search.State(trial,durations.copy(),encoded.copy(),nearest,1)
                state.score = objective.evaluate(state)
                trials.append(dict(source_sha256=search.sha(path),noise_mask=mask,gain_scale=scale,
                                   nearest=nearest,coefficient_reuse=reuse,score=state.score))
                if state.score is not None:
                    seeds = search.pareto_add(seeds,state)
    if not seeds:
        raise ValueError('No mixed-source seed passed full size and arithmetic guards')
    selected = [min(seeds,key=lambda s:objective.energy(s.score)),max(seeds,key=lambda s:s.score['stoi']),
                min(seeds,key=lambda s:s.score['spectrogram_loss'])]
    selected += sorted(seeds,key=lambda s:objective.energy(s.score))[:8]
    paths,seen = [],set()
    for state in selected:
        fingerprint = (state.frames.tobytes(),state.durations.tobytes(),state.book.tobytes(),state.nearest)
        if fingerprint in seen: continue
        seen.add(fingerprint)
        folder = a.output/'initial'/str(len(paths))
        search.export_state(folder,state,objective,search.sha(a.reference))
        paths.append(folder/'model.json')
    search.save(a.output/'seed-screen.json',dict(schema='pulsebook-mixed-seeds-v1',trials=trials))
    result = search.run(a.reference,paths,a.output,proposals=a.proposals,seed=a.seed,
                        rounded_budget=603,floor_budget=605)
    result['schema'],result['format'] = 'q3-pulsebook-mixed-search-v1',codec.SCHEMA
    result['eeprom_encoding'] = 'coefficient+8 in low nibble; bit4 selects gain/2 voiced noise, uniform across each16-byte row'
    for path in (Path(__file__),ROOT/'ATtiny13A/Sound/codec/q3_pulsebook_mixed.py'):
        result['source_sha256_normalized_lf'][path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    search.save(a.output/'report.json',result)
    print(json.dumps(dict(target_met=result['target_met'],finalists={k:{m:v[m] for m in
        ('stoi','spectrogram_loss','stream_bytes')} for k,v in result['finalists'].items()})),flush=True)


if __name__ == '__main__': main()

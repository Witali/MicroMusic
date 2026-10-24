"""Bounded automatic fit of K1/K2 maps, indices and original Q3 speech data.

Capacities are explicit experiment inputs. A PC result is never an assembled
1KB firmware: separate AVR assembly and three-engine proof remain necessary.
"""
import argparse
from copy import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import sys
import time

import numpy as np
import soundfile as sf
from scipy.signal import sosfilt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q3_kmap as codec
from harmonic_tracks import HarmonicTrackObjective
from hq4_speech_search import deterministic_estoi
from partial_bounds import check_partial_bounds

spec = importlib.util.spec_from_file_location('q3_kmap_base_search',ROOT/'tools/probe-q3-pulsebook.py')
search = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = search
spec.loader.exec_module(search)
search.render,search.validate,search.SCHEMA = codec.render,codec.validate,codec.SCHEMA


def mutate(anchor,rng):
    if rng.random() < .58:
        return search.mutate(anchor,rng)
    f,d,b = anchor.frames.copy(),anchor.durations.copy(),anchor.book.copy()
    row,index = rng.randrange(4,6),rng.randrange(16)
    if rng.random() < .75:
        b[row,index] = np.clip(int(b[row,index])+rng.choice((-8,-4,-2,-1,1,2,4,8)),-127,127)
    else:
        # Joint map and index change can reach a useful unused map entry.
        frame = rng.randrange(len(f))
        shift = (row-4)*4
        old = (int(f[frame,2])>>shift)&15
        b[row,index] = np.clip(int(b[row,old])+rng.choice((-8,-4,-2,2,4,8)),-127,127)
        f[frame,2] = (int(f[frame,2])&(255^(15<<shift)))|(index<<shift)
    if rng.random() < .2:
        scale = rng.choice((.8,.9,1.1))
        f[:,1] = (f[:,1]&48)|np.clip(np.rint((f[:,1]&15)*scale),0,15).astype(np.uint8)
    return search.State(f,d,b,anchor.nearest,anchor.tilt)


def export(folder,state,objective,reference_sha):
    folder.mkdir(parents=True,exist_ok=True)
    payload = codec.validate(state.frames,state.durations,state.book,len(objective.reference),objective.budget(state))
    pcm,counts = codec.render(state.frames,state.durations,state.book,state.tilt,state.nearest)
    ee = codec.pack_eeprom(state.book)
    search.save(folder/'model.json',dict(schema=codec.SCHEMA,sample_rate=7500,samples=len(pcm),
        nearest=state.nearest,tilt_shift=state.tilt,pulsebook=state.book[:4].tolist(),
        coefficient_maps=state.book[4:].tolist(),frames=state.frames.tolist(),durations=state.durations.tolist(),
        reference_sha256=reference_sha,stream_budget=objective.budget(state)))
    (folder/'speech.hq').write_bytes(payload)
    (folder/'eeprom.bin').write_bytes(ee)
    (folder/'expected.raw').write_bytes(pcm.tobytes())
    audio = (pcm.astype(float)-128)/128
    sf.write(folder/'decoded.wav',audio,7500,subtype='FLOAT')
    tracks = HarmonicTrackObjective(objective.reference)
    details = tracks.details(audio)
    raw_tracks = copy(tracks)
    raw_tracks.matched = lambda value:sosfilt(raw_tracks.hp,np.asarray(value,dtype=float))
    raw_details = raw_tracks.details(audio)
    quality = dict(state.score,estoi=deterministic_estoi(objective.reference,audio,7500),
        harmonic_metrics=details['metrics'],eeprom_bytes=len(ee),
        partial_bounds_hp70_raw_level=check_partial_bounds(raw_details,duration_seconds=len(audio)/7500),
        partial_bounds_hp70_rms_matched=check_partial_bounds(details,duration_seconds=len(audio)/7500),
        stream_sha256=hashlib.sha256(payload).hexdigest(),eeprom_sha256=hashlib.sha256(ee).hexdigest(),
        pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest(),avr_assembled=False,avr_verified=False,
        hardware_tested=False)
    search.save(folder/'quality.json',quality)
    return quality


def run(reference_path,models,output,*,floor_budget=589,rounded_budget=587,proposals=6000,seed=23501):
    reference,sr = sf.read(reference_path,dtype='float64')
    if sr != 7500 or reference.ndim != 1 or proposals < 0:
        raise ValueError('Expected unchanged mono7500Hz source and nonnegative proposal count')
    started = time.perf_counter()
    objective = search.Objective(reference,floor_budget=floor_budget,rounded_budget=rounded_budget,
                                 spectrum_target=.344975553560209)
    initial,archive = [],[]
    for path in models:
        model = json.loads(path.read_text(encoding='utf-8'))
        f,d = np.asarray(model['frames'],np.uint8),np.asarray(model['durations'],np.uint16)
        nearest = bool(model.get('nearest',model['schema'] == 'hq4-q3-rounded-v1'))
        original = len(search.pack_stream(f,d))
        f,reuse = search.fit_budget(f,d,rounded_budget if nearest else floor_budget)
        tables = codec.legacy_tables()
        if 'pulsebook' in model: tables[:4] = np.asarray(model['pulsebook'],np.int8)
        if model['schema'] == codec.SCHEMA: tables[4:] = np.asarray(model['coefficient_maps'],np.int8)
        elif np.any((f[:,2:]&15) == 0) or np.any((f[:,2:]>>4) == 0):
            raise ValueError('Old model contains incompatible coefficient0; explicit conversion required')
        for delta1 in (0,-8,8):
            for delta2 in (0,-8,8):
                for scale in ((1.,) if delta1 == delta2 == 0 else (.65,.85,1.)):
                    trial = f.copy()
                    trial[:,1] = (trial[:,1]&48)|np.minimum(15,np.rint((trial[:,1]&15)*scale)).astype(np.uint8)
                    book = tables.copy()
                    book[4] = np.clip(book[4].astype(int)+delta1,-127,127)
                    book[5] = np.clip(book[5].astype(int)+delta2,-127,127)
                    state = search.State(trial,d.copy(),book,nearest,int(model.get('tilt_shift',1)))
                    state.score = objective.evaluate(state)
                    initial.append(dict(source=path.relative_to(ROOT).as_posix(),source_sha256=search.sha(path),
                        original_stream_bytes=original,coefficient_reuse=reuse,map_offsets=[delta1,delta2],
                        gain_scale=scale,nearest=nearest,score=state.score))
                    if state.score is not None: archive = search.pareto_add(archive,state)
    if not archive: raise ValueError('No valid clean Kmap seed')
    current = min(archive,key=lambda s:objective.energy(s.score))
    rng,history = random.Random(seed),[]
    accepted = evaluated = 0
    for index in range(proposals):
        elite = min(archive,key=lambda s:objective.energy(s.score))
        if index%1500 == 0: current = rng.choice(archive)
        anchor = elite if rng.random() < .5 else (rng.choice(archive) if rng.random() < .3 else current)
        candidate = mutate(anchor,rng)
        candidate.score = objective.evaluate(candidate)
        if candidate.score is not None:
            evaluated += 1
            archive = search.pareto_add(archive,candidate)
            temperature = .006*.05**((index%1500)/1499)
            delta = objective.energy(candidate.score)-objective.energy(current.score)
            if delta <= 0 or rng.random() < math.exp(-min(700,delta/temperature)):
                current,accepted = candidate,accepted+1
        if (index+1)%500 == 0:
            elite = min(archive,key=lambda s:objective.energy(s.score))
            row = dict(proposals=index+1,evaluated=evaluated,accepted=accepted,pareto=len(archive),
                best_stoi=max(s.score['stoi'] for s in archive),
                best_spectrum=min(s.score['spectrogram_loss'] for s in archive),balanced=elite.score)
            history.append(row)
            search.save(output/'progress.json',row)
            print(json.dumps({k:v for k,v in row.items() if k != 'balanced'}),flush=True)
    finalists = dict(balanced=min(archive,key=lambda s:objective.energy(s.score)),
        best_stoi=max(archive,key=lambda s:s.score['stoi']),best_spectrum=min(archive,key=lambda s:s.score['spectrogram_loss']))
    qualities = {name:export(output/name,state,objective,search.sha(reference_path)) for name,state in finalists.items()}
    report = dict(schema='q3-kmap-search-v1',format=codec.SCHEMA,reference_sha256=search.sha(reference_path),
        samples=len(reference),sample_rate=7500,initial=initial,proposals=proposals,seed=seed,evaluated=evaluated,
        accepted=accepted,history=history,finalists=qualities,guard_rejections=objective.invalid,
        targets=dict(stoi=objective.stoi_target,spectrogram_loss=objective.spectrum_target),
        target_met=any(s.score['target_met'] for s in archive),floor_stream_budget=floor_budget,
        rounded_stream_budget=rounded_budget,capacity_policy='Explicit PC experiment capacities; no AVR size or timing claim',
        avr_qualified=False,public_firmware_changed=False,elapsed_seconds=time.perf_counter()-started,
        pareto=[dict(s.score,nearest=s.nearest) for s in sorted(archive,key=lambda s:s.score['stoi'])],
        source_sha256_normalized_lf={path.relative_to(ROOT).as_posix():hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for path in (Path(__file__),ROOT/'ATtiny13A/Sound/codec/q3_kmap.py',ROOT/'tools/probe-q3-pulsebook.py',
                         ROOT/'ATtiny13A/Sound/codec/q3_pulsebook.py',ROOT/'ATtiny13A/Sound/codec/hq4_core.py',
                         ROOT/'ATtiny13A/Sound/codec/hq4_speech_search.py',ROOT/'ATtiny13A/Sound/codec/harmonic_tracks.py',
                         ROOT/'ATtiny13A/Sound/codec/spectrogram_objective.py',ROOT/'ATtiny13A/Sound/codec/partial_bounds.py')})
    search.save(output/'report.json',report)
    print(json.dumps(dict(target_met=report['target_met'],finalists={name:{key:score[key] for key in
        ('stoi','spectrogram_loss','stream_bytes')} for name,score in qualities.items()})),flush=True)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--model',required=True,type=Path,action='append')
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--floor-budget',type=int,default=589)
    p.add_argument('--rounded-budget',type=int,default=587)
    p.add_argument('--proposals',type=int,default=6000)
    p.add_argument('--seed',type=int,default=23501)
    a = p.parse_args()
    run(a.reference.resolve(),[path.resolve() for path in a.model],a.output,
        floor_budget=a.floor_budget,rounded_budget=a.rounded_budget,proposals=a.proposals,seed=a.seed)


if __name__ == '__main__': main()

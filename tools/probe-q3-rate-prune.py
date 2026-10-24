"""Quality-aware coefficient-half reuse for a frozen Kmap speech model.

Intermediate trials use the original stream capacity. Only the finished model
must satisfy the requested smaller PC capacity. No samples or frames are cut.
AVR memory/timing qualification is deliberately separate from this encoder.
"""
import argparse
from collections import Counter
from copy import copy
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.signal import sosfilt
import soundfile as sf
from pystoi import stoi

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
import q3_kmap as codec
from hq4_core import pack_stream
from hq4_speech_search import deterministic_estoi
from harmonic_tracks import HarmonicTrackObjective
from partial_bounds import check_partial_bounds

spec = importlib.util.spec_from_file_location('q3_rate_frozen_search',ROOT/'tools/probe-q3-pulsebook.py')
search = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = search
spec.loader.exec_module(search)
search.render,search.validate,search.SCHEMA = codec.render,codec.validate,codec.SCHEMA


@dataclass
class Reuse:
    state: object
    frame: int
    half: int
    saved: int
    legacy_distance: float
    mapped_distance: float
    guide_score: float = None


def reflection_vector(frame,tables):
    """Decode indices before measuring pole-sensitive coefficient distance."""
    values = []
    for position in range(8):
        nibble = (int(frame[2+position//2]) >> ((position%2)*4)) & 15
        values.append(float(tables[4+position,nibble])/128 if position < 2 else (nibble-8)/8)
    return np.asarray(values)


def half_reuse_proposals(state):
    """Same complete two-byte packet-copy family as the old fit_budget.

    The actual packer decides whether a copy saves bytes; a later coefficient
    retransmission can cancel a nominal two-byte saving and must be rejected.
    """
    before = len(pack_stream(state.frames,state.durations))
    for index in range(1,len(state.frames)):
        for half in (2,4):
            old = state.frames[index,half:half+2]
            new = state.frames[index-1,half:half+2]
            if np.array_equal(old,new):
                continue
            f = state.frames.copy()
            f[index,half:half+2] = new
            size = len(pack_stream(f,state.durations))
            if size >= before:
                continue
            legacy = float(np.sum(abs((old.astype(int)&15)-(new.astype(int)&15)))
                +np.sum(abs((old.astype(int)>>4)-(new.astype(int)>>4))))
            a,b = reflection_vector(state.frames[index],state.book),reflection_vector(f[index],state.book)
            mapped = float(np.sum(abs(np.arctanh(a)-np.arctanh(b))))
            candidate = type(state)(f,state.durations.copy(),state.book.copy(),state.nearest,state.tilt)
            yield Reuse(candidate,index,half,before-size,legacy,mapped)


def diverse_shortlist(proposals,limit):
    """Include legacy, decoded-pole distance and actual decoded spectrum paths."""
    if not proposals:
        return []
    if limit == 0 or len(proposals) <= limit:
        return proposals
    if limit < 3:
        raise ValueError('A three-guide shortlist requires at least three candidates, or zero for all')
    queues = [sorted(proposals,key=lambda p:(p.legacy_distance/p.saved,p.frame,p.half)),
        sorted(proposals,key=lambda p:(p.mapped_distance/p.saved,p.frame,p.half)),
        sorted(proposals,key=lambda p:(float('inf') if p.guide_score is None else p.guide_score,p.frame,p.half))]
    result,seen = [],set()
    for index in range(len(proposals)):
        for queue in queues:
            candidate = queue[index]
            key = candidate.state.frames.tobytes()
            if key not in seen:
                seen.add(key)
                result.append(candidate)
                if len(result) == limit:
                    return result
    return result


def quality_prune(state,target_budget,evaluate,energy,*,shortlist=12,max_evaluations=3000,preview=None):
    """Greedy exact target-energy increase per actual saved byte.

    The evaluator must permit the original-size intermediate states. The
    smaller requested capacity is enforced here only on the final endpoint.
    """
    original_size = len(pack_stream(state.frames,state.durations))
    if not 1 <= target_budget <= original_size or max_evaluations < 0 or (shortlist != 0 and shortlist < 3):
        raise ValueError('Invalid final capacity or bounded pruning configuration')
    state.score = evaluate(state)
    if state.score is None:
        raise ValueError('Starting model fails full-duration arithmetic/size guards')
    initial = dict(state.score)
    evaluations,history,cache = 0,[],{}
    counts = Counter()
    stop_reason = 'target_reached'
    while len(pack_stream(state.frames,state.durations)) > target_budget:
        proposals = list(half_reuse_proposals(state))
        counts['enumerated_byte_saving_proposals'] += len(proposals)
        valid = []
        for proposal in proposals:
            if preview is not None:
                proposal.guide_score = preview(proposal,state)
                counts['guide_trials'] += 1
                if proposal.guide_score is None:
                    counts['guide_guard_rejections'] += 1
                    continue
            valid.append(proposal)
        proposals = diverse_shortlist(valid,shortlist)
        candidates = []
        for proposal in proposals:
            key = proposal.state.frames.tobytes()
            if key in cache:
                score = cache[key]
                counts['cached_exact_trials'] += 1
            else:
                if evaluations >= max_evaluations:
                    break
                score = evaluate(proposal.state)
                cache[key] = score
                evaluations += 1
            if score is None:
                counts['exact_guard_rejections'] += 1
                continue
            proposal.state.score = score
            delta = (energy(score)-energy(state.score))/proposal.saved
            candidates.append((delta,energy(score),-proposal.saved,proposal.frame,proposal.half,proposal))
        if not candidates:
            stop_reason = 'evaluation_budget_exhausted' if evaluations >= max_evaluations else 'no_guard_safe_byte_saving_candidate'
            break
        chosen = min(candidates,key=lambda item:item[:-1])[-1]
        history.append(dict(step=len(history)+1,frame=chosen.frame,coefficient_byte=chosen.half,
            bytes_before=len(pack_stream(state.frames,state.durations)),bytes_after=len(pack_stream(chosen.state.frames,chosen.state.durations)),
            saved_bytes=chosen.saved,energy_increase_per_byte=(energy(chosen.state.score)-energy(state.score))/chosen.saved,
            legacy_nibble_distance=chosen.legacy_distance,mapped_atanh_distance=chosen.mapped_distance,
            shortlisted_candidates=len(proposals),exact_valid_candidates=len(candidates),
            before=dict(state.score),after=dict(chosen.state.score)))
        state = chosen.state
        print(json.dumps(dict(step=len(history),bytes=len(pack_stream(state.frames,state.durations)),
            full_evaluations=evaluations,stoi=state.score['stoi'],spectrum=state.score['spectrogram_loss'])),flush=True)
        if evaluations >= max_evaluations and len(pack_stream(state.frames,state.durations)) > target_budget:
            stop_reason = 'evaluation_budget_exhausted'
            break
    size = len(pack_stream(state.frames,state.durations))
    return state,dict(initial=initial,final=dict(state.score),original_stream_bytes=original_size,
        requested_final_stream_budget=target_budget,actual_final_stream_bytes=size,
        final_fits_requested_capacity=size <= target_budget,stop_reason=stop_reason,
        exact_evaluations=evaluations,max_exact_evaluations=max_evaluations,shortlist=shortlist,
        counts=dict(counts),steps=len(history),history=history)


def measure_and_export(folder,state,reference,reference_sha,requested_budget):
    """Always expose raw guards, even if a legacy-pruned control violates them."""
    payload = codec.validate(state.frames,state.durations,state.book,len(reference))
    pcm,counts = codec.render(state.frames,state.durations,state.book,state.tilt,state.nearest)
    signed = pcm.astype(np.int16)-128
    audio = signed.astype(float)/128
    spectral = search.SpectrogramObjective(reference)
    tracks = HarmonicTrackObjective(reference)
    details = tracks.details(audio)
    raw = copy(tracks)
    raw.matched = lambda value:sosfilt(raw.hp,np.asarray(value,dtype=float))
    raw_details = raw.details(audio)
    peak,steps = int(abs(signed).max()),int(np.sum(abs(np.diff(signed)) >= 48))
    quality = dict(stoi=float(stoi(reference,audio,7500)),estoi=float(deterministic_estoi(reference,audio,7500)),
        **spectral.evaluate(audio),stream_bytes=len(payload),eeprom_bytes=64,peak_signed=peak,steps_ge48=steps,
        wrap_counts=counts.tolist(),arithmetic_peak_step_guards_pass=bool(not np.any(counts) and peak <= 115 and steps == 0),
        raw_mean=float(audio.mean()),raw_rms=float(np.sqrt(np.mean(audio**2))),
        raw_mse=float(np.mean((reference-audio)**2)),harmonic_metrics=details['metrics'],
        partial_bounds_hp70_raw_level=check_partial_bounds(raw_details,duration_seconds=len(audio)/7500),
        partial_bounds_hp70_rms_matched=check_partial_bounds(details,duration_seconds=len(audio)/7500),
        requested_final_stream_budget=requested_budget,final_fits_requested_capacity=len(payload) <= requested_budget,
        stream_sha256=hashlib.sha256(payload).hexdigest(),pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest(),
        eeprom_sha256=hashlib.sha256(codec.pack_eeprom(state.book)).hexdigest(),
        avr_assembled=False,avr_verified=False,hardware_tested=False)
    quality['target_met'] = bool(quality['stoi'] >= .9 and quality['spectrogram_loss'] <= .3449755536)
    model = dict(schema=codec.SCHEMA,sample_rate=7500,samples=len(reference),nearest=state.nearest,tilt_shift=state.tilt,
        pulsebook=state.book[:4].tolist(),coefficient_maps=state.book[4:].tolist(),frames=state.frames.tolist(),
        durations=state.durations.tolist(),reference_sha256=reference_sha,stream_budget=len(payload),
        requested_stream_budget=requested_budget)
    search.save(folder/'model.json',model)
    search.save(folder/'quality.json',quality)
    (folder/'speech.hq').write_bytes(payload)
    (folder/'eeprom.bin').write_bytes(codec.pack_eeprom(state.book))
    (folder/'expected.raw').write_bytes(pcm.tobytes())
    sf.write(folder/'decoded.wav',audio,7500,subtype='FLOAT')
    return quality


def run(reference_path,model_path,output,*,target_budget=563,max_evaluations=3000,shortlist=12):
    started = time.perf_counter()
    reference,sr = sf.read(reference_path,dtype='float64')
    model = json.loads(Path(model_path).read_text(encoding='utf-8'))
    if (model['schema'] != codec.SCHEMA or sr != 7500 or reference.ndim != 1 or len(reference) < 3072
            or not np.all(np.isfinite(reference)) or model.get('reference_sha256') != search.sha(reference_path)):
        raise ValueError('Expected a tagged Kmap model and its unchanged complete7500Hz original')
    f,d = np.asarray(model['frames'],np.uint8),np.asarray(model['durations'],np.uint16)
    tables = np.vstack((np.asarray(model['pulsebook'],np.int8),np.asarray(model['coefficient_maps'],np.int8)))
    original_size = len(codec.validate(f,d,tables,len(reference)))
    state = search.State(f,d,tables,bool(model.get('nearest',False)),int(model.get('tilt_shift',1)))
    # Critical: this is the ORIGINAL capacity, not the requested final target.
    objective = search.Objective(reference,floor_budget=original_size,rounded_budget=original_size,
        stoi_target=.9,spectrum_target=.3449755536)
    state.score = objective.evaluate(state)
    if state.score is None:
        raise ValueError('Input model fails original-size full arithmetic/peak/step guards')
    output = Path(output)
    initial = measure_and_export(output/'before',state,reference,search.sha(reference_path),original_size)
    old_f,old_changes = search.fit_budget(f,d,target_budget)
    old = search.State(old_f,d.copy(),tables.copy(),state.nearest,state.tilt)
    old_quality = measure_and_export(output/'legacy-distance',old,reference,search.sha(reference_path),target_budget)
    preview_counts = Counter()
    preview_cache = {}
    def preview(proposal,anchor):
        key = proposal.state.frames.tobytes()
        if key not in preview_cache:
            try:
                codec.validate(proposal.state.frames,d,tables,len(reference),original_size)
            except ValueError:
                preview_counts['layout'] += 1
                preview_cache[key] = None
                return None
            pcm,counts = codec.render(proposal.state.frames,d,tables,state.tilt,state.nearest)
            signed = pcm.astype(np.int16)-128
            if np.any(counts) or abs(signed).max() > 115 or np.any(abs(np.diff(signed)) >= 48):
                preview_counts['arithmetic_peak_steps'] += 1
                preview_cache[key] = None
                return None
            preview_cache[key] = objective.spectral.evaluate(signed.astype(float)/128)['spectrogram_loss']
            preview_counts['full_decoded_spectrum'] += 1
        value = preview_cache[key]
        return None if value is None else (value-anchor.score['spectrogram_loss'])/proposal.saved
    final,trace = quality_prune(state,target_budget,objective.evaluate,objective.energy,
        shortlist=shortlist,max_evaluations=max_evaluations,preview=preview)
    quality = measure_and_export(output/'quality-aware',final,reference,search.sha(reference_path),target_budget)
    sources = [Path(__file__),ROOT/'tools/probe-q3-pulsebook.py',CODEC/'q3_kmap.py',CODEC/'q3_pulsebook.py',
        CODEC/'hq4_core.py',CODEC/'spectrogram_objective.py',CODEC/'hq4_speech_search.py',CODEC/'harmonic_tracks.py',CODEC/'partial_bounds.py']
    report = dict(schema='q3-kmap-quality-rate-prune-v1',reference_sha256=search.sha(reference_path),
        source_model_sha256=search.sha(model_path),source_model_path=Path(model_path).resolve().relative_to(ROOT).as_posix(),
        samples=len(reference),sample_rate=7500,original_stream_bytes=original_size,requested_final_stream_budget=target_budget,
        initial=initial,legacy=dict(quality=old_quality,coefficient_reuse=old_changes),
        quality_aware=dict(quality=quality,trace=trace),preview_counts=dict(preview_counts),
        exact_guard_rejections=objective.invalid,targets=dict(stoi=.9,spectrogram_loss=.3449755536),
        quality_aware_dominates_legacy_stoi_spectrum=bool(quality['arithmetic_peak_step_guards_pass']
            and quality['final_fits_requested_capacity'] and quality['stoi'] >= old_quality['stoi']
            and quality['spectrogram_loss'] <= old_quality['spectrogram_loss']),
        comparison_target_energy=dict(legacy=objective.energy(old_quality),quality_aware=objective.energy(quality)),
        capacity_policy='Requested actual packed PC stream capacity; original-size intermediates; no assembled Flash/timing/AVR claim',
        shortlist_policy='Same packet-half reuse family aslegacy; interleave legacy nibble distance, mappedatanh pole distance and exact decoded spectrum-delta/byte; shortlist0 evaluates all',
        choice_policy='Full exact original STOI+spectrogram targetenergy increase peractualsavedbyte; wholeclipstate preserved; final eSTOI/rawDC/strictpartials not hidden',
        source_sha256_normalized_lf={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in sources},
        avr_qualified=False,hardware_tested=False,public_firmware_changed=False,elapsed_seconds=time.perf_counter()-started)
    search.save(output/'report.json',report)
    print(json.dumps(dict(final_fits=quality['final_fits_requested_capacity'],legacy={k:old_quality[k] for k in ('stoi','estoi','spectrogram_loss','stream_bytes')},
        quality_aware={k:quality[k] for k in ('stoi','estoi','spectrogram_loss','stream_bytes')})),flush=True)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--model',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--target-budget',type=int,default=563)
    p.add_argument('--max-evaluations',type=int,default=3000)
    p.add_argument('--shortlist',type=int,default=12,help='Zero evaluates every guard-safe byte-saving proposal')
    args = p.parse_args()
    run(args.reference,args.model,args.output,target_budget=args.target_budget,
        max_evaluations=args.max_evaluations,shortlist=args.shortlist)


if __name__ == '__main__':
    main()

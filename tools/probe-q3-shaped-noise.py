"""PC-only exhaustive row-color screen, followed by a gated bounded joint fit.

Every seed/gain has its own all-off control at the same600-byte stream cap.
Only a strict paired STOI+spectrum win enables the optional1500-proposal fit.
No AVR decoder has been implemented or budgeted for this source.
"""
import argparse
import csv
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

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
import q3_shaped_noise as codec

spec = importlib.util.spec_from_file_location('shaped_noise_search',ROOT/'tools/probe-q3-pulsebook32.py')
search = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = search
spec.loader.exec_module(search)
BASE32_SCHEMA = search.SCHEMA
# An isolated module instance reuses the frozen score/guard/export policy.
# No other search module or source file is changed.
search.render,search.validate,search.pack_book,search.SCHEMA = (
    codec.render,codec.validate,codec.pack_book,codec.SCHEMA)


def import_model(model):
    if model.get('sample_rate') != 7500 or model.get('tilt_shift',1) != 1:
        raise ValueError('Expected a7500Hz T1 source model')
    if 'nearest' in model and not isinstance(model['nearest'],bool):
        raise ValueError('Nearest flag must be a JSON boolean')
    nearest = model.get('nearest',model['schema']=='hq4-q3-rounded-v1')
    if model['schema'] == codec.SCHEMA:
        f,d,b = np.asarray(model['frames']),np.asarray(model['durations']),np.asarray(model['pulsebook'])
        codec.validate(f,d,b,model['samples'])
        c,_ = codec.decode_book(b)
        conversion = dict(original_schema=model['schema'],existing_noise_modes_reset_for_screen=True)
        return f.astype(np.uint8),d.astype(np.uint16),c,nearest,conversion
    # Use the original function's globals only for validation/conversion of
    # old plain-Q3 schemas. It expects a4x32 book, not our encoded64 bytes.
    original_validate,original_schema = search.validate,search.SCHEMA
    from q3_pulsebook32 import validate as validate32
    try:
        search.validate = validate32
        search.SCHEMA = BASE32_SCHEMA
        f,d,b,conversion = search.import_model(model)
    finally:
        search.validate = original_validate
        search.SCHEMA = original_schema
    if np.any(b[:,16:]):
        raise ValueError('Cannot silently discard nonzero32-tap source coefficients')
    return f,d,b[:,:16].copy(),nearest,conversion


def paired_win(score,control,tolerance=1e-9):
    return bool(score is not None and control is not None and
                score['stoi'] > control['stoi']+tolerance and
                score['spectrogram_loss'] < control['spectrogram_loss']-tolerance)


def mutate(anchor,rng):
    f,d = anchor.frames.copy(),anchor.durations.copy()
    c,modes = codec.decode_book(anchor.book)
    kind = rng.randrange(100)
    if kind < 20:
        row = rng.randrange(4)
        modes[row] = (int(modes[row])+rng.randrange(1,4))%4
    elif kind < 75:
        f,d = search.frame_proposal(f,d,rng)
    elif kind < 92:
        row,column = rng.randrange(4),rng.randrange(16)
        c[row,column] = max(-7,min(7,int(c[row,column])+rng.choice((-2,-1,1,2))))
    else:
        row,column = rng.randrange(4),rng.randrange(16)
        delta = rng.choice((-1,1))
        for j in range(column,min(16,column+rng.randint(2,4))):
            c[row,j] = max(-7,min(7,int(c[row,j])+delta))
        indices = np.flatnonzero((f[:,1] >> 4)==row)
        if len(indices):
            i = int(rng.choice(indices.tolist()))
            f[i,1] = (int(f[i,1])&48)|max(0,min(15,(int(f[i,1])&15)+delta))
    return search.State(f,d,codec.encode_book(c,modes),anchor.nearest,1)


def source_name(path):
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def export(folder,state,objective,reference_sha):
    result = search.export_state(folder,state,objective,reference_sha,final_metrics=True)
    result.update(pc_only=True,avr_assembled=False,avr_verified=False,hardware_tested=False,
        size_policy='Measured packed speech and64EEPROM bytes only;600-byte speech cap is a conservative screen, no complete AVR image size is known')
    search.save(folder/'quality.json',result)
    return result


def run(reference_path,model_paths,output,*,proposals=1500,seed=423107,stream_budget=600):
    if not 0 <= proposals <= 1500 or not 1 <= stream_budget <= 600:
        raise ValueError('This bounded PC probe allows0..1500 proposals and at most600 stream bytes')
    started = time.perf_counter()
    reference_path,output = Path(reference_path),Path(output)
    reference,sr = sf.read(reference_path,dtype='float64')
    if sr != 7500 or reference.ndim != 1 or len(reference)<3072 or not np.all(np.isfinite(reference)):
        raise ValueError('Expected unchanged finite mono7500Hz reference')
    reference_sha = search.sha(reference_path)
    objective = search.Objective(reference,rounded_budget=stream_budget,floor_budget=stream_budget)
    archive,controls,initializers,rows,strict_wins = [],[],[],[],[]
    best_noise = None
    for source_index,path in enumerate(model_paths):
        path = Path(path)
        model = json.loads(path.read_text(encoding='utf8'))
        f,d,c,nearest,conversion = import_model(model)
        original_size = len(search.pack_stream(f,d))
        f,reuse = search.fit_budget(f,d,stream_budget)
        initializers.append(dict(source_index=source_index,path=source_name(path),sha256=search.sha(path),
            original_stream_bytes=original_size,nearest=nearest,conversion=conversion,coefficient_reuse=reuse))
        for gain_scale in (.8,1.):
            scaled = f.copy()
            scaled[:,1] = (scaled[:,1]&48)|np.rint((scaled[:,1]&15)*gain_scale).astype(np.uint8)
            control = None
            for code in range(256):
                modes = np.array([(code >> (2*row))&3 for row in range(4)],np.uint8)
                state = search.State(scaled.copy(),d.copy(),codec.encode_book(c,modes),nearest,1)
                before = objective.invalid.copy()
                state.score = objective.evaluate(state)
                rejection = ','.join(k for k,v in objective.invalid.items() if v>before[k])
                if code == 0:
                    control = state.score
                    controls.append((f'source{source_index}-gain{gain_scale:g}',state))
                win = bool(code and paired_win(state.score,control))
                if win:
                    strict_wins.append(dict(source_index=source_index,gain_scale=gain_scale,mode_code=code,
                        noise_modes=modes.tolist(),score=state.score,control=control))
                row = dict(source_index=source_index,gain_scale=gain_scale,nearest=nearest,mode_code=code,
                    mode0=int(modes[0]),mode1=int(modes[1]),mode2=int(modes[2]),mode3=int(modes[3]),
                    valid=state.score is not None,rejection=rejection,strict_paired_win=win)
                if state.score is not None:
                    row.update({key:state.score[key] for key in ('stoi','spectrogram_loss','fine_log_error',
                        'envelope_error','unsupported_energy','missing_energy','raw_mean','raw_rms',
                        'stream_bytes','peak_signed','steps_ge48')})
                    archive = search.pareto_add(archive,state)
                    if code and (best_noise is None or state.score['stoi']>best_noise.score['stoi']):
                        best_noise = state
                rows.append(row)
            print(json.dumps(dict(source_index=source_index,gain_scale=gain_scale,
                screened=len(rows),strict_paired_wins=len(strict_wins),control=control)),flush=True)
    if not archive:
        raise ValueError('No all-off or shaped-noise state passed full arithmetic/size guards')
    output.mkdir(parents=True,exist_ok=True)
    fields = list(rows[0])+['stoi','spectrogram_loss','fine_log_error','envelope_error','unsupported_energy',
                          'missing_energy','raw_mean','raw_rms','stream_bytes','peak_signed','steps_ge48']
    fields = list(dict.fromkeys(fields))
    with (output/'screen.csv').open('w',encoding='utf8',newline='') as handle:
        writer = csv.DictWriter(handle,fieldnames=fields)
        writer.writeheader();writer.writerows(rows)
    search.save(output/'paired-wins.json',strict_wins)
    screening = dict(conditions=len(rows),valid=sum(row['valid'] for row in rows),
        strict_paired_wins=len(strict_wins),joint_fit_enabled=bool(strict_wins),
        paired_policy='Same source, coefficient reuse, rounding and quantized gain scale; STOI strictly increases AND spectrum loss strictly decreases by more than1e-9')
    print(json.dumps(dict(screening=screening)),flush=True)
    requested_proposals = proposals
    if not strict_wins:
        proposals = 0
    current = min(archive,key=lambda s:objective.energy(s.score))
    rng,history = random.Random(seed),[]
    accepted = evaluated = 0
    for index in range(proposals):
        elite = min(archive,key=lambda s:objective.energy(s.score))
        anchor = elite if rng.random()<.5 else (rng.choice(archive) if rng.random()<.3 else current)
        state = mutate(anchor,rng)
        state.score = objective.evaluate(state)
        if state.score is not None:
            evaluated += 1
            archive = search.pareto_add(archive,state)
            delta = objective.energy(state.score)-objective.energy(current.score)
            temperature = .006*.05**(index/max(proposals-1,1))
            if delta<=0 or rng.random()<math.exp(-min(700,delta/temperature)):
                current = state;accepted += 1
        if (index+1)%250 == 0:
            record = dict(proposals=index+1,evaluated=evaluated,accepted=accepted,
                best_stoi=max(s.score['stoi'] for s in archive),
                best_spectrum=min(s.score['spectrogram_loss'] for s in archive))
            history.append(record);search.save(output/'progress.json',record)
            print(json.dumps(record),flush=True)
    selected = dict(balanced=min(archive,key=lambda s:objective.energy(s.score)),
        best_stoi=max(archive,key=lambda s:s.score['stoi']),
        best_spectrum=min(archive,key=lambda s:s.score['spectrogram_loss']))
    # Keep one failed nonzero-noise example even when every colored state is
    # dominated. Its name and paired screen results never mark it a success.
    if best_noise is not None:
        selected['least_bad_noise'] = best_noise
    results = {name:export(output/name,state,objective,reference_sha) for name,state in selected.items()}
    all_off = {name:export(output/'controls'/name,state,objective,reference_sha)
               for name,state in controls if state.score is not None}
    report = dict(schema='q3-shaped-noise-probe-v1',format=codec.SCHEMA,pc_only=True,
        reference=source_name(reference_path),reference_sha256=reference_sha,samples=len(reference),sample_rate=sr,
        initializers=initializers,gain_scales=[.8,1.],gain_rounding='np.rint nearest-even before nibble packing',
        screening=screening,requested_proposals=requested_proposals,proposals=proposals,seed=seed,
        joint_evaluated=evaluated,joint_accepted=accepted,history=history,guard_rejections=objective.invalid,
        target_met=any(s.score['target_met'] for s in archive),
        targets=dict(stoi=.9,spectrogram_loss=.344975554),finalists=results,all_off_controls=all_off,
        stream_budget=stream_budget,eeprom_bytes=64,avr_code_bytes=None,avr_qualified=False,
        full_flash_bytes=None,public_firmware_changed=False,hardware_tested=False,
        objective_policy='Unchanged full reference; exact byte Q3/T1. All conditions STOI/full-spectrum/raw DC/RMS; eSTOI/top10/strict5dB for finalists and all-off controls. No AVR fit inferred from the600-byte screen cap.',
        elapsed_seconds=time.perf_counter()-started,
        source_sha256_normalized_lf={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for p in (Path(__file__),CODEC/'q3_shaped_noise.py',ROOT/'tools/probe-q3-pulsebook32.py',
                      CODEC/'q3_pulsebook.py',CODEC/'spectrogram_objective.py',CODEC/'harmonic_tracks.py')})
    search.save(output/'report.json',report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',required=True,type=Path)
    parser.add_argument('--model',required=True,type=Path,action='append')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--proposals',type=int,default=1500)
    parser.add_argument('--seed',type=int,default=423107)
    parser.add_argument('--stream-budget',type=int,default=600)
    args = parser.parse_args()
    result = run(args.reference,args.model,args.output,proposals=args.proposals,seed=args.seed,
                 stream_budget=args.stream_budget)
    print(json.dumps(dict(target_met=result['target_met'],proposals=result['proposals'],
        finalists={name:{k:value[k] for k in ('stoi','estoi','spectrogram_loss','stream_bytes')}
                   for name,value in result['finalists'].items()})),flush=True)


if __name__ == '__main__':
    main()
